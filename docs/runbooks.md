# Runbooks operacionais

Estas instruções descrevem o procedimento de provisionamento. Os dados exigidos
antes da execução estão em [cloud-prerequisites.md](cloud-prerequisites.md).

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
5. use o output `state_bucket` para preencher o bucket em uma cópia de
   `infra/stack/backend.hcl.example` chamada `infra/stack/backend.hcl`. A cópia
   de `terraform.tfvars.example`, a migração e o plano do stack só vêm depois
   do build, pois o stack exige os digests e as URIs de schema:

    # não execute o init do stack antes do passo "Stack após o build"

Se a migração for interrompida no root `infra/stack`, não apague state local ou
bucket. Confira `infra/stack/backend.hcl` e rode novamente o comando de migração
do stack (`terraform -chdir=infra/stack init -migrate-state -backend-config=backend.hcl`);
compare o backend e o plano antes de retomar.
Nunca use "-reconfigure" para resolver divergência sem entender qual state é a
fonte de verdade.

## Build, digests e schemas de referência

Depois de aplicar o bootstrap e cadastrar as oito variáveis descritas em
[cloud-prerequisites.md](cloud-prerequisites.md), dispare manualmente o workflow
`deploy-gcp`.
Ele constrói, publica e verifica imagens; não aplica Terraform nem inicia Batch
ou Dataflow. Para executar o mesmo fluxo localmente com uma identidade já
autenticada, preencha os cinco valores emitidos pelo bootstrap e rode:

```bash
export GCP_PROJECT_ID='id-do-projeto'
export GCP_REGION='us-central1'
export GCP_CLOUD_BUILD_SERVICE_ACCOUNT='saida-do-bootstrap'
export GCP_ARTIFACT_REPOSITORY='saida-do-bootstrap'
export GCP_ARTIFACT_BUCKET='saida-do-bootstrap'
git diff --quiet && git diff --cached --quiet && test -z "$(git ls-files --others --exclude-standard)" || {
  echo 'Faça commit ou limpe arquivos não rastreados antes de associar o build ao HEAD.' >&2
  exit 1
}
export GITHUB_SHA="$(git rev-parse HEAD)"
build_output="$(mktemp)"
set -o pipefail
bash cloudbuild/submit-images.sh | tee "$build_output"
```

O script espera dois builds. O primeiro publica as imagens. O segundo executa
Batch, dbt e Producer por digest e valida separadamente o launcher do Flex
Template e o runtime SDK Beam dos workers Dataflow. Depois publica
`runtime-smoke.json`. Ao terminar, o script
devolve no `stdout` um único JSON com os dois IDs, a URI do smoke, o SHA e as
cinco referências imutáveis. Ele não gera
`image-digests.json`. Valide esse JSON e use os digests no
`infra/stack/terraform.tfvars`:

```bash
build_id="$(jq -r '.build_id' "$build_output")"
jq -e '.git_sha | test("^[0-9a-f]{40}$")' "$build_output"
jq -e '.images | keys == ["batch", "dataflow_sdk", "dataflow_template", "dbt", "producer"]' "$build_output"
verification_build_id="$(jq -er '.verification_build_id' "$build_output")"
runtime_smoke_uri="$(jq -er '.runtime_smoke_uri' "$build_output")"
test -n "$verification_build_id" && test -n "$runtime_smoke_uri"
```

O único arquivo de variáveis produzido pelo build está no local abaixo. Ele é
um `tfvars.json` válido com `release_git_sha` e as seis URIs de schema; não é
artefato assinado nem SBOM:

```bash
schema_output="$(mktemp)"
gcloud storage cp \
  "gs://${GCP_ARTIFACT_BUCKET}/builds/${build_id}/reference-schema-uris.tfvars.json" \
  "$schema_output"
jq -e '
  (.release_git_sha | test("^[0-9a-f]{40}$")) and
  (.reference_schema_uris | keys == ["alunos", "meta_alfabetizacao_brasil", "meta_alfabetizacao_municipio", "meta_alfabetizacao_uf", "municipio", "uf"])
' "$schema_output"
```

Se o build, a cópia ou uma validação falhar, não use valores parciais nem tags
mutáveis.

### Exceção temporária do worker Dataflow

O worker permanece em Apache Beam 2.75.0, última versão estável adotada nesta
entrega. Essa versão declara `httplib2<0.32`, embora a correção para respostas
compactadas sem limite esteja em `httplib2 0.32.0`. O próprio Beam já
[removeu esse teto](https://github.com/apache/beam/pull/39280) no ciclo 2.76.
Enquanto essa versão não estiver publicada, o lock e a imagem aplicam somente
essa atualização. O import do Beam, o DirectRunner e os dois alvos da imagem
Dataflow fazem parte do smoke obrigatório.

Por causa desse descompasso de metadados, `pip check` na imagem Dataflow deve
apontar apenas as restrições `apache-beam 2.75.0` versus `httplib2 0.32.0` e
`cryptography 50.0.1`. O alvo `dataflow-dependency-audit` exige exatamente esses
dois conflitos de metadados e executa `pip-audit` no ambiente resultante. Qualquer
outra incompatibilidade ou vulnerabilidade bloqueia a publicação. O smoke gerenciado
continua pendente até haver projeto e credenciais GCP; ele deve cobrir criação do Flex Template,
subida de um job curto, leitura no BigQuery e encerramento do worker.

O mesmo Beam limita `cryptography` a versões anteriores à 48, mas as quatro
vulnerabilidades conhecidas na versão 47.0.0 exigem 50.0.0 ou superior. Até uma
versão compatível do Beam, a imagem instala `cryptography 50.0.1` sem resolver
novamente as dependências e fixa `pyOpenSSL 26.4.0`, compatível com essa versão.
O mesmo arquivo atualiza dependências vulneráveis herdadas da imagem-base. O NLTK,
também herdado, não é dependência de outro pacote nem é usado pelo pipeline e é
removido porque não há versão corrigida para todos os avisos. Import, DirectRunner,
auditoria e os dois alvos finais são smokes obrigatórios dessa exceção.

Revise esta exceção em toda atualização do lock e antes de publicar as imagens.
Assim que houver uma versão estável do Beam compatível com ambos os pacotes,
atualize o worker, remova `override-dependencies` e `requirements-overrides.txt`,
regenere o lock, exija `pip check` limpo e repita DirectRunner, build, smoke local e
o job curto na GCP.

## Stack após o build

Use o output `state_bucket` do bootstrap em `infra/stack/backend.hcl`, criado
localmente a partir de `backend.hcl.example`. Copie também
`terraform.tfvars.example` para o arquivo local ignorado. Preencha seus valores
de bootstrap e de imagens, mas passe `$schema_output` como um segundo arquivo
de variáveis em vez de transcrever o SHA ou as URIs de referência. Antes da
confirmação do smoke, prepare apenas backend, formatação e validação:

```bash
terraform -chdir=infra/stack init -migrate-state -backend-config=backend.hcl
terraform -chdir=infra/stack fmt -check
terraform -chdir=infra/stack validate
```

Antes do primeiro plano, recupere e valide o relatório do segundo Cloud Build.
Ele executou os entrypoints de Batch, dbt e Producer e validou o launcher Flex e
o boot do SDK Beam em referências por digest distintas publicadas pelo primeiro
build. Use `images.dataflow_template` em `dataflow_template_image` e
`images.dataflow_sdk` em `dataflow_sdk_image`:

```bash
runtime_smoke="$(mktemp)"
gcloud storage cp "$runtime_smoke_uri" "$runtime_smoke"
jq -e '.overall == "passed" and (.images | length == 5) and
  all(.images[]; test("@sha256:"))' "$runtime_smoke"
```

`scripts/verify-runtime-images.sh` continua útil para QA local; seu
`--allow-local-tags` não libera apply. A prova que libera este procedimento é o
segundo Cloud Build, com imagens terminadas em `@sha256`. Somente após a cópia e
o `jq` retornarem sucesso, defina `runtime_entrypoints_verified = true` no
`infra/stack/terraform.tfvars` local, que é ignorado pelo Git. Então execute o
primeiro plano e, quando autorizado, o apply:

```bash
terraform -chdir=infra/stack plan \
  -var-file=terraform.tfvars \
  -var-file="$schema_output"
terraform -chdir=infra/stack apply \
  -var-file=terraform.tfvars \
  -var-file="$schema_output"
```

Se a migração de state for interrompida, não apague state local ou bucket:
confira `backend.hcl`, compare os estados e retome somente após definir a fonte
de verdade.

## Batch mensal ou sob demanda

    uv run alfabetizacao batch source inspect --source municipio --demo --format json
    uv run alfabetizacao batch plan --source municipio --year 2024 --dry-run --demo-estimated-bytes 1073741824 --format json
    uv run alfabetizacao batch run --source municipio --year 2024 --dry-run --demo --format json
    uv run alfabetizacao release rollback --reference-year 2024 --table "$GCP_PROJECT.ops.active_release" --dry-run

O dry-run deve expor bytes estimados por consulta. Acima de 25 GiB, pare. O
aumento de cap exige aprovação conforme
[cloud-prerequisites.md](cloud-prerequisites.md).
Quando a execução real for autorizada, obtenha o workflow Batch pelo output do
stack e registre a execução, o `release_id`, os manifests e métricas agregadas:

```bash
batch_workflow="$(terraform -chdir=infra/stack output -json resource_inventory | jq -r '.workflows.batch')"
batch_execution="$(gcloud workflows run "$batch_workflow" \
  --location="$GCP_REGION" \
  --data='{"action":"release","year":2024}' \
  --format='value(name)')"
gcloud workflows executions describe "$batch_execution" \
  --workflow="$batch_workflow" \
  --location="$GCP_REGION" \
  --format=json
```

Não copie registros de aluno. O workflow executa as seis fontes, dbt, avaliação
e promoção, e retorna o `release_id` da execução.

## Promoção e rollback

Antes de promover, confirme: release candidato completo, regras bloqueantes
verdes, manifest de cada fonte e release ativo atual conhecidos.

Em cloud, a promoção ocorre dentro do workflow Batch. Cada candidato registra
o `baseline_release_id` que estava ativo ao começar; a promoção normal avança a
cadeia por ano e só aceita esse baseline. Para rollback autorizado, inicie o
mesmo workflow com `{"action":"rollback","year":2024}` e registre a
execução. Não atualize tabelas Gold manualmente nem aplique scripts SQL de
promoção/rollback fora do workflow. Se houver erro, consulte o ponteiro de
release ativo: se não mudou, corrija o candidato e abra nova release; se mudou
para o release errado, execute o rollback autorizado pela cadeia de baselines e
abra incidente com hashes/contagens, nunca PII.

Não passe credencial de release na linha de comando. A chamada já usa a conta
de serviço do job; os checks de estado e baseline, seguidos do update
condicional do ponteiro, são a proteção contra concorrência.

O ano é resolvido apenas dentro da cadeia ancestral ativa. O workflow escolhe a
versão efetiva mais próxima desse ano e salta diretamente para ela; se ela já
estiver ativa, a repetição termina sem mutação. O `prior_release_id` passa a ser
o baseline do alvo, portanto um retry não alterna de volta para o release
abandonado. Ano futuro, ausente ou fora de 2000–2100 falha antes de qualquer
atualização.

Correção de ano histórico é manutenção explícita, não promoção mensal comum:
volte com autorização até o ano que será corrigido, promova a correção desse
mesmo ano e então reprocese e promova, em ordem, todos os anos posteriores. Não
se corrige um ano antigo mantendo diretamente o último release como ativo; esse
atalho quebraria a lineage e pode ressuscitar release já revertido.

Os três modelos Gold históricos (`indicador_municipio`,
`comparativo_meta_resultado` e `evolucao_alfabetizacao`) têm
`full_refresh=false`. Não execute `dbt --full-refresh` para uma correção: ele
não é procedimento de reconstrução e pode apagar ancestrais necessários à
cadeia. Use o replay cronológico autorizado pelo workflow.

## Demo streaming e drain

1. obtenha `stream_demo` em `terraform -chdir=infra/stack output -json resource_inventory` e inicie o workflow com `release_year=2024`; antes de criar o Dataflow, ele exige a release ativa de 2024;
2. o workflow aguarda Dataflow em RUNNING por até 60 tentativas de 10 segundos (cerca de 10 minutos);
3. depois da fixture, staging e quarentena são aguardados em paralelo, cada um por até 60 tentativas de 10 segundos;
4. nessa mesma fase, o ramo raw procura o Avro no GCS por até 18 tentativas de 10 segundos (cerca de 3 minutos);
5. só após os três ramos terem sucesso, o workflow pede DRAIN, nunca CANCEL, e aguarda DRAINED por até 90 tentativas de 10 segundos (cerca de 15 minutos);
6. por fim, confirma o backlog das assinaturas principais em zero e nenhum
   encaminhamento à DLQ durante a execução.

```bash
stream_workflow="$(terraform -chdir=infra/stack output -json resource_inventory | jq -r '.workflows.stream_demo')"
stream_execution="$(gcloud workflows run "$stream_workflow" \
  --location="$GCP_REGION" \
  --data='{"action":"run","release_year":2024}' \
  --format='value(name)')"
gcloud workflows executions describe "$stream_execution" \
  --workflow="$stream_workflow" \
  --location="$GCP_REGION" \
  --format=json
```

O cenário esperado é 10 mensagens aceitas pelo schema, nove linhas válidas no
staging Beam, oito `event_id` lógicos em `rede=publica` na relação deduplicada,
uma cópia na auditoria, uma rejeição semântica na quarentena e oito linhas Gold
do overlay. A 11ª mensagem Avro-incompatível deve
ser rejeitada localmente antes de chamar o publisher. Estado
CANCELLED, FAILED ou timeout é falha da demo, não sucesso parcial.

Para tolerar retry de publicação, a espera do workflow confirma oito
`event_id` distintos no staging e um `event_fingerprint` distinto na
quarentena; por isso não trata o `message_id` físico como identidade de negócio.

A assinatura Pub/Sub para GCS grava no prefixo `raw/` em partições de data; ela
não cria uma pasta por `correlation_id`. Por isso, a etapa raw procura um Avro
gravado no prefixo durante a janela da demonstração. A correlação é comprovada
nas tabelas Silver, quarentena, auditoria e Gold.

Backlog não tem correlação por mensagem. No final, o workflow exige uma série e
um ponto igual a zero em `num_undelivered_messages` para cada uma das duas
assinaturas principais. Em seguida, espera cinco minutos para cobrir a janela
de visibilidade do Monitoring e percorre todas as séries e páginas de
`dead_letter_message_count` dessas assinaturas. Qualquer contagem positiva
falha a demonstração; ausência de série depois dessa barreira significa que não
houve encaminhamento no intervalo. Essa checagem não afirma que o backlog das
assinaturas de auditoria da DLQ foi inspecionado.

## Observabilidade e triagem

Os alertas provisionados cobrem erros dos Jobs Batch, dbt e Producer, testes dbt
reprovados, execução FAILED de Workflow, falha terminal do Dataflow, idade da
mensagem mais antiga e backlog das assinaturas principais e DLQs. O alerta de
Workflow também alcança falhas antes do lançamento de um Job ou Dataflow; o
alerta `is_failed` do Dataflow só existe quando houve job lançado. Antes de
intervir, confirme no alerta o recurso e a janela: backlog principal exige dez
minutos; DLQ exige um minuto; o alerta de idade exige métrica de idade maior ou
igual a 60 segundos sustentada por cinco minutos. Não promova release, escale
worker ou apague mensagem apenas por um gráfico; relacione o evento ao `run_id`
ou `correlation_id` da execução.
Por padrão, `alert_email` é nulo e as políticas não recebem canal de notificação:
elas devem ser consultadas no Console. Se o responsável definir o e-mail local antes
do apply, confirme a inscrição do destinatário e teste a entrega de forma
controlada antes de depender dela em um incidente.

O dashboard apresenta `row_count` dos manifests Batch concluídos, volume
confirmado pelo Pub/Sub e ocorrências de execução dos modelos dbt de quarentena
e duplicidade. Ocorrência de nome de modelo não representa quantidade de linhas:
consulte as tabelas de qualidade para medir o impacto. Também não existe hoje
um alerta de ausência por 35 dias. Para avaliar freshness, verifique a última
execução concluída e seu manifest; automatizar essa regra ou os totais exatos de
quarentena/duplicidade depende de um emissor ou avaliador agendado ainda não
implementado.

## Incidentes

| Sintoma | Primeira ação | Retomada segura |
| --- | --- | --- |
| DLQ maior que zero | pausar novas publicações e inspecionar motivo agregado | corrigir contrato/consumer, usar fixture nova |
| backlog crescente | conferir estado Dataflow e capacidade limitada | escalar dentro do limite aprovado; nunca criar job permanente |
| DQ bloqueante | congelar promoção e comparar manifest/partição | gerar novo release após correção da fonte/transformação |
| cap excedido | parar antes de exportar | pedir autorização de novo cap e repetir dry-run |
| Dataflow cancelado | declarar demo falha | criar execução nova; não assumir drain |
| divergência de release | consultar ponteiro singleton | rollback transacional para release anterior |
| suspeita de PII em log | restringir acesso e preservar evidência mínima | remover exposição e revisar logs/código |

## Teardown após a avaliação

Confirme primeiro que não há execução ativa e registre a confirmação humana de
que os backups ou exports permitidos foram conferidos. Desligar
`deletion_protection` é a autorização destrutiva: no destroy seguinte, o
Terraform poderá apagar o conteúdo dos datasets gerenciados, inclusive tabelas.
O teardown usa duas fases explícitas, sempre na ordem stack e depois bootstrap:

1. no stack, revise e aplique somente a retirada das proteções:

    terraform -chdir=infra/stack plan -var-file=terraform.tfvars -var-file="$schema_output" -var=deletion_protection=false
    terraform -chdir=infra/stack apply -var-file=terraform.tfvars -var-file="$schema_output" -var=deletion_protection=false

2. ainda com a mesma variável, revise `plan -destroy` e autorize o `destroy` do
   stack;
3. no bootstrap, repita o apply preparatório com
   `-var=deletion_protection=false`, confirme que o stack já foi removido e só
   então revise e execute o destroy do bootstrap.

`deletion_protection` nasce `true`; não tente contornar a fase preparatória com
`state rm`, exclusão manual ou `-reconfigure`. Retenção de Bronze não substitui
backup ou export confirmado antes do destroy pós-avaliação. Não execute destroy
em state, bucket ou projeto diferentes dos confirmados nos dois planos.

Use o mesmo `$schema_output` imutável que foi aplicado no stack. Se a sessão que
o criou terminou, recupere novamente
`gs://${GCP_ARTIFACT_BUCKET}/builds/${build_id}/reference-schema-uris.tfvars.json`
antes do plano preparatório. No `plan -destroy` e no `destroy` do stack, passe
também `-var-file=terraform.tfvars -var-file="$schema_output"` junto de
`-var=deletion_protection=false`; não aplique a retirada de proteção com
placeholders ou valores divergentes.
