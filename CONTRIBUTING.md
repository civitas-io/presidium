# Contributing to Presidium

Thank you for your interest in contributing to Presidium.

## Current Status: real, implemented, published

**Corrected 2026-08-24** — this file previously described the project as "documentation-first,
before any implementation begins." That's stale; implementation has been extensive and both
packages are real, tested, and live on PyPI:

```bash
pip install presidium          # policy engine, registry, trust, credentials
pip install presidium-contrib  # real network server (M7), OPA/OpenBao/AgentGateway/SPIFFE/
                                # Slack/Postgres adapters
```

Design docs (`docs/design/`) and RFCs (`docs/rfcs/`) are still the right place to start for any
non-trivial change — this project stays documentation-driven for new capabilities (a design doc
before implementation, not the other way around) — but there is a real, substantial, tested
codebase to build on now, not a blank slate. See [HANDOFF.md](HANDOFF.md) for the current,
real, dated status, and [docs/vision/roadmap.md](docs/vision/roadmap.md) for what's left.

Ways to contribute:

1. **Real code** — see `docs/vision/roadmap.md`'s Implementation Priority section for the
   current, real P1 list
2. **Feedback on design docs** — open an issue with your thoughts on any document in `docs/design/`
3. **RFC comments** — review and comment on RFCs in `docs/rfcs/`
4. **Use case descriptions** — tell us how you'd use Presidium (open an issue)
5. **Competitive intelligence** — know a project we should evaluate? Open an issue.

## Development Setup

```bash
# Clone
git clone https://github.com/civitas-io/presidium.git
cd presidium

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies (both workspace packages, all extras)
uv sync --all-extras --package presidium --package presidium-contrib

# Install pre-commit hooks -- ruff/ruff-format/gitleaks run on every commit,
# mypy --strict + the real test suites run on every push. See
# .pre-commit-config.yaml for exactly what runs and why.
uv run pre-commit install
uv run pre-commit install --hook-type pre-push

# Run checks manually (matches what CI actually runs, package by package --
# this is a uv workspace, not a single flat package)
uv run ruff check packages/presidium/src/ packages/presidium/tests/
uv run ruff check packages/presidium-contrib/src/ packages/presidium-contrib/tests/
uv run ruff format --check packages/presidium/src/ packages/presidium/tests/
uv run ruff format --check packages/presidium-contrib/src/ packages/presidium-contrib/tests/
cd packages/presidium && uv run mypy src/presidium/ && cd -
cd packages/presidium-contrib && uv run mypy src/presidium_contrib/ && cd -
uv run --package presidium pytest packages/presidium/tests/
cd packages/presidium-contrib && uv run pytest tests/ && cd -
```

## Standards

This project follows conventions established in `civitas-io/python-civitas`:

- **Python:** ≥3.12
- **Linting:** Ruff, 100 char line length
- **Type checking:** mypy strict
- **Testing:** pytest + pytest-asyncio, 85% coverage minimum
- **Build:** hatchling via uv workspaces

See [AGENTS.md](AGENTS.md) for full conventions.

## PR Process

1. Design doc exists in `docs/design/` for new packages or non-trivial capabilities
2. All code passes `ruff check` and `ruff format --check`
3. All code passes `mypy --strict`
4. Tests pass with ≥85% coverage
5. AGENTS.md updated if conventions changed
6. CHANGELOG.md updated

## Code of Conduct

Be respectful. Be constructive. Focus on the work.
