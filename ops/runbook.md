# Operação, custos e teardown

O catálogo `observability.yml` é o contrato comum entre Terraform, alertas e operação. O canal de notificação é recebido por variável; nenhum endereço ou credencial fica versionado. Falha de ingestão, atraso superior a 35 dias, queda de volume superior a 50%, p95 de streaming a partir de 60 segundos, falha terminal do Dataflow, backlog, DLQ, qualidade crítica e orçamento possuem identificadores estáveis.

O orçamento de R$ 50,00 é um aviso para contas em BRL, não um bloqueio de cobrança. Os limites efetivos são 25 GiB faturáveis por consulta, um ou dois workers, zero instâncias mínimas e retenções de 7 dias no landing e 30 dias em streaming/quarentena. As tarifas no catálogo são premissas didáticas em BRL e devem ser revisadas antes de cada implantação.

Cada execução recebe referências de imagem por digest, SHA Git e ID de build. Proveniência é obrigatória; o SBOM é anexado quando o scanner do Artifact Registry estiver habilitado. Logs não carregam credenciais nem `id_aluno`.

O teardown começa desabilitando o Scheduler, depois solicita drain do Dataflow e aceita somente `DRAINED`. Em seguida, preserva uma cópia do estado e exige confirmação explícita antes do `terraform destroy`. `CANCELLED` ou timeout interrompem a operação.
