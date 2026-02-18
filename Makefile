.PHONY: dev test lint check typecheck

dev:  ## Run the test project
	uv run --directory examples/test-project python app.py

test:  ## Run library tests
	uv run pytest

lint:  ## Lint with ruff
	uv run ruff check src/ tests/

typecheck:  ## Type check with mypy
	uv run mypy src/

check: lint typecheck test  ## Run all checks
