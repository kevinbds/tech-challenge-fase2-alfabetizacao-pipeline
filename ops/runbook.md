# Operação, custos e teardown

`ops/observability.yml` é um espelho versionado, validado por testes, das
políticas declaradas no Terraform; o Terraform não o lê em tempo de apply. As
políticas cobrem falhas de Batch, dbt e Producer, qualidade crítica, execução
FAILED de Workflow, falha terminal do Dataflow, idade da mensagem não
confirmada maior ou igual a 60 segundos por cinco minutos, backlog e DLQ. A
falha de Workflow cobre etapas anteriores ao lançamento; `is_failed` do
Dataflow só existe para jobs já lançados. Não há métrica emitida nem alerta
para freshness de 35 dias, queda de volume, p95 ponta a ponta ou avisos de
qualidade não bloqueantes; esses sinais exigem implementação futura.

`alert_email` é nulo por padrão. Nesse caso, as políticas existem no Console,
mas não têm canal de notificação externa. Para receber e-mail, o responsável
define o endereço no tfvars local antes do apply, confirma a inscrição no Google
Cloud e testa uma entrega controlada. Nenhum endereço ou credencial fica
versionado.

O orçamento de R$ 50,00 é um aviso para contas em BRL, não um bloqueio de cobrança. Os limites efetivos são 25 GiB faturáveis por consulta, um ou dois workers, zero instâncias mínimas e retenções de 7 dias no landing e 30 dias em streaming/quarentena. As tarifas no catálogo são premissas didáticas em BRL e devem ser revisadas antes de cada implantação.

As imagens publicadas pelo Cloud Build são referenciadas por digest e SHA Git. A saída do build traz `build_id` para auditoria daquele build, mas ele não identifica por si só cada execução de Batch ou Dataflow. O build solicita proveniência verificada das imagens; este fluxo não gera nem associa SBOM automaticamente. Logs não devem carregar credenciais nem `id_aluno`.

O teardown começa desabilitando o Scheduler, depois solicita drain do Dataflow e aceita somente `DRAINED`. Em seguida, preserva uma cópia do estado e exige confirmação explícita antes do `terraform destroy`. `CANCELLED` ou timeout interrompem a operação.
