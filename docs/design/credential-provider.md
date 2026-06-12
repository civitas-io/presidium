# Design: Credential Provider

> Per-agent credential management with governance context.

**Status:** Draft (June 2026)
**Package:** `presidium` (protocol + env/file defaults) / `presidium-contrib` (Vault, AWS, Infisical adapters)
**Milestone:** M2
**Requirements:** [credential-provider-requirements.md](credential-provider-requirements.md)

## Problem Statement

Agent frameworks have no credential isolation. LangChain, CrewAI, and AutoGen all read credentials from environment variables — every agent in the process can access every secret. There's no per-agent scoping, no audit trail on access, and no way to revoke a specific agent's access without redeploying.

Civitas adds per-agent `credentials:` blocks in topology YAML and `get_credential()` / `model_for()` methods on AgentProcess. But the credential values are just strings from env vars — no governance layer checks whether the agent is authorized to access that credential.

## Goals

1. Grant-based credential access — agents only get credentials they have grants for
2. Backend abstraction — swap from env vars to Vault without changing agent code
3. Transparent integration — agents keep using `self.get_credential()` unchanged
4. Audit enrichment — every access logged with governance context (which grant, what trust tier)
5. Token lifecycle — remote backends handle renewal transparently

## Non-Goals (M2)

- OAuth token exchange (OBO, XAA) — M3+
- Dynamic secret generation — M3+
- Credential rotation automation — M3+

---

## Architecture

The CredentialProvider wraps Civitas's existing credential infrastructure:

```
Topology YAML
    ↓ ${VAR_NAME} substituted (Civitas)
    ↓ credentials: block parsed (Civitas)
    ↓
CredentialProvider (Presidium)
    ↓ checks agent's grants for credential:{name}
    ↓ resolves value from backend (env/file/Vault/AWS)
    ↓ emits enriched audit event
    ↓
agent._credentials dict (Civitas)
    ↓
agent.get_credential(name) / agent.model_for(name) (Civitas)
```

The key insight: Presidium doesn't replace Civitas's credential plumbing. It sits between the topology YAML and the `agent._credentials` dict, adding a governance check.

---

## Data Model

### CredentialProvider Protocol

```python
from __future__ import annotations
from typing import Any, Protocol

class CredentialProvider(Protocol):
    """Protocol for governed credential resolution."""
    
    async def get(
        self,
        agent_id: str,
        credential_name: str,
        grants: list[Grant],
    ) -> str | None:
        """Resolve a credential for the given agent.
        
        Returns the credential value if the agent has a matching grant
        (`credential:{credential_name}` in resources, `read` in actions).
        Returns None if no grant matches or credential not found in backend.
        Emits audit event on every call (success or denial).
        """
        ...
    
    async def close(self) -> None:
        """Release backend resources (connections, tokens)."""
        ...
```

### CredentialConfig (from topology YAML)

```python
@dataclass
class CredentialConfig:
    """Parsed from the `presidium.credentials` block in topology YAML."""
    backend: str = "env"                  # "env" | "file" | "vault" | "aws" | "infisical"
    
    # Backend-specific config
    file_path: str | None = None          # for file backend
    vault_url: str | None = None          # for vault backend
    vault_auth_method: str = "token"      # "token" | "approle" | "kubernetes"
    vault_mount: str = "secret"           # KV v2 mount path
    aws_region: str | None = None         # for AWS backend
    
    # Token lifecycle
    token_ttl: int = 3600                 # seconds
    cache_ttl: int = 300                  # seconds (for remote backends)
```

---

## Default Implementations

### EnvCredentialProvider

```python
class EnvCredentialProvider:
    """Reads credentials from os.environ. Wraps Civitas's EnvSecretsProvider.
    
    Adds grant checking and audit enrichment on top of raw env var access.
    """
    
    async def get(self, agent_id, credential_name, grants):
        # 1. Check grants
        has_grant = any(
            f"credential:{credential_name}" in g.resources and "read" in g.actions
            for g in grants
        )
        if not has_grant:
            await self._audit_denied(agent_id, credential_name, "no matching grant")
            return None
        
        # 2. Resolve from env
        value = os.environ.get(credential_name) or os.environ.get(credential_name.upper())
        
        # 3. Audit
        if value is not None:
            await self._audit_granted(agent_id, credential_name)
        else:
            await self._audit_denied(agent_id, credential_name, "not found in environment")
        
        return value
```

### FileCredentialProvider

```python
class FileCredentialProvider:
    """Reads credentials from a key=value file. Wraps Civitas's FileSecretsProvider.
    
    Same grant checking and audit enrichment as EnvCredentialProvider.
    File format: one KEY=VALUE per line, # for comments, blank lines ignored.
    """
```

---

## Contrib Implementations (M3)

### VaultCredentialProvider (`presidium-contrib[vault]`)

```python
class VaultCredentialProvider:
    """Reads credentials from HashiCorp Vault KV v2 engine.
    
    Authentication: AppRole (RoleID + SecretID), Kubernetes, or token.
    Token renewal: transparent, runs in background asyncio task.
    Caching: configurable TTL, invalidated on token renewal.
    
    Secret path convention:
        /{vault_mount}/data/agents/{agent_name}/{credential_name}
    """
```

### AWSCredentialProvider (`presidium-contrib[aws]`)

```python
class AWSCredentialProvider:
    """Reads credentials from AWS Secrets Manager.
    
    Authentication: via boto3 (uses instance role, env vars, or shared credentials).
    Secret name convention: presidium/{agent_name}/{credential_name}
    Versioning: defaults to AWSCURRENT stage.
    """
```

---

## Grant Integration

Credentials are resources in the grant model. The resource format is `credential:{name}`:

```python
# Agent's grant
Grant(
    resources=["credential:anthropic", "credential:openai"],
    actions=["read"],
)
```

CEL policy can enforce credential access:

```cel
// Does the agent have a grant for this credential?
agent.grants.exists(g,
    ("credential:" + request.credential_name) in g.resources &&
    "read" in g.actions
)
```

For dynamically spawned agents, the subset grant rule applies: a child agent can only access credentials its parent has grants for.

---

## Topology YAML Integration

```yaml
presidium:
  credentials:
    backend: env    # "env" | "file" | "vault" | "aws" | "infisical"
    
    # File backend config
    # file_path: ./secrets.env
    
    # Vault backend config (presidium-contrib[vault])
    # vault_url: https://vault.internal:8200
    # vault_auth_method: approle
    # vault_mount: secret
    # token_ttl: 3600
    # cache_ttl: 300

supervision:
  children:
    - agent:
        name: researcher
        credentials:
          anthropic: ${RESEARCHER_ANTHROPIC_KEY}
```

**Flow:**
1. Civitas resolves `${RESEARCHER_ANTHROPIC_KEY}` from env
2. Presidium's CredentialProvider wraps the resolved values
3. At agent startup, CredentialProvider checks grants before populating `agent._credentials`
4. Agent calls `self.get_credential("anthropic")` — works unchanged

---

## Audit Events

Every credential access emits an enriched audit event:

```python
AuditEvent(
    event="credential.access",
    ts="2026-06-11T10:00:00Z",
    agent="presidium://acme.com/prod/researcher",
    signer_id="presidium://acme.com/prod/researcher",
    details={
        "credential_name": "anthropic",
        "result": "granted",                    # or "denied"
        "grant_match": "credential:anthropic",  # which grant matched
        "trust_tier": "standard",               # agent's trust at access time
        "backend": "env",                       # which backend resolved it
    }
)
```

Note: the credential VALUE is never logged. Only the access metadata.

---

## Civitas Integration Points

| Civitas Component | Presidium Action |
|---|---|
| `SecretsProvider` protocol | Wrapped by CredentialProvider (adds grant check + audit) |
| `agent._credentials` dict | Populated by CredentialProvider at startup |
| `get_credential()` / `model_for()` | Called by agents unchanged |
| `AuditSink.emit()` | CredentialProvider emits enriched `credential.access` events |
| `credentials:` YAML block | Parsed by Civitas, values passed through CredentialProvider |
| `${VAR_NAME}` substitution | Runs before CredentialProvider (Civitas responsibility) |

---

## Design Decisions

| # | Decision | Choice | Alternatives Considered | Rationale |
|---|---|---|---|---|
| C1 | Grant-based access | Credentials are resources: `credential:{name}` | Separate credential ACL system, no access control | Unified grant model — one system for tools, LLMs, and credentials |
| C2 | Backend abstraction | Protocol with env/file defaults | Vault-only, env-only | Same interface-first pattern as every other Presidium component |
| C3 | Civitas integration | Wrap existing `agent._credentials`, keep `get_credential()` API | New credential API on agents, replace Civitas credential system | Zero changes to Civitas. Agents don't know governance exists. |
| C4 | Token lifecycle | Transparent renewal in contrib backends | Agent-managed tokens, no renewal | Agents are application logic, not infrastructure management |
| C5 | Audit enrichment | Emit `credential.access` with grant + trust context | Use Civitas's `secret.access` as-is | Governance needs richer audit than raw access events |
| C6 | Value security | Never log credential values | Log values for debugging | Security invariant. Audit the access, not the secret. |

---

## Open Questions (Deferred)

1. **Credential rotation notification**: should agents be notified when a credential rotates? (M3)
2. **Dynamic secrets**: should Presidium support Vault's dynamic secret engines (database, AWS)? (M3)
3. **Per-credential TTL**: should individual credentials have TTLs independent of the backend? (M3)
4. **Credential sharing**: can two agents share a credential if both have grants? Or must each have its own? (M2 — lean toward sharing is fine, grant controls access)
