# Privacidade, retenção e modelo de ameaça

## Dados e retenção

| Área | Conteúdo | Retenção | Regra |
| --- | --- | --- | --- |
| landing | exportação transitória, inclusive aluno | 7 dias | bucket restrito |
| Bronze alunos | Parquet original pseudonimizado | 730 dias | imutável; lifecycle |
| Bronze não aluno | dados de fonte | até destroy pós-avaliação | imutável |
| raw streaming | Avro e metadados técnicos | 30 dias | acesso do pipeline |
| quarentena | eventos inválidos e motivo | 30 dias | acesso operacional restrito |
| Silver aluno | normalizado, com `id_aluno` | DML após 365 dias | dataset restrito |
| Gold/evidências/logs | agregados sem aluno | conforme avaliação | proibição de `id_aluno` |

Pseudônimo não é anonimização. Mesmo sem nome, `id_aluno` permanece identificador
que exige minimização, IAM e retenção.

## Ameaças e controles

| Ameaça | Controle | Evidência esperada |
| --- | --- | --- |
| leitura indevida de aluno | datasets/buckets restritos, SAs separados, IAM negativo | teste de negação por identidade |
| vazamento em logs | redaction e proibição de IDs em payload de log | teste/scan de logs sintéticos |
| sobrescrita de evidência | Bronze com geração condicional e manifest | tentativa de escrita repetida falha |
| manipulação de release | transação e singleton | teste de cardinalidade/rollback |
| evento duplicado/reordenado | auditoria e deduplicação determinística | fixture com repetição |
| dado inválido no Gold | Avro + validação semântica + quarentena | fixture inválida |
| credencial estática | WIF para CI e contas de serviço | revisão Terraform/IAM |
| custo por abuso | byte cap, workers, timeout e budget | plano/alerta e abortação |

Incidentes não devem ser resolvidos copiando PII para ticket, chat, print ou
evidência. Use contagem, hash ou ID sintético. A resposta operacional está no
runbook.

