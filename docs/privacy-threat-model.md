# Privacidade, retenção e modelo de ameaça

## Dados e retenção

| Área | Conteúdo | Retenção | Regra |
| --- | --- | --- | --- |
| landing | exportação transitória, inclusive aluno | elegível para Delete aos 7 dias | restrito; sem versionamento ou soft delete |
| Bronze alunos | Parquet original pseudonimizado | até destroy pós-avaliação | imutável; sem regra de lifecycle no baseline |
| Bronze não aluno | dados de fonte | até destroy pós-avaliação | imutável; sem regra de lifecycle no baseline |
| manifests de controle | metadados de release e objetos Bronze | 730 dias | lifecycle no bucket `control` |
| raw streaming | Avro e metadados técnicos | elegível para Delete aos 30 dias | acesso do pipeline; sem versionamento ou soft delete |
| quarentena | referência da mensagem, fingerprint e motivo, sem payload | elegível para Delete aos 30 dias | acesso restrito; sem versionamento ou soft delete |
| Silver aluno | normalizado, com `id_aluno` | tabelas criadas no dataset expiram em 365 dias | dataset restrito; não há DML de limpeza programado |
| Gold/evidências/logs | agregados sem aluno | conforme avaliação | proibição de `id_aluno` |

O `default_table_expiration_ms` do dataset Silver restrito incide sobre tabelas
criadas nele; não é uma rotina de DML nem uma garantia retroativa sobre toda
tabela existente. O histórico Bronze é preservado pelo baseline até o teardown
autorizado. Qualquer redução dessa retenção deve ser uma decisão explícita do
controlador de infraestrutura, revisada antes do apply.

As idades do lifecycle tornam objetos elegíveis para exclusão; o GCS executa a
ação de forma assíncrona, portanto sete ou 30 dias não são um instante garantido
de remoção. Landing, streaming e Dataflow têm `versioning=false` e soft delete
com duração zero. Quando o `Delete` termina, esses buckets não mantêm geração ou
soft delete recuperável. Bronze e control preservam as proteções configuradas.

Os manifests de controle expiram em 730 dias. Isso limita a auditabilidade de
metadados de releases mais antigos, embora os snapshots Bronze permaneçam. Os
730 dias marcam a elegibilidade da geração ativa para o lifecycle, não a remoção
permanente: versionamento e soft delete do bucket `control` ampliam a janela de
recuperação. Se a política exigir outro prazo, ajuste o lifecycle e essas duas
proteções antes do apply e registre a decisão.

Pseudônimo não é anonimização. Mesmo sem nome, `id_aluno` permanece identificador
que exige minimização, IAM e retenção.

## Ameaças e controles

| Ameaça | Controle | Evidência esperada |
| --- | --- | --- |
| leitura indevida de aluno | datasets/buckets restritos, SAs separados, IAM negativo | teste de negação por identidade |
| vazamento em logs | `id_aluno` não entra nas saídas modeladas para consumo; evidências passam por revisão antes da exposição | revisão de logs e fixtures sintéticas |
| sobrescrita de evidência | Bronze com geração condicional e manifest | tentativa de escrita repetida falha |
| manipulação de release | transação e singleton | teste de cardinalidade/rollback |
| evento duplicado/reordenado | auditoria e deduplicação determinística | fixture com repetição |
| dado inválido no Gold | Avro + validação semântica + quarentena | fixture inválida |
| credencial estática | WIF para CI e contas de serviço | revisão Terraform/IAM |
| custo por abuso | byte cap, workers, timeout e budget | plano/alerta e abortação |

Incidentes não devem ser resolvidos copiando PII para ticket, chat, print ou
evidência. Use contagem, hash ou ID sintético. A resposta operacional está no
runbook.
