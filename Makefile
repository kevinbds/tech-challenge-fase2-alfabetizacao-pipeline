.DEFAULT_GOAL := help

.PHONY: help sync lint format-check typecheck test test-ops test-ci yaml-lint contracts \
	verify-fast verify check estimate-cost

help: ## Lista os targets locais sem executar cloud
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "%-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync: ## Sincroniza todas as dependencias bloqueadas
	uv sync --all-groups --frozen

lint: ## Executa o lint Python estrito
	uv run ruff check .

format-check: ## Confere a formatacao sem alterar arquivos
	uv run ruff format --check .

typecheck: ## Executa o basedpyright em modo all
	uv run basedpyright

test: ## Executa a suite completa com cobertura minima
	uv run pytest --cov=alfabetizacao_pipeline --cov-report=term-missing --cov-fail-under=90

test-ops: ## Exercita FinOps e contratos operacionais
	uv run pytest tests/ops tests/ci/test_yaml_lint.py --cov=alfabetizacao_pipeline.ops --cov-report=term-missing --cov-fail-under=90

test-ci: ## Valida CI, Cloud Build, containers e targets
	uv run pytest tests/ci

yaml-lint: ## Valida todos os caminhos YAML presentes
	uv run python -m alfabetizacao_pipeline.ops.yaml_lint

contracts: ## Valida catalogos por meio dos modelos Pydantic
	uv run python -c "from pathlib import Path; from alfabetizacao_pipeline.ops.catalogs import load_observability, load_run_contracts; load_observability(Path('ops/observability.yml')); load_run_contracts(Path('ops/run-contracts.yml'))"

verify-fast: lint format-check typecheck test-ops test-ci yaml-lint contracts ## Gate local rapido da plataforma

verify: sync verify-fast test ## Gate local completo

check: verify-fast ## Alias compativel com a fundacao

estimate-cost: ## Estima o perfil demo em JSON
	uv run python -m alfabetizacao_pipeline.ops.costs estimate --profile demo --format json
