.PHONY: sync lint format-check typecheck test check

sync:
	uv sync --all-groups

lint:
	uv run ruff check .

format-check:
	uv run ruff format --check .

typecheck:
	uv run basedpyright

test:
	uv run pytest --cov=alfabetizacao_pipeline --cov-report=term-missing --cov-fail-under=90

check: lint format-check typecheck test
