# Contributing to Presidium

Thank you for your interest in contributing to Presidium.

## Current Phase: Documentation-First

Presidium is in its documentation-first phase. We're writing design docs and RFCs before any implementation begins. The most valuable contributions right now are:

1. **Feedback on design docs** — Open an issue with your thoughts on any document in `docs/design/`
2. **RFC comments** — Review and comment on RFCs in `docs/rfcs/`
3. **Use case descriptions** — Tell us how you'd use Presidium (open an issue)
4. **Competitive intelligence** — Know a project we should evaluate? Open an issue.

## Development Setup

Once implementation begins:

```bash
# Clone
git clone https://github.com/civitas-io/presidium.git
cd presidium

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync --all-extras

# Run checks
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```

## Standards

This project follows conventions established in `civitas-io/civitas-forge`:

- **Python:** ≥3.12
- **Linting:** Ruff, 100 char line length
- **Type checking:** mypy strict
- **Testing:** pytest + pytest-asyncio, 85% coverage minimum
- **Build:** hatchling via uv workspaces

See [AGENTS.md](AGENTS.md) for full conventions.

## PR Process

1. Design doc exists in `docs/design/` for new packages
2. All code passes `ruff check` and `ruff format --check`
3. All code passes `mypy --strict`
4. Tests pass with ≥85% coverage
5. AGENTS.md updated if conventions changed
6. CHANGELOG.md updated

## Code of Conduct

Be respectful. Be constructive. Focus on the work.
