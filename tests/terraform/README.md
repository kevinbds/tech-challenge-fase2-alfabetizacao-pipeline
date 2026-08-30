# Contratos Terraform

O Terraform exige que o diretório de testes esteja dentro do root em teste. Por isso, as suítes executáveis e formatadas ficam em `infra/bootstrap/tests` e `infra/stack/tests`; o RED reconstruído e os resultados completos estão nos artefatos de execução `.omo/start-work/artifacts/terraform`.

Comandos locais, sem backend nem credenciais:

```text
terraform -chdir=infra/bootstrap init -backend=false
terraform -chdir=infra/bootstrap test -verbose
terraform -chdir=infra/stack init -backend=false
terraform -chdir=infra/stack test -verbose
```
