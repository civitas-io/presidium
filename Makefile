.PHONY: install lint format test test-presidium test-contrib typecheck check clean version release-presidium release-contrib

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

version:
	@echo "presidium:       $$(grep '^version' packages/presidium/pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/')"
	@echo "presidium-contrib: $$(grep '^version' packages/presidium-contrib/pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/')"

release-presidium: check
	@VERSION=$$(grep '^version' packages/presidium/pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/'); \
	echo "Releasing presidium v$$VERSION"; \
	echo "Steps:"; \
	echo "  1. Update CHANGELOG.md (move Unreleased → v$$VERSION)"; \
	echo "  2. git add -A && git commit -m 'release: presidium v$$VERSION'"; \
	echo "  3. git tag v$$VERSION"; \
	echo "  4. git push origin main --tags"; \
	echo "  → publish.yml builds + publishes to PyPI on tag push"

release-contrib: check
	@VERSION=$$(grep '^version' packages/presidium-contrib/pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/'); \
	echo "Releasing presidium-contrib v$$VERSION"; \
	echo "Steps:"; \
	echo "  1. Update CHANGELOG.md (move Unreleased → contrib-v$$VERSION)"; \
	echo "  2. git add -A && git commit -m 'release: presidium-contrib v$$VERSION'"; \
	echo "  3. git tag contrib-v$$VERSION"; \
	echo "  4. git push origin main --tags"; \
	echo "  → publish.yml builds + publishes to PyPI on tag push"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov/
