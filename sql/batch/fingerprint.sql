SELECT
    COUNT(*) AS row_count,
    BIT_XOR(
        FARM_FINGERPRINT(
            TO_JSON_STRING(
                STRUCT(
                    ano,
                    id_municipio,
                    serie,
                    rede,
                    taxa_alfabetizacao,
                    media_portugues,
                    proporcao_aluno_nivel_0,
                    proporcao_aluno_nivel_1,
                    proporcao_aluno_nivel_2,
                    proporcao_aluno_nivel_3,
                    proporcao_aluno_nivel_4,
                    proporcao_aluno_nivel_5,
                    proporcao_aluno_nivel_6,
                    proporcao_aluno_nivel_7,
                    proporcao_aluno_nivel_8
                )
            )
        )
    ) AS content_fingerprint
FROM `basedosdados.br_inep_avaliacao_alfabetizacao.municipio`
WHERE ano = @year
