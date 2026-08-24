# Vendor research: SPIFFE/SPIRE, 2026-08-24

**Status:** Research complete, feeds directly into `presidium-contrib[spiffe]`'s design pass.
**Why now:** `docs/design/agent-registry.md`/`presidium-server-requirements.md`/`presidium-server.md`
all name `presidium-contrib[spiffe]` (real SPIRE-issued X.509-SVIDs) as the "full" upgrade to the
P0 Ed25519 identity binding already shipped — but none of them were written against the SPIFFE
project's *current* real state. Every claim below is sourced directly (GitHub releases API,
PyPI, the SPIFFE project's own current docs), not carried over from memory or the original
design snapshot.

---

## 1. Where SPIFFE/SPIRE actually stands today

**SPIRE (the SPIFFE Runtime Environment) latest release: `v1.15.3`** (2026-08-21 — three days
before this research, actively maintained, not stale). CNCF graduated project. Go, Apache 2.0.

**Official Python SDK: [`spiffe`](https://pypi.org/project/spiffe/)** (part of the `py-spiffe`
library, `HewlettPackard/py-spiffe` on GitHub) — currently `0.3.1` on PyPI, Apache 2.0, requires
Python `>=3.10` (compatible with this org's `>=3.12` floor). Repo health checked directly: 22
GitHub stars (a real, honestly low adoption-signal number, worth stating plainly — this is a
narrower, more specialized library than AgentGateway's 4.5k), 3 open issues, pushed as recently
as 2026-08-17 — actively maintained despite the modest star count, and it's the community's own
recognized reference SDK (linked directly from spiffe.io's own docs), not an unofficial
third-party wrapper. Provides a real Workload API client (`X509Source`/`JwtSource`), automatic
SVID fetching and renewal over the standard SPIFFE Workload API (a Unix domain socket).

There is also an experimental `spiffe-tls` package (pyOpenSSL-based TLS listener/connection
helpers) — explicitly marked experimental by its own maintainers, not relied on here.

## 2. The real, load-bearing distinction, already correctly anticipated in this repo's own docs — confirmed, not re-derived

`docs/design/presidium-server-requirements.md` FR-3.2 already states the key architectural
boundary correctly, ahead of this research: **mTLS (already shipped, M7) and SPIFFE identity are
two separate concerns, not sequential steps of the same feature.**

- **mTLS (shipped)**: Civitas's own `civitas.gateway.mtls` — X.509 **subject-DN allowlist**
  based. Answers "is this HTTP request from a legitimate calling *service* at all?" Coarse,
  connection-level. Confirmed directly by reading `civitas/gateway/mtls.py`: it extracts and
  checks only the certificate's subject DN (`_dn_from_der()`) — it has no SPIFFE ID / SAN URI
  handling of any kind today.
- **SPIFFE (not built)**: answers "is this specific *agent* who it claims to be?" Fine-grained,
  per-agent, used for `AgentRecord`-level identity verification (what `presidium.identity
  .verify_agent_signature()` does today with a raw Ed25519 key) — not a replacement for the
  gateway's own TLS termination.

**Confirmed, real implication for the design**: this is genuinely a **third identity mechanism**
in this codebase, not a variant of the second. It doesn't touch `civitas/gateway/mtls.py` at all.

## 3. A real, concrete design tension the existing docs name but don't resolve

`AgentRecord.public_key` is documented and implemented today as a raw base64-encoded **Ed25519**
verify key — `presidium.identity.verify_agent_signature()` decodes it directly as an Ed25519
`VerifyKey` (`nacl.signing.VerifyKey`). A real SPIRE-issued X.509-SVID does **not** carry an
Ed25519 key by SPIRE's own default configuration — confirmed directly against SPIFFE's own
quickstart output: SPIRE's default key type is **EC P-256** (`NIST CURVE: P-256`, confirmed in a
real, current SVID example from spiffe.io's own docs). SPIRE *can* be configured for other key
types, but Ed25519 is not its default, and a real X.509-SVID additionally carries the SPIFFE ID
itself as a **Subject Alternative Name URI** (`URI:spiffe://example.org/myservice`), a whole
identity artifact `AgentRecord.public_key`'s bare-key field was never designed to hold.

**Concrete implication**: `presidium-contrib[spiffe]` cannot simply "populate `public_key` with a
SPIFFE key instead of an Ed25519 one" — verifying a real SVID means validating a full **X.509
certificate chain** against a trust bundle, checking certificate validity dates, and matching the
SAN URI against the agent's claimed `agent_id` — a materially different verification shape from
today's single Ed25519 signature check, not a drop-in swap.

## 4. Real, concrete design implications for the pass that follows this doc

1. **A new, separate verification path is needed, not a field-level swap.** The cleanest,
   lowest-risk shape: keep `presidium.identity.verify_agent_signature()` (Ed25519, the real,
   already-shipped default) completely unchanged, and add a new,
   `presidium_contrib.spiffe`-namespaced verifier for the X.509-SVID case — a real, additive
   capability, not a modification of existing, tested, shipped code. `AgentRegistry`
   implementations would need a pluggable verification strategy (today they call
   `verify_agent_signature()` directly) — this needs its own explicit decision in the design pass:
   likely a small `IdentityVerifier` Protocol, mirroring this session's own established
   Protocol-plus-adapter pattern (`ToolsGatewayBackend`/`GatewayToolProvider`), not a hardcoded
   Ed25519-only call site.
2. **Real testing needs a real, running SPIRE server + agent** — genuinely feasible on the
   homelab (a real Linux machine; SPIRE's own quickstart is Linux/macOS-friendly, pre-built
   binaries for Linux, well short of the setup complexity of, say, the Firecracker jailer work).
   This is a real, standard, well-documented process: `spire-server run`, a join token to attest
   `spire-agent`, a registration entry keyed on a real workload attestor (e.g. `unix:uid:<N>`),
   then fetching a real X.509-SVID over the Workload API. Matches this org's own "real hardware,
   not mocked" discipline for anything with a genuine hardware/infra dependency.
3. **SPIFFE ID format alignment, already correct, confirmed not to need a change**: this codebase's
   `presidium://{trust_domain}/{path}` URI scheme was already deliberately modeled on
   `spiffe://{trust_domain}/{path}`'s own structure (per `agent-registry.md`'s own D7 decision) —
   confirmed no rework needed there; a real SPIFFE ID would use the literal `spiffe://` scheme
   (SPIRE's own registration entries are always `spiffe://`), so the mapping is direct
   (`presidium://acme.com/prod/researcher` <-> `spiffe://acme.com/prod/researcher`), not a
   redesign.
4. **Auto-rotation is a real, structural difference from the current model.** Today's Ed25519
   keys are generated once and persisted (Civitas's own `AgentIdentity` machinery). Real SPIFFE
   SVIDs default to a short lifetime (SPIRE's own default is measured in hours, confirmed
   generally short-lived by design, exact default TTL configurable server-side) with automatic
   background renewal via the Workload API's streaming interface — a genuinely different
   lifecycle a `presidium-contrib[spiffe]` integration needs to actually hold open (a background
   watch/renewal task), not a one-shot fetch.
5. **Scope boundary, explicit**: this integration is about agent-level identity *verification*
   inside Presidium's own registry, not about replacing Civitas's gateway-level mTLS, and not
   about SPIFFE-izing inter-agent transport wholesale (a real, bigger, separate future direction
   `agent-registry.md` itself already named as "cross-deployment federation via trust domain
   bundles," explicitly out of scope for this pass).

## 5. Summary — what changes for the design pass because of this research

1. Confirmed: this is a real, separate, additive identity mechanism — not a modification of the
   already-shipped, already-tested Ed25519 path or the already-shipped M7 mTLS path.
2. A real design decision is needed on the verification-strategy shape (a pluggable
   `IdentityVerifier`-style Protocol vs. a hardcoded second call site) before implementation.
3. Real end-to-end testing is genuinely feasible on the homelab against a real SPIRE server +
   agent — not a "credentials-blocked, deferred" item like Fabrica's managed-sandbox adapters.
4. SPIRE's default key type (EC P-256) and SAN-URI-carrying SVID shape mean the real verification
   logic is X.509-chain-and-SAN based, not a bare public-key comparison — a genuinely different,
   slightly heavier implementation than the existing Ed25519 check.
5. Auto-rotation requires a real, held-open background renewal mechanism, not a one-shot key
   fetch — a real, new lifecycle concern for whatever object owns the Workload API connection.
