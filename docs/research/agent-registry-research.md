# Agent Registry: Industry Research

> How cloud providers, infrastructure systems, and governance frameworks model agent identity, registration, authorization, and trust.
> Researched: June 2026

## Executive Summary

Every major system that manages agent or workload identity makes the same architectural choice: identity and authorization are separate objects. Who you are is an immutable fact. What you can do is a revocable grant. This separation appears in AWS IAM (agentId vs. agentResourceRoleArn), Kubernetes RBAC (ServiceAccount vs. Role vs. RoleBinding), SPIFFE (SPIFFE ID vs. downstream policy), and Google Zanzibar (principal vs. relationship tuple). No system conflates them.

Google has the closest prior art to what Presidium needs. The Gemini Enterprise Agent Platform ships a centralized Agent Registry — a unified catalog for agents, MCP servers, tools, and endpoints, with IAM-based access control, audit logging, and dynamic endpoint resolution. Google also adopted SPIFFE as the identity substrate for agents, giving each agent a cryptographically bound, non-impersonable identity that rotates every 24 hours. This is the most complete production implementation of agent identity found in the research.

Microsoft AGT has the most mature trust scoring model: a 0-1000 scale with 5 tiers, 5 weighted dimensions, temporal decay, and trust contagion across interaction graphs. SPIFFE/SPIRE is the best model for ephemeral workloads — agents that spawn, attest, communicate, and crash, with credentials that expire naturally rather than requiring cleanup. Kubernetes RBAC has the cleanest structural pattern: three separate objects (identity, authorization definition, binding) that can be composed independently. These four systems together cover the design space Presidium needs to navigate.

---

## 1. AWS Bedrock Agents

### Agent Identity Model
- `agentId` (10-char alphanumeric) + ARN for cross-account reference
- Identity separated from authorization via `agentResourceRoleArn` (IAM Role)
- Agent metadata: `name`, `description`, `foundationModel`, `instruction` (40-4000 chars), `status` (CREATING/PREPARED/FAILED/UPDATING/DELETING)

### Versioning & Aliases
- DRAFT (mutable working version) → numbered versions (immutable snapshots via `PrepareAgent`) → aliases (pointers to versions for deployment)
- Alias routing configuration enables blue-green/canary deployment patterns
- Alias history events provide audit trail of routing changes

### Action Groups (Capabilities)
- Declare what an agent can do: `name`, `description`, `state` (ENABLED/DISABLED)
- Executor: Lambda ARN or RETURN_CONTROL
- Schema: OpenAPI 3.0 or function definitions
- Built-in signatures: `AMAZON.UserInput`, `AMAZON.CodeInterpreter`, `ANTHROPIC.Computer`, `ANTHROPIC.Bash`, `ANTHROPIC.TextEditor`
- Key pattern: capability declaration is separate from implementation

### Guardrails
- Content filters (Hate/Insults/Sexual/Violence/Misconduct/Prompt Attack)
- Denied topics, word filters, PII detection/masking, contextual grounding, automated reasoning
- Layered enforcement: org-level → account-level → application-level (most restrictive wins)
- Attached to agents via `guardrailConfiguration` (identifier + version)

### IAM Policy Structure
- Effect/Action/Resource/Condition model
- 20+ condition operators (String, Numeric, Date, Bool, IP, ARN, Null, IfExists)
- Trust policies for role assumption (who can assume this role)
- Permission boundaries (maximum permissions ceiling)

### AgentCore Policy (Cedar)
- Deterministic, auditable access control for agent-to-tool interactions
- Cedar policy language: `permit`/`forbid` with principal, action, resource, conditions
- Natural language policy authoring with automatic Cedar translation + safety validation
- Enforcement at AgentCore Gateway (outside agent code)

### IAM Roles Anywhere
- Certificate-based identity for workloads outside AWS
- Trust anchor → Profile → Role assumption
- X.509 certificate attributes extracted as principal tags for policy evaluation
- Relevant: agents may run anywhere, not just inside a cloud provider

---

## 2. Google Gemini Enterprise Agent Platform

### Agent Identity (SPIFFE-based)
- Per-agent SPIFFE identity: `spiffe://TRUST_DOMAIN/resources/SERVICE/RESOURCE_PATH`
- Cryptographically bound X.509 certificates (24-hour rotation)
- Non-impersonable (unlike shared service accounts)
- IAM principal format: `principal://agents.global.org-ORGID.system.id.goog/resources/...`

### Agent Registry (Centralized Catalog)
- Unified catalog for agents, MCP servers, tools, endpoints
- Search by keyword/prefix
- Centralized authentication via auth manager
- Dynamic endpoint resolution
- IAM-based access control + audit logging
- Data model: Agent ID, Display Name, Description, Runtime Type, Deployment Location, Version, MCP Servers, Tools, Auth Bindings, IAM Policy

### Auth Manager
- Manages OAuth credentials (2-legged machine-to-machine, 3-legged user delegation)
- API key storage
- End-user credential encryption (decrypted only at Agent Gateway)
- Audit trails

### Google Zanzibar / SpiceDB (ReBAC)
- Relationship tuples: `object#relation@user` (e.g., `document:readme#editor@bob`)
- Userset rewrite rules for computed permissions: `permission view = owner + editor + viewer + parent->viewer`
- Schema definition language for namespace configuration
- Zookies (consistency tokens) prevent the "new enemy problem"
- Scale: 10M+ QPS, 2+ trillion ACLs, <10ms 95th percentile
- Open-source implementation: SpiceDB by AuthZed

### Agent Grants via Zanzibar Tuples
- Model agent-to-resource permissions: `agent:researcher#can_use@tool:web_search`
- Supports inheritance: `team:engineering#member@agent:researcher` → team grants flow to agent
- Supports delegation with computed permissions
- Schema example:
  ```zed
  definition agent {
    relation owner: user
    relation can_use: tool
  }
  definition tool {
    relation accessible_by: agent
    permission use = accessible_by
  }
  ```

### GCP IAM & Service Accounts
- Service account identity: `SA@PROJECT.iam.gserviceaccount.com`
- Key difference from Agent Identity: service accounts are shared and impersonable; agent identities are per-agent and non-impersonable
- Workload Identity Federation: external workloads → STS → service account → GCP resources

---

## 3. Microsoft AGT (Agent Governance Toolkit)

### Agent Identity (DID-based)
- DID format: `did:mesh:<128-bit-hex>` (128 bits = 32 hex chars from `secrets.token_hex(16)`)
- Ed25519 keypairs for all signatures
- `AgentIdentity` fields: `did`, `name`, `description`, `public_key`, `verification_key_id`, `sponsor_email`, `sponsor_verified`, `organization`, `organization_id`, `capabilities`, `created_at`, `updated_at`, `expires_at`, `status` (active/suspended/revoked), `revocation_reason`, `parent_did`, `delegation_depth` (0-5), `max_initial_trust_score`
- Mandatory human sponsor: every agent has a human accountable for it
- Delegation chains with depth limits (max 5) and trust ceiling propagation

### Trust Scoring (0-1000 Scale)
- Default: 500 (Standard tier)
- 5 tiers:
  - 900-1000: Verified Partner (full autonomy)
  - 700-899: Trusted (high autonomy)
  - 500-699: Standard (normal operations)
  - 300-499: Probationary (restricted)
  - 0-299: Untrusted (sandbox only)
- Revocation threshold: 300
- 5 weighted dimensions:
  - Policy compliance: 25%
  - Security posture: 25%
  - Output quality: 20%
  - Resource efficiency: 15%
  - Collaboration health: 15%

### Trust Decay Algorithm
- Temporal decay: 2 points/hour with no positive signals
- Trust contagion: if agent A trusts B and B fails, A's score decays proportionally (30% propagation factor, 2-hop depth)
- Behavioral regime detection: KL divergence between recent (1 hour) and historical (30 days) action distributions triggers alerts at threshold 0.5
- Network-aware: interaction graph tracks `(from_did, to_did)` edges

### Privilege Rings (0-3)
- Ring 0 (Root): Hypervisor config, requires SRE Witness. Full access.
- Ring 1 (Privileged): Non-reversible actions, requires `eff_score > 0.95` + consensus. Full network/filesystem/subprocess.
- Ring 2 (Standard): Reversible actions, requires `eff_score > 0.60`. Network allowed, scoped filesystem, 8 concurrent tools max.
- Ring 3 (Sandbox): Read-only, default for unknown agents. No network, no filesystem write, no subprocess, 2 concurrent tools max.

### Policy Engine
- `PolicyRule` fields: `name`, `description`, `stage` (pre_input/pre_tool/post_tool/pre_output), `condition` (expression string), `action` (allow/deny/warn/require_approval/log), `limit` (rate string), `approvers`, `priority`, `enabled`
- Fail-closed semantics: evaluation errors default to MATCH (deny)
- Supports YAML, OPA Rego, Cedar
- Example: `condition: "action.type == 'export' and agent.trust_score < 500"` → `action: deny`

### Zero-Trust Workflow
1. Agent registered → DID + Ed25519 keypair generated
2. Human sponsor verifies
3. Initial trust: 500 (Standard), Ring 3 (Sandbox)
4. Every action evaluated by policy engine
5. Trust score updated based on behavior
6. Ring elevation/demotion based on effective score

---

## 4. IBM watsonx Orchestrate

### Agent Registry API
- REST: `POST /v1/orchestrate/agents` with `name`, `display_name`, `config` (type, model, tools), `metadata` (publisher, tags, version)
- Listing: `GET /v1/orchestrate/agents?query=...&limit=50`
- Multi-framework: native, LangGraph, A2A

### CUGA (Compositional Unified Governance Architecture)
- 5 structural checkpoints embedded in the agent pipeline:
  1. Intent Guard (upstream of planning)
  2. Playbook (within system prompt)
  3. Tool Guide (at tool-call boundary)
  4. Tool Approvals (outside reasoning loop)
  5. Output Formatter (at output stage)
- Policy-as-code, no model fine-tuning required
- Typed governance primitives per checkpoint
- Explicit conflict handling for overlapping policies

### Entra Agent ID (Microsoft + IBM convergence)
- Extends Entra ID to AI agent identities
- Lifecycle: provisioning → approval → activation → rotation → decommission
- Mandatory human sponsor
- Conditional Access policies target agent identities
- Revocation in ≤5 seconds

---

## 5. Infrastructure Identity Systems

### SPIFFE/SPIRE
- SPIFFE ID format: `spiffe://trust-domain/path` (max 2048 bytes)
- SVID: X.509 (SPIFFE ID in SAN extension, short-lived, auto-rotated) or JWT (`sub` claim = SPIFFE ID, audience required)
- Designed for ephemeral workloads: spawn → attest → issue SVID → communicate → crash → SVID expires naturally
- Two-phase attestation: node (verify host) + workload (verify process via selectors: UID, container ID, K8s namespace/SA)
- Registration entry: Entry ID, SPIFFE ID, Parent ID, Selectors, TTL, Hint, Federated Trust Domains
- Trust domains + federation via SPIFFE bundles (JWK sets)

### Kubernetes RBAC
- Identity: ServiceAccount (name + namespace, JWT token auto-mounted)
- Authorization: Role/ClusterRole with rules (`apiGroups`, `resources`, `verbs`, `resourceNames`)
- Binding: RoleBinding/ClusterRoleBinding links identity to authorization
- Namespace scoping for isolation
- Admission webhooks for policy enforcement at API level
- The pattern: 3 separate objects (identity, authorization, binding) — clean separation

### OAuth 2.0 Client Credentials
- Client ID as identity, client secret as credential
- Scopes as grants: `read:logs write:metrics`
- Token-based, time-limited
- Resource server validates scope on each request

### Workload Identity (K8s → Cloud IAM)
- GKE: K8s ServiceAccount → GCP IAM Service Account via annotation + workload identity pool
- EKS: K8s ServiceAccount → AWS IAM Role via OIDC provider + trust policy
- Pattern: local identity maps to cloud identity for resource access

---

## 6. Academic Research (2026)

### Auditable Agents (arXiv:2604.05485)
- 5 dimensions: action recoverability, lifecycle coverage, policy checkability, responsibility attribution, evidence integrity
- 3 mechanism classes: detect (real-time), enforce (preventive), recover (forensic)
- Key finding: no single temporal vantage point supplies all 5 dimensions

### Overlaying Governance (arXiv:2606.03518)
- Compositional authorization: overlay agentic semantics on existing relational policies
- Recursive delegation with scope attenuation (child gets narrower permissions)
- Dynamic scoping: permissions change based on runtime context

### Governing Dynamic Capabilities (arXiv:2603.14332)
- Chain verifiability theorem: one unverifiable agent breaks end-to-end verification
- Bounded divergence: ε ≤ 1 - α^(1/n) for n agents in chain
- Implementations: Ed25519 + SHA-256 (97µs verify) or BBS+ ZK proofs (13.8ms verify)

### AGENTSAFE Framework (arXiv:2512.03180)
- Design controls → runtime controls → audit controls
- Semantic telemetry, dynamic authorization, anomaly detection, interruptibility, cryptographic tracing

---

## 7. Comparative Analysis

| Dimension | AWS Bedrock | Google Gemini | Microsoft AGT | IBM watsonx | SPIFFE | K8s RBAC |
|---|---|---|---|---|---|---|
| Identity format | agentId + ARN | SPIFFE URI | DID (did:mesh:) | Service principal | SPIFFE URI | ServiceAccount |
| Identity binding | IAM Role (separate) | IAM + Agent Identity | Ed25519 keypair | Entra ID | X.509 cert / JWT | JWT token |
| Authorization model | IAM policies + Cedar | IAM + Zanzibar ReBAC | YAML/OPA/Cedar policies | CUGA checkpoints | None (identity only) | RBAC rules |
| Grant structure | Effect/Action/Resource/Condition | Relationship tuples | Capabilities list + policy rules | Policy-as-code | N/A | apiGroups/resources/verbs |
| Trust scoring | None | None | 0-1000, 5 tiers, 5 dimensions, decay + contagion | Implicit | None | None |
| Human sponsor | None | None | Mandatory | Publisher (soft) | None | None |
| Versioning | DRAFT → numbered → aliases | Revisions | expires_at | Semantic version | TTL-based | Immutable objects |
| Ephemeral workloads | Via IAM session credentials | SPIFFE (auto-rotation) | expires_at field | N/A | Core design | Via token rotation |
| Delegation | Via IAM role chaining | Via Zanzibar tuples | parent_did + depth limit + trust ceiling | N/A | Via parent ID | Via bindings |
| Policy enforcement | IAM + Cedar + Guardrails | IAM + Zanzibar | 4-stage policy pipeline (fail-closed) | 5-checkpoint pipeline | N/A | Admission webhooks |

---

## 8. Key Patterns for Presidium

### Pattern 1: Separate Identity from Authorization (Universal)
Every system separates who you are from what you can do. Identity is an immutable fact. Authorization is a revocable grant.

### Pattern 2: Bindings Link Identity to Authorization (K8s, Zanzibar)
The cleanest systems have 3 objects: identity, permission definition, and a binding that links them. This enables: same permissions → multiple agents, multiple permissions → one agent, revoke binding without touching identity or permission definition.

### Pattern 3: Trust Scoring Influences Authorization (AGT)
Trust score determines what ring/tier an agent operates in. Low trust → sandbox. High trust → full access. Score changes dynamically based on behavior. This is the bridge between static grants and dynamic autonomy.

### Pattern 4: Human Sponsor for Accountability (AGT, Entra)
Every agent has a human owner. This enables: responsibility attribution, sponsor-initiated revocation, compliance (someone is accountable). Enterprise adoption likely requires this.

### Pattern 5: Ephemeral Credentials for Ephemeral Agents (SPIFFE)
Agents spawn and die. Credentials should be short-lived, auto-rotated, and expire naturally on crash. No persistent key storage, no cleanup on failure.

### Pattern 6: Delegation with Attenuation (AGT, Zanzibar, OAuth)
When agent A spawns agent B, B gets narrower permissions than A. Trust ceiling propagation (AGT), scope attenuation (OAuth), computed permissions (Zanzibar) all achieve this differently.

### Pattern 7: Fail-Closed Policy Evaluation (AGT)
If the policy engine errors during evaluation, the result is DENY, not ALLOW. This prevents attackers from crafting inputs that trigger exceptions to bypass policy.

### Pattern 8: Layered Enforcement (AWS, IBM)
Multiple enforcement points: org-level → agent-level → action-level. Most restrictive wins. AWS does this with guardrail layering. IBM does it with 5 structural checkpoints.
