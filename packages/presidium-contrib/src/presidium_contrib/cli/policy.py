"""presidium policy validate -- validate a CEL policy YAML file.

Real, deliberate reuse, not a reimplementation: parses the exact same `presidium.policies:`
YAML shape `presidium.runtime.GovernedRuntime.from_config()`/`reload_policies()` accept
(`parse_policy_rules()`, promoted to public 2026-08-24 specifically so this command can call
the real thing, not a second parser that could silently drift out of sync). Also accepts a
bare, top-level `policies:` list for a standalone policy file not embedded in a full topology.

Mirrors civitas.cli.topology's own `civitas topology validate` shape: collect every real error
(both structural -- missing `name`/`expression`, invalid enum values -- and CEL compilation
errors), print them grouped, exit 1 if anything failed, matching that command's own real,
already-established "show every issue, not just the first" UX rather than aborting on the
first bad rule the way calling `parse_policy_rules()`/`CelPolicyEngine.load_policies()` on the
whole file at once would (both raise atomically on the first bad entry).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
import yaml
from civitas.secrets.substitution import substitute_vars

from presidium.errors import PolicyCompilationError
from presidium.model import PolicyRule
from presidium.policy.cel import CelPolicyEngine
from presidium.runtime import parse_policy_rules
from presidium_contrib.cli.app import console, err_console, error, section, success

policy_app = typer.Typer(
    name="policy",
    help="Validate CEL policy YAML files.",
    no_args_is_help=True,
)


class _ValidationResult:
    """Collects categorized validation results -- same shape as civitas.cli.topology's own
    `_ValidationResult`, not reinvented, since it's the right, already-proven shape for this
    exact kind of "show everything, don't stop at the first error" CLI validation.
    """

    def __init__(self) -> None:
        self.checks: list[tuple[str, str, bool]] = []

    def ok(self, category: str, msg: str) -> None:
        self.checks.append((category, msg, True))

    def fail(self, category: str, msg: str) -> None:
        self.checks.append((category, msg, False))

    @property
    def passed(self) -> bool:
        return all(c[2] for c in self.checks)

    @property
    def error_count(self) -> int:
        return sum(1 for c in self.checks if not c[2])

    def print(self) -> None:
        current_category = ""
        for category, msg, ok in self.checks:
            if category != current_category:
                section(category)
                current_category = category
            if ok:
                success(msg)
            else:
                error(msg)


def _extract_policies_config(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Accept either a full topology file's `presidium.policies:` block or a bare, top-level
    `policies:` list -- real flexibility for a standalone policy file, not just topology-embedded
    ones.
    """
    if "presidium" in config:
        result: list[dict[str, Any]] = config["presidium"].get("policies", [])
        return result
    result = config.get("policies", [])
    return result


def _validate_policies(policies_cfg: list[dict[str, Any]]) -> _ValidationResult:
    result = _ValidationResult()

    if not policies_cfg:
        result.fail("Structure", "No policies found ('presidium.policies' or 'policies' key)")
        return result

    result.ok(
        "Structure", f"{len(policies_cfg)} polic{'y' if len(policies_cfg) == 1 else 'ies'} found"
    )

    parsed_rules: list[PolicyRule] = []
    for cfg in policies_cfg:
        name = cfg.get("name", "<unnamed>")
        try:
            rules = parse_policy_rules([cfg])
        except KeyError as exc:
            # str(KeyError("name")) is the bare, unhelpful "'name'" -- confirmed by running
            # this against a real, deliberately-broken policy file before deciding this needed
            # a clearer message, not assumed.
            result.fail("Structure", f"'{name}': missing required field {exc}")
            continue
        except ValueError as exc:
            result.fail("Structure", f"'{name}': {exc}")
            continue
        result.ok("Structure", f"'{name}': valid shape")
        parsed_rules.extend(rules)

    # Real CEL compilation check -- a rule can have a perfectly valid shape (name/stage/
    # decision all fine) and still fail here, e.g. a typo'd field reference or invalid CEL
    # syntax in `expression`. Compiled one at a time (not the whole batch via a single
    # `load_policies()` call) so a single bad expression doesn't hide every other rule's own
    # real compilation result.
    for rule in parsed_rules:
        engine = CelPolicyEngine()
        try:
            engine.load_policies([rule])
        except PolicyCompilationError as exc:
            result.fail("CEL compilation", f"'{rule.name}': {exc.detail}")
        else:
            result.ok("CEL compilation", f"'{rule.name}': compiles")

    return result


@policy_app.command("validate")
def policy_validate(
    path: str = typer.Argument(help="Path to a policy YAML file (standalone or topology)"),
) -> None:
    """Validate a CEL policy YAML file -- structure and real CEL compilation."""
    policy_path = Path(path)
    if not policy_path.exists():
        err_console.print(f"[red]Error:[/red] File '{path}' not found.")
        raise typer.Exit(1)

    try:
        config = yaml.safe_load(policy_path.read_text())
    except yaml.YAMLError as exc:
        err_console.print(f"[red]YAML parse error:[/red] {exc}")
        raise typer.Exit(1) from exc

    config = substitute_vars(config)

    console.print(f"\n  Validating [cyan]{path}[/cyan]")

    policies_cfg = _extract_policies_config(config)
    result = _validate_policies(policies_cfg)
    result.print()

    if result.passed:
        console.print(f"\n  [green]\u2714 Valid[/green]  [dim]{len(policies_cfg)} policies[/dim]\n")
    else:
        console.print(f"\n  [red]{result.error_count} errors found[/red]\n")
        raise typer.Exit(1)
