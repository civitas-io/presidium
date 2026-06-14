# Design: MCP Gateway

> Governed tool access — authorization + post-execution validation via Model Context Protocol.

**Status:** Draft (revised June 2026)
**Package:** `presidium` (GovernedToolProvider) + `presidium-contrib` (MCP governance reference impl)
**Milestone:** M2 (authorization) / M3 (post-execution, tool poisoning, PII masking)

## Problem Statement

MCP (Model Context Protocol) gives agents access to external tools — databases, APIs, file systems, code execution. Without governance, any agent can use any tool. There's no access control, no audit trail, no protection against tool poisoning, and no validation of tool outputs for sensitive data leakage.

## Goals

1. Grant-based tool access control via CEL policies (Presidium `PRE_TOOL`)
2. Post-execution output validation via `POST_TOOL` stage (M3) — PII detection, result filtering
3. Tool poisoning detection — hash-based fingerprinting of tool descriptions/parameters
4. Credential redaction from tool call parameters before audit logging
5. Output PII masking — detect and redact sensitive data in tool results before returning to agent
6. Audit log all tool interactions with governance context

## Non-Goals

- MCP server implementation — Civitas handles MCP client integration
- Tool discovery — agents get tools through the gateway, not by scanning
- Content validation (hallucination, factual accuracy) — separate concern (NeMo Guardrails, Guardrails AI)

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

## Post-Execution Output Validation (M3)

The `POST_TOOL` evaluation stage runs after tool execution, before the result is returned to the agent:

```
Agent calls tool
    ↓
GovernedToolProvider.check()       ← PRE_TOOL (authorization, grant check)
    ↓ ALLOW
Tool executes                      ← MCP call
    ↓ result
GovernedToolProvider.post_check()  ← POST_TOOL (output validation)
    ↓ ALLOW/DENY/REDACT
Agent receives result
```

### Output PII Masking

Tool results may contain sensitive data (SSNs, credit cards, API keys, emails) that the agent doesn't need and shouldn't persist in context. Post-execution PII masking detects and redacts before the result reaches the agent:

```python
# CEL policy example for POST_TOOL
- name: mask-pii-in-results
  stage: post_tool
  expression: >
    result.contains_pii == true
  decision: require_approval
  reason: "Tool result contains PII — review before returning to agent"
  priority: 80
```

PII detection itself is not CEL — it uses regex patterns or an external service (Microsoft Presidio, AWS Comprehend). The CEL policy decides *what to do* when PII is detected (deny, redact, require approval). The detection is a context enrichment step before policy evaluation.

### Result Size Limits

Unbounded tool results can exhaust agent context windows:

```python
- name: limit-result-size
  stage: post_tool
  expression: >
    result.size_bytes > 100000
  decision: deny
  reason: "Tool result exceeds 100KB limit"
  priority: 70
```

## MCP Governance Landscape

Research (June 2026) identified 10+ MCP gateway projects addressing tool governance. Key patterns Presidium adopts:

| Pattern | Source | Presidium approach |
|---|---|---|
| Default-deny tool access | mcp-zero, mcp-gov | `enforce-grants` policy at priority 100 |
| Tool fingerprinting | mcp-guardian | Hash-based `ToolSnapshot` in contrib |
| Output PII masking | mcp-zero (Presidio) | `POST_TOOL` stage + PII detection enrichment |
| Shadow/audit mode | mcp-guardian | `advisory` enforcement mode |
| Credential redaction | mcp-zero, mcp-guardian | Regex-based parameter redaction before audit |

AgentGateway (Linux Foundation) provides native MCP routing with CEL policies. The `presidium-contrib[agentgateway]` adapter delegates MCP routing to AgentGateway while Presidium owns authorization and post-execution validation.

## Open Questions

- Should tool approval be per-agent or global? (Lean per-agent — matches grant model)
- How do we handle tools that legitimately change (version updates)? (Re-approval workflow with diff)
- PII detection backend: built-in regex patterns vs. external service (Presidio)? (Start regex, Presidio as contrib adapter)
- Should POST_TOOL be able to *modify* results (redact inline) or only ALLOW/DENY? (Lean toward ALLOW/DENY/REDACT as a third decision type for post-execution)
- Integration with Civitas's existing MCP module?
