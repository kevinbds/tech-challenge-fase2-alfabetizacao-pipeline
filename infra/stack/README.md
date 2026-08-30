# Stack GCP

O stack usa backend GCS configurado por arquivo local. Copie `backend.hcl.example`, preencha o bucket criado no bootstrap e execute a migração somente depois de conferir o estado local e autorizar a mudança:

```text
terraform init -migrate-state -backend-config=backend.hcl
```

Se a migração for interrompida, não aplique nada: compare `terraform state list` no backend anterior e no novo, preserve ambos e retome `init -migrate-state` somente quando um deles for inequivocamente a fonte de verdade. O prefixo do backend é fixo por ambiente para impedir estado stale compartilhado.

O Terraform cria buckets, datasets/tabelas, external tables, identidades, Cloud Run Jobs, Workflows, Scheduler, Pub/Sub, configuração de template Flex, métricas, alertas e budget. Ele **não** cria `google_dataflow_*_job`: o workflow de demonstração inicia um job sob demanda, aguarda RUNNING, publica a fixture e pede DRAINED. O Scheduler nasce pausado.

## Ordem cloud que depende do usuário

1. Criar/selecionar projeto com billing e autenticar o deployer.
2. Aplicar o bootstrap após revisar o plano.
3. Gerar e subir os seis Parquet zero-row em URIs imutáveis e publicar as quatro imagens por digest.
4. Migrar o backend, rodar `plan` e autorizar o stack.
5. Executar o demo; habilitar o Scheduler somente depois do primeiro lote promovido.

O budget é apenas alerta. `BRL` recebe o default acadêmico de 50; qualquer outra moeda exige valor explícito. O cap de consulta permanece em 25 GiB e o demo Dataflow limita workers a 1–2.
