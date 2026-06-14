.PHONY: install lint format test test-presidium test-contrib typecheck check clean

install:
	uv sync --all-extras --package presidium --package presidium-contrib

lint:
	uv run ruff check packages/presidium/src/ packages/presidium/tests/
	uv run ruff check packages/presidium-contrib/src/ packages/presidium-contrib/tests/

format:
	uv run ruff format packages/presidium/src/ packages/presidium/tests/
	uv run ruff format packages/presidium-contrib/src/ packages/presidium-contrib/tests/

test: test-presidium test-contrib

test-presidium:
	uv run --package presidium pytest packages/presidium/tests/ -q

test-contrib:
	uv run --package presidium-contrib pytest packages/presidium-contrib/tests/ -q

typecheck:
	cd packages/presidium && uv run mypy src/presidium/
	cd packages/presidium-contrib && uv run mypy src/presidium_contrib/

check: lint typecheck test
	@echo "All checks passed."

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov/
