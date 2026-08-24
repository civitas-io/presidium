"""Unit tests for `presidium policy validate` via Typer's CliRunner -- real YAML files, real
CEL compilation via the actual CelPolicyEngine, not mocked.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from presidium_contrib.cli import app
from tests.unit.cli._helpers import unwrapped

runner = CliRunner()

VALID_TOPOLOGY_EMBEDDED = """
presidium:
  policies:
    - name: enforce-grants
      stage: pre_tool
      expression: >
        !agent.grants.exists(g,
          request.resource in g.resources &&
          request.action in g.actions
        )
      decision: deny
      reason: No matching grant
      priority: 100
    - name: allow-all
      stage: [pre_tool, pre_llm]
      expression: "true"
      decision: allow
      priority: 0
"""

VALID_STANDALONE = """
policies:
  - name: allow-all
    stage: pre_tool
    expression: "true"
    decision: allow
"""

BROKEN = """
policies:
  - name: bad-cel
    stage: pre_tool
    expression: "agent.grants.exists(g, )"
    decision: deny
  - stage: pre_tool
    expression: "true"
    decision: allow
  - name: good-one
    stage: pre_tool
    expression: "true"
    decision: allow
"""

EMPTY = """
some_other_key: {}
"""


def _write(tmp_path: Path, text: str, name: str = "policy.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def test_validate_topology_embedded_policies_passes(tmp_path: Path) -> None:
    path = _write(tmp_path, VALID_TOPOLOGY_EMBEDDED)
    result = runner.invoke(app, ["policy", "validate", str(path)])
    assert result.exit_code == 0, result.output


def test_validate_standalone_policies_passes(tmp_path: Path) -> None:
    path = _write(tmp_path, VALID_STANDALONE)
    result = runner.invoke(app, ["policy", "validate", str(path)])
    assert result.exit_code == 0, result.output


def test_validate_reports_every_real_error_not_just_the_first(tmp_path: Path) -> None:
    """Real, explicit proof of the "collect everything, don't stop at the first" design goal:
    a missing 'name' field AND a real CEL syntax error both fire, and the third, genuinely
    valid rule in the same file still reports as valid."""
    path = _write(tmp_path, BROKEN)
    result = runner.invoke(app, ["policy", "validate", str(path)])
    assert result.exit_code == 1
    assert "missing required field" in unwrapped(result.output)
    assert "bad-cel" in unwrapped(result.output)
    assert "good-one" in unwrapped(result.output)


INVALID_ENUM = """
policies:
  - name: bad-decision
    stage: pre_tool
    expression: "true"
    decision: not_a_real_decision
"""


def test_validate_invalid_decision_value_reports_a_real_error(tmp_path: Path) -> None:
    """Real, distinct from the missing-field case: parse_policy_rules() raises ValueError (not
    KeyError) for a structurally-present but invalid enum value."""
    path = _write(tmp_path, INVALID_ENUM)
    result = runner.invoke(app, ["policy", "validate", str(path)])
    assert result.exit_code == 1
    assert "bad-decision" in unwrapped(result.output)


def test_validate_no_policies_found_fails(tmp_path: Path) -> None:
    path = _write(tmp_path, EMPTY)
    result = runner.invoke(app, ["policy", "validate", str(path)])
    assert result.exit_code == 1


def test_validate_missing_file_fails(tmp_path: Path) -> None:
    result = runner.invoke(app, ["policy", "validate", str(tmp_path / "nope.yaml")])
    assert result.exit_code == 1


def test_validate_invalid_yaml_fails(tmp_path: Path) -> None:
    path = _write(tmp_path, "not: valid: yaml: [")
    result = runner.invoke(app, ["policy", "validate", str(path)])
    assert result.exit_code == 1
