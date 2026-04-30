# Design: MCP Gateway

> `presidium-mcp-gateway` — Tool access governance via Model Context Protocol.

**Status:** Draft
**Package:** `presidium-mcp-gateway`
**Milestone:** M3

## Problem Statement

MCP (Model Context Protocol) gives agents access to external tools — databases, APIs, file systems, code execution. Without governance, any agent can use any tool. There's no access control, no audit trail, and no protection against tool poisoning (tools that change behavior after initial approval).

## Goals

1. Control which agents can access which tools (capability-based access control)
2. Detect tool poisoning (tool descriptions or behavior changing post-approval)
3. Redact credentials from tool call parameters before logging
4. Audit log all tool interactions
5. Implemented as a Civitas `ToolProvider` plugin

## Non-Goals

- MCP server implementation — Civitas already handles MCP client integration
- Tool discovery — agents get tools through the gateway, not by scanning
- Tool quality evaluation — that's `presidium-eval`

## Design

### Access Control

Tool access is determined by agent capabilities in the registry:

```yaml
# Registry entry:
agents:
  - name: data-analyst
    capabilities:
      - "tool:database:read"
      - "tool:spreadsheet:*"
    # Cannot access: tool:filesystem:*, tool:code_execution:*

# MCP Gateway enforces:
# data-analyst calls database.query() → ALLOW (has tool:database:read)
# data-analyst calls filesystem.write() → DENY (no tool:filesystem:* capability)
```

### Tool Poisoning Detection

```python
@dataclass
class ToolSnapshot:
    """Captures tool state at approval time."""
    name: str
    description_hash: str
    parameters_hash: str
    approved_at: datetime
    approved_by: str

class PoisoningDetector:
    """Detects tools that have changed since approval."""

    async def check(self, tool: ToolDefinition) -> PoisoningResult:
        snapshot = await self.store.get_snapshot(tool.name)
        if snapshot is None:
            return PoisoningResult(status="unapproved")

        if hash(tool.description) != snapshot.description_hash:
            return PoisoningResult(status="description_changed")

        if hash(tool.parameters) != snapshot.parameters_hash:
            return PoisoningResult(status="parameters_changed")

        return PoisoningResult(status="clean")
```

### Credential Redaction

Before logging tool call parameters, redact sensitive values:

```python
REDACTION_PATTERNS = [
    r"(?i)(api[_-]?key|token|secret|password|credential)\s*[:=]\s*\S+",
    r"(?i)bearer\s+\S+",
    r"sk-[a-zA-Z0-9]+",  # OpenAI keys
]
```

## Open Questions

- Should tool approval be per-agent or global?
- How do we handle tools that legitimately change (version updates)?
- Should the gateway support tool call interception (modify params before execution)?
- Integration with Civitas's existing MCP module?
