# Monetization Strategy

> How Civitas + Presidium can generate meaningful revenue.
> Based on analysis of Temporal, LangChain, CrewAI, Inngest, and Restate business models.

## The Proven Playbook: Open Core + Managed Cloud

Every successful company in agent infrastructure follows the same pattern:

```
Free OSS core → Developer adoption → Production pain → Paid managed service
```

### Comparable Company Revenue Data

| Company | What They Sell | Revenue | Valuation | Model |
|---|---|---|---|---|
| **Temporal** | Durable execution runtime | 380% YoY growth (est. $50M+ ARR) | $5B | OSS free → Temporal Cloud (usage-based) |
| **LangChain** | Agent framework + observability | $12-16M ARR (mid-2025) | $1.25B | OSS free → LangSmith (seat + traces) |
| **CrewAI** | Multi-agent orchestration | $3.2M ARR (mid-2025) | Undisclosed | OSS free → CrewAI Cloud (execution-based) |
| **Inngest** | Durable functions | Growing | $20M Series A | OSS free → managed cloud |
| **Restate** | Lightweight durable execution | Early | $7M seed | BSL OSS → Restate Cloud (usage-based) |

### Pricing Models in the Market

| Company | Pricing Axis | Free Tier | Paid Entry | Enterprise |
|---|---|---|---|---|
| LangChain (LangSmith) | Seat + usage | 5K traces/mo | $39/seat/mo | Custom |
| CrewAI Cloud | Execution (runs) | 100 runs/mo | $200/mo | $120K/yr |
| Temporal Cloud | Usage (actions) | — | Usage-based | Custom |

## Presidium Monetization Tiers

### Tier 1: Civitas + Presidium Community (Free, Apache 2.0)

The runtime + governance core. Everything needed to build governed agents locally.

**Goal:** GitHub stars, PyPI downloads, community. Revenue = $0. This is the adoption funnel.

### Tier 2: Presidium Cloud (Paid, managed)

Managed runtime + governance. No infrastructure to operate.

**Recommended pricing axis: Usage-based** (agent-hours + messages + policy evaluations)

| Tier | Price | Includes |
|---|---|---|
| **Free** | $0 | Self-hosted Civitas + Presidium Community |
| **Starter** | $49/mo | 10K agent-hours, 3 seats, basic dashboard |
| **Pro** | $299/mo | 100K agent-hours, unlimited seats, governance dashboard, compliance reports |
| **Enterprise** | Custom | Dedicated infra, SSO/SAML, SOC 2, SLA, on-prem option |

### Tier 3: Enterprise Add-ons

Premium features that only enterprises need:

| Feature | Why Enterprises Pay | Estimated Value |
|---|---|---|
| Compliance automation (EU AI Act, NIST, SOC 2) | Regulatory requirement | $$$$ |
| Audit trail & decision logging | Legal/compliance mandate | $$$ |
| SSO/SAML/RBAC | IT security requirement | $$ |
| Multi-region deployment | Data sovereignty | $$$ |
| SLA (99.9%+ uptime guarantee) | Production criticality | $$$ |
| Priority support | Reduces risk | $$ |
| Custom policy engine integration (OPA, Cedar) | Existing policy infra | $$ |

## Revenue Projections (Conservative)

| Year | Milestone | Est. ARR |
|---|---|---|
| Y1 | 1,000 GitHub stars, 50 Cloud users | $50K-$100K |
| Y2 | 5,000 stars, 300 Cloud users, first enterprise | $500K-$1M |
| Y3 | 15,000 stars, 1,000+ Cloud users, 5 enterprises | $2M-$5M |
| Y4 | Seed/Series A territory | $5M-$10M |

## Defensible Moats

### Weak Moats (don't rely on)
- Features (Microsoft can replicate with 70 engineers)
- First mover (Temporal, AGT exist)
- Price (race to bottom)

### Strong Moats (build these)
- **Integrated architecture** — governance baked into runtime (unique)
- **Developer experience** — `pip install presidium` → governed agent in 5 min
- **Community + ecosystem** — plugins, adapters, templates
- **Python-native** — one language done perfectly
- **Approachable codebase** — 10K LOC vs. 540K LOC AGT
- **OSS credibility** — Apache 2.0, no vendor lock-in
