# Stack GCP

O stack usa backend GCS configurado por arquivo local. Copie `backend.hcl.example`, preencha o bucket criado no bootstrap e execute a migração somente depois de conferir o estado local e autorizar a mudança:

```text
terraform init -migrate-state -backend-config=backend.hcl
```

Se a migração for interrompida, não aplique nada: compare `terraform state list` no backend anterior e no novo, preserve ambos e retome `init -migrate-state` somente quando um deles for inequivocamente a fonte de verdade. O prefixo do backend é fixo por ambiente para impedir estado stale compartilhado.

O Terraform cria buckets, datasets/tabelas, external tables, identidades, Cloud Run Jobs, Workflows, Scheduler, Pub/Sub, configuração de template Flex, métricas, alertas e budget. Ele **não** cria `google_dataflow_*_job`: o workflow de demonstração inicia um job sob demanda, aguarda RUNNING, publica a fixture e pede DRAINED. O Scheduler nasce pausado.

`runtime_entrypoints_verified` começa como `false`. Antes do `plan`, recupere o
`runtime-smoke.json` do segundo Cloud Build: ele executa Batch, dbt, Producer e
Dataflow por digest, conforme [docs/runbooks.md](../../docs/runbooks.md#stack-após-o-build).
Altere a variável para `true` somente com o relatório aprovado dessas cinco
imagens. O teste mockado deste root valida o gate, não as imagens publicadas no
registry.

Use `stream_release_year=2024`: é o único ano da fixture reconciliado ao recorte
oficial e aceito pelo demo. O lote mensal
aceita `batch_reference_year=null` enquanto o Scheduler estiver pausado; para
habilitá-lo, escolha o ano da fonte antes do plano. Execuções manuais do
workflow Batch também recebem `year` explicitamente. Nenhum desses caminhos
deduz ano de negócio pelo relógio da execução.

As fontes públicas estão no multi-region `US`; mantenha `data_location="US"`
e configure `storage_location` e `region` como `us-central1`. Para liberar
consulta humana, preencha `gold_consumer_principals` com members IAM explícitos
(`user:`, `group:` ou `serviceAccount:`). O stack concede somente Job User no
projeto e Data Viewer no dataset `gold`; candidatos internos continuam ocultos.

## Ordem cloud que depende do usuário

1. Criar/selecionar projeto com billing e autenticar o deployer.
2. Aplicar o bootstrap após revisar o plano.
3. Gerar e subir os seis Parquet zero-row em URIs imutáveis, publicar as cinco imagens por digest e preencher `release_git_sha` com o SHA emitido pelo mesmo build. `dataflow_template_image` é o launcher do ContainerSpec Flex; `dataflow_sdk_image` é o runtime Beam informado em `sdkContainerImage`. As referências devem ser distintas.
4. Migrar o backend, rodar `plan` e autorizar o stack.
5. Executar o demo com `release_year`; habilitar o Scheduler somente depois do primeiro lote promovido e com `batch_reference_year` definido.

O budget é apenas alerta. Para contas de cobrança em `BRL`, o valor didático padrão é R$ 50; qualquer outra moeda exige valor explícito. O cap de consulta permanece em 25 GiB e o demo Dataflow limita workers a 1–2.

O stack não concede `roles/dataflow.worker` nem `roles/dataflow.developer` às
identidades da demo. Os papéis customizados ficam em `iam_dataflow.tf`: um reúne
somente as permissões operacionais do worker e o outro limita o workflow às
quatro operações de job que aparecem em `workflows/stream_demo.yaml`. Acesso a
bucket, tabela e `actAs` continua declarado no recurso de destino.

No teardown autorizado, mantenha `deletion_protection=true` até confirmar os
backups ou exports permitidos e encerrar execuções. Um apply separado com a
variável `false` é a autorização humana para que o destroy seguinte apague o
conteúdo dos datasets; revise esse apply e o plano de destroy antes de seguir. O
procedimento completo e a ordem stack → bootstrap estão em `docs/runbooks.md`.
