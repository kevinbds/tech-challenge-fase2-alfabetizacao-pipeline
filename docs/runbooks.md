# Runbooks operacionais

Os exemplos descrevem o caminho desejado, não afirmam que a cloud já foi
provisionada. Execute somente depois de cumprir
[user-actions.md](user-actions.md).

## Bootstrap e migração de estado

1. copie `infra/bootstrap/terraform.tfvars.example` para o arquivo local
   ignorado `infra/bootstrap/terraform.tfvars`, sem colocar segredo no Git;
2. autentique a identidade aprovada no projeto GCP;
3. valide e planeje o root inicial:

    terraform -chdir=infra/bootstrap init
    terraform -chdir=infra/bootstrap fmt -check
    terraform -chdir=infra/bootstrap validate
    terraform -chdir=infra/bootstrap plan -var-file=terraform.tfvars

4. após autorização, aplique o bootstrap;
5. confirme o bucket de estado, copie `infra/stack/terraform.tfvars.example`
   para `infra/stack/terraform.tfvars` e execute a migração solicitada pelo
   Terraform:

    terraform -chdir=infra/bootstrap init -migrate-state
    terraform -chdir=infra/stack init
    terraform -chdir=infra/stack plan -var-file=terraform.tfvars

Se a migração for interrompida, não apague state local ou bucket. Rode novamente
"terraform init -migrate-state", confira o backend e compare o plano antes de
retomar. Nunca use "-reconfigure" para resolver divergência sem entender qual
state é a fonte de verdade.

## Build com digest

A imagem usada pelo Job e pelo Flex Template deve ser identificada por digest,
não por tag mutável. O pipeline de build deve imprimir o digest e salvá-lo no
arquivo de variáveis do stack. Faça o plan do stack novamente e confirme que o
digest aparece na mudança esperada. Se build falhar ou for cancelado, descarte o
digest parcial; não reutilize tag "latest".

## Batch mensal ou sob demanda

    uv run alfabetizacao batch source inspect --source municipio --demo --format json
    uv run alfabetizacao batch plan --source municipio --year 2024 --dry-run --demo-estimated-bytes 1073741824 --format json
    uv run alfabetizacao batch run --source municipio --year 2024 --dry-run --demo --format json
    uv run alfabetizacao release select --manifests tests/releases/fixtures/manifests.json --release-id demo-2024 --year 2024 --expected-source uf --expected-source meta_alfabetizacao_brasil --expected-source meta_alfabetizacao_uf --expected-source meta_alfabetizacao_municipio --expected-source municipio --expected-source alunos

O dry-run deve expor bytes estimados. Acima de 25 GiB, pare. O aumento de cap é
uma ação humana registrada em [user-actions.md](user-actions.md). Quando a
execução real for autorizada, salve somente o manifest e métricas agregadas como
evidência. Não copie registros de aluno.

## Promoção e rollback

Antes de promover, confirme: release candidato completo, regras bloqueantes
verdes, manifest de cada fonte e release ativo atual conhecidos.

    uv run alfabetizacao release promote --release-id <release_id> --table <projeto>.ops.active_release --dry-run
    uv run alfabetizacao release rollback --active-release-id <release_id_atual> --previous-release-id <release_id_anterior> --table <projeto>.ops.active_release --dry-run

Esses dois comandos locais apenas renderizam o SQL parametrizado e recusam
`--execute`; não executam DML na cloud. Após revisão e autorização, a operação
deve executar os scripts versionados em `sql/quality/promote_release.sql` ou
`sql/quality/rollback_release.sql` no BigQuery, com os parâmetros do ambiente.
A promoção e o rollback descritos nesses scripts são transacionais. Se a operação
parar ou retornar erro, consulte `ops.active_release`: se o ponteiro não mudou,
não tente corrigir tabelas Gold manualmente. Corrija o candidato, execute os
testes e repita a promoção. Se mudou para o release errado, execute o rollback
para o release anterior conhecido e abra o incidente com hashes/contagens,
nunca PII.

## Demo streaming e drain

1. inicie o workflow de demo;
2. espere Dataflow em RUNNING por no máximo 15 minutos;
3. publique a fixture; espere o estágio por no máximo 10 minutos;
4. peça DRAIN, não CANCEL;
5. espere DRAINED por no máximo 20 minutos;
6. valide raw Avro independentemente em até 10 minutos;
7. confirme backlog e DLQs zerados.

O cenário esperado é 10 mensagens aceitas pelo schema, 8 eventos válidos
distintos no Silver, uma duplicata na auditoria e uma rejeição semântica na
quarentena. A 11ª mensagem Avro-incompatível deve falhar no publish. Estado
CANCELLED, FAILED ou timeout é falha da demo, não sucesso parcial.

## Incidentes

| Sintoma | Primeira ação | Retomada segura |
| --- | --- | --- |
| DLQ maior que zero | pausar novas publicações e inspecionar motivo agregado | corrigir contrato/consumer, usar fixture nova |
| backlog crescente | conferir estado Dataflow e capacidade limitada | escalar dentro do limite aprovado; nunca criar job permanente |
| DQ bloqueante | congelar promoção e comparar manifest/partição | gerar novo release após correção da fonte/transformação |
| cap excedido | parar antes de exportar | pedir autorização de novo cap e repetir dry-run |
| Dataflow cancelado | declarar demo falha | criar execução nova; não assumir drain |
| divergência de release | consultar ponteiro singleton | rollback transacional para release anterior |
| suspeita de PII em log | restringir acesso e preservar evidência mínima | remover exposição e revisar redaction |

## Teardown após a avaliação

Confirme primeiro que a equipe preservou as evidências permitidas e que não há
execução ativa. Rode "terraform plan -destroy" em cada root, revise recursos
protegidos e só então execute "terraform destroy" com autorização. Retenção de
Bronze não substitui destroy pós-avaliação. Não execute destroy em state, bucket
ou projeto diferentes dos confirmados no plano.
