# Catálogo de dados e contratos

## Convenções

Todos os IDs são tratados como texto quando isso preserva zeros à esquerda.
`ano` é inteiro; taxas, participações, proporções, proficiência e peso são
normalizados para `NUMERIC` no Silver. Fonte é classificada como pública,
interna operacional ou restrita. Dono operacional: equipe de dados do projeto;
dono de negócio: equipe do challenge.

| Fonte | Chave | Classificação | Campos e limites relevantes |
| --- | --- | --- | --- |
| `uf` | `(ano,sigla_uf,rede)` | pública | taxa e nove proporções em 0..100; UF, rede obrigatórias |
| `meta_alfabetizacao_brasil` | `(ano,rede)` | pública | meta por ano/rede; taxa 0..100 |
| `meta_alfabetizacao_uf` | `(ano,sigla_uf,rede)` | pública | meta por UF; taxa 0..100 |
| `meta_alfabetizacao_municipio` | `(ano,id_municipio,rede)` | pública | meta por município; município com 7 dígitos |
| `municipio` | `(ano,id_municipio,rede)` | pública | taxa, média e nove proporções; município e rede obrigatórios |
| `alunos` | `(ano,id_municipio,id_escola,id_aluno)` | restrita | `id_aluno` pseudônimo; permitido somente nas camadas restritas e proibido em Gold, saídas de consumo, logs e evidências; revisão antes da exposição |
| diretório `municipio` | ID municipal | pública | referência geográfica de normalização |

Os valores de `rede` fazem parte das colunas contratadas de cada fonte, mas os
códigos não têm o mesmo significado em todos os arquivos. Nos resultados de UF
e município, `0`, `2`, `3` e `5` viram, respectivamente, `total`, `estadual`,
`municipal` e `publica`. Em alunos, a dependência administrativa `1`, `2`, `3`
e `4` vira `federal`, `estadual`, `municipal` e `privada`. As metas já chegam
como texto; o staging apenas uniformiza caixa, espaços e o acento de `pública`.
No evento de streaming, o enum executável aceita somente `total`, `estadual`,
`municipal` e `publica`; os valores não são armazenados no manifest.

## Regras que compõem o contrato

- chaves são obrigatórias e únicas depois de quarentena;
- todo aluno referencia um município existente no diretório pelo
  `id_municipio`; resultados agregados não são usados como pai do aluno;
- a meta municipal da rede `municipal` deve encontrar o resultado municipal;
  para UF, a direção é resultado `publica` para meta `publica`;
- no nível Brasil, taxa observada e meta pertencem à mesma linha oficial. Essa
  linha entra no comparativo, mas não é contada como relacionamento entre
  fontes;
- campos Gold centrais não aceitam nulo;
- taxa, participação e proporção ficam em 0..100; proficiência e peso são
  maiores ou iguais a zero;
- as nove proporções ficam entre 99,5 e 100,5 quando somadas;
- duplicata idêntica vira aviso e é deduplicada; conflitante bloqueia e vai para
  quarentena;
- a linha oficial de 2024/RR/rede pública fica na Silver porque as metas são
  válidas e também é registrada em
  `quarantine.meta_alfabetizacao_uf_rejections` para auditoria, com fonte,
  release, execução de origem e motivo; ela gera aviso no gate e no registro
  operacional. Qualquer outra ausência obrigatória também é registrada na
  quarentena e bloqueia a promoção;
- taxa de registros duplicados: até 0,01% passa, até 0,50% avisa, acima de 0,50% bloqueia;
- volume do fato municipal acima de 20% avisa; zero ou queda maior que 50%
  bloqueia. Presença das seis fontes e relacionamentos entre elas são checks
  distintos;
- freshness máxima é 35 dias.

## Contrato do manifest

Cada manifest descreve uma fonte, partição e run. A identidade descoberta da
fonte fica em `source_identity`, com `location`, `modified_at` e `etag` quando
disponíveis. O registro também contém `row_count`, `fingerprint`, `query_hash`,
`schema_hash`, `completed_at` da ingestão imutável, `verified_at` da reconsulta
mais recente, SHA Git e digest da imagem. Os objetos Bronze aparecem em
`bronze_objects`; cada item registra `uri`, `generation`, `crc32c` e `size_bytes`.
O fingerprint cobre apenas o conteúdo do recorte de colunas contratadas. Por
isso, detecta mudança de conteúdo nesse recorte, mas não mudança de ordem nem
adição de coluna fora dele. A validação de schema é a outra metade do contrato:
ela bloqueia remoção, mudança de tipo ou de modo e classifica coluna adicional
como mudança aditiva, não bloqueante.

## Gold

| Tabela | Grão | Conteúdo | Classificação |
| --- | --- | --- | --- |
| `indicador_municipio` | `(release_id,ano,id_municipio,rede)` | resultado municipal normalizado | interna agregada |
| `comparativo_meta_resultado` | `(release_id,ano_meta,nivel_geografico,id_geografia,rede)` | meta 2024..2030; resultado, gap e status nulos enquanto o ano for futuro | interna agregada |
| `evolucao_alfabetizacao` | `(release_id,ano,id_municipio,rede)` | indicador, variação e histórico com `LAG` | interna agregada |
| `indicador_atual_hibrido` | chave do indicador municipal | lote oficial e overlay simulado posterior | interna agregada |

O `release_id` faz parte do grão físico de `indicador_municipio` e
`evolucao_alfabetizacao`. Na view pública do comparativo, a chave lógica exclui
`release_id`: entre
releases da cadeia ativa, vale a maior `reference_year` que não ultrapassa
`ano_meta`. O `release_id` selecionado continua exposto como proveniência.

## Evento de streaming

`MunicipalLiteracyRateUpdatedV1` (Avro, versão `1.0`) tem `event_id` UUID,
`event_type` fixo, `simulation=true`, `event_time` UTC, `ano` entre 2000 e
2100, `id_municipio` com sete dígitos, `rede` igual a `total`, `estadual`,
`municipal` ou `publica`,
`taxa_alfabetizacao` em 0..100, `participacao` opcional em 0..100, `producer` e
`correlation_id`. Não usa nomes reservados de metadados Pub/Sub.
