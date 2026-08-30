# Catálogo de dados e contratos

## Convenções

Todos os IDs são tratados como texto quando isso preserva zeros à esquerda.
`ano` é inteiro; taxas, participações, proporções, proficiência e peso são
normalizados para `NUMERIC` no Silver. Fonte é classificada como pública,
interna operacional ou restrita. Dono operacional: equipe de dados do projeto;
dono de negócio: equipe do challenge.

| Fonte | Chave | Classificação | Campos e limites relevantes |
| --- | --- | --- | --- |
| `uf` | `(ano,sigla_uf,rede)` | pública | taxa/participação/proporções em 0..100; UF, rede obrigatórias |
| `meta_alfabetizacao_brasil` | `(ano,rede)` | pública | meta por ano/rede; taxa 0..100 |
| `meta_alfabetizacao_uf` | `(ano,sigla_uf,rede)` | pública | meta por UF; taxa 0..100 |
| `meta_alfabetizacao_municipio` | `(ano,id_municipio,rede)` | pública | meta por município; município com 7 dígitos |
| `municipio` | `(ano,id_municipio,rede)` | pública | resultado municipal, participação, perfis e pesos |
| `alunos` | `(ano,id_municipio,id_escola,id_aluno)` | restrita | `id_aluno` pseudônimo; nunca Gold/log/evidência |
| diretório `municipio` | ID municipal | pública | referência geográfica de normalização |

As categorias de `rede` não são codificadas como suposição documental: são
descobertas na fonte no momento da execução e registradas no manifest.

## Regras que compõem o contrato

- chaves são obrigatórias e únicas depois de quarentena;
- relacionamento de aluno com pai `(ano,id_municipio,rede)` é 100%;
- campos Gold centrais não aceitam nulo;
- taxa, participação e proporção ficam em 0..100; proficiência e peso são
  maiores ou iguais a zero;
- as nove proporções ficam entre 99,5 e 100,5 quando somadas;
- duplicata idêntica vira aviso e é deduplicada; conflitante bloqueia e vai para
  quarentena;
- repetição de taxa: até 0,01 passa, até 0,50 avisa, acima de 0,50 bloqueia;
- volume acima de 20% avisa; zero ou queda maior que 50% bloqueia;
- freshness máxima é 35 dias.

## Contrato do manifest

Cada manifest descreve uma fonte, partição e run. Ele contém
`source_last_modified_time`, `source_etag`, `row_count`,
`content_fingerprint`, `query_hash`, `schema_hash`, URI, geração e CRC32C
do GCS, bytes, tempos, SHA Git e digest de imagem. O fingerprint usa as colunas
explícitas para que mudança de ordem ou coluna inesperada seja detectável.

## Gold

| Tabela | Grão | Conteúdo | Classificação |
| --- | --- | --- | --- |
| `indicador_municipio` | `(ano,id_municipio,rede)` | resultado municipal normalizado | interna agregada |
| `comparativo_meta_resultado` | `(ano_resultado,nivel_geografico,id_geografia,rede)` | meta 2024..2030, resultado, gap e status | interna agregada |
| `evolucao_alfabetizacao` | município/rede ordenado por ano | indicador, variação e histórico com `LAG` | interna agregada |
| `indicador_atual_hibrido` | chave do indicador municipal | lote oficial e overlay simulado posterior | interna agregada |

## Evento de streaming

`MunicipalLiteracyRateUpdatedV1` (Avro, versão `1.0`) tem `event_id` UUID,
`event_type` fixo, `simulation=true`, `event_time` UTC, `ano` entre 2000 e
2100, `id_municipio` com sete dígitos, `rede` pertencente às categorias da fonte,
`taxa_alfabetizacao` em 0..100, `participacao` opcional em 0..100, `producer` e
`correlation_id`. Não usa nomes reservados de metadados Pub/Sub.

