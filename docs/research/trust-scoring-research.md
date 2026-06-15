# Trust Scoring & Adaptive Autonomy Research

> Comprehensive research for LearningTrustScorer requirements. Covers production reputation systems, AI governance frameworks, academic research, and open-source implementations.
>
> Status: Research complete. Requirements analysis pending.
> Last updated: 2026-06-14

---

## Production Trust Systems — Key Patterns

### eBay/Amazon Seller Reputation
- Seller trust weighted 30-40% of ranking with defect rate as hard gate
- Amazon AHR: 0-1000 scale, rolling 60-day window
- eBay shifted from subjective feedback to **administrative performance** (controllable signals)
- **Pattern**: Separate controllable from uncontrollable signals

### Uber/Lyft Driver Ratings
- Uber: average of last 500 rated trips (not all trips)
- Lyft: last 100 trips + assumes unrated = 5 stars (higher ratings)
- Bayesian averaging for cold start — new drivers pulled toward platform mean
- Notification thresholds trigger behavior change before deactivation
- **Pattern**: Windowed aggregation, Bayesian cold-start, graduated deactivation

### Stack Overflow Reputation
- Temporal weighting — votes at different times have different signal strength
- Forgetting factor (β=0.99/day) — old contributions decay
- Activity period — reputation only accumulates during active periods
- Ledger-based history for retroactive recalculation when rules change
- **Pattern**: Exponential decay, signal type weighting, retroactive recalculation

### FICO Credit Scoring
- Five weighted factors: payment history (35%), amounts owed (30%), length (15%), new credit (10%), mix (10%)
- FICO 10T: trajectory over 24+ months, not point-in-time snapshots
- Different scorecards for different profiles (thin file, mature, delinquent)
- Asymmetric penalty — high-trust agents penalized MORE for deviation
- **Pattern**: Behavioral trajectory, profile-specific weighting, asymmetric penalties

---

## AI Agent Trust Frameworks

### Microsoft AGT Trust Model
- 0-1000 scale, 5 tiers (verified_partner 900+, trusted 700+, standard 500+, probationary 300+, untrusted <300)
- 5 reward dimensions: policy compliance, anomaly detection, credential validity, behavior consistency, sponsor verification
- Decay without positive signals, resets to 500 after 30 days with no anomalies
- Tier floors prevent lockout from scheduled downtime

### OpenAI Preparedness Framework
- Risk category matrix (cybersecurity, CBRN, manipulation) — separate concerns
- Threshold-based gating: High = restricted deployment; Critical = pause/rollback
- External red team evaluations before deployment

### Anthropic RSP
- Capability-triggered evaluation — trust assessment depends on what agent CAN do
- Specification as auditable object — decompose into testable tenets
- Adversarial multi-turn evaluation

### NIST AI RMF
- 7 trustworthiness characteristics: valid/reliable, safe, secure/resilient, accountable/transparent, explainable, privacy-enhanced, fair
- Multi-characteristic assessment — don't reduce to single score
- Tradeoff documentation required

### EU AI Act
- Context-dependent risk classification — same agent may be high-risk in one domain
- Profiling as hard gate — if agent makes decisions about individuals, it's high-risk
- Fines up to €35M or 7% global turnover for misclassification

---

## Academic Research (2024-2026)

### Trust Architectures
- **A-Trust**: 6 orthogonal trust dimensions (truthfulness, completeness, relevance, manner, sincerity, reliability). Uses LLM attention patterns to detect violations.
- **DynaTrust**: Dynamic Trust Graph with Bayesian penalty + weighted jury consensus. 41.7% improvement over prior art.
- **Trust-Vulnerability Paradox**: Higher inter-agent trust improves coordination BUT increases over-exposure. Trust must be modeled as security variable.

### Reputation Systems for LLM Agents
- **AgentReputation**: 3-layer framework (execution → reputation services → tamper-proof persistence). Context-conditioned reputation cards.
- **TrustFlow**: Topic-aware vector reputation (multi-dimensional, not scalar). Sybil-resistant.
- **Ev-Trust**: Game-theoretic framework proving cooperative equilibria are stable when trust = survival advantage.
- **RepuNet**: Agent-level (direct interactions + gossip) + system-level (network evolution). Cooperative clusters emerge.

### Graduated Autonomy
- **Digital Apprentice**: Per-skill autonomy tiers (Pre-L0 → L0 → L1 → L2). Asymmetric demotion on quality degradation. Empirical evidence gates.
- **MI9 Runtime Governance**: Agency-Risk Index (autonomy 33%, adaptability 33%, continuity 33%). Graduated containment strategies.
- **Levels of Autonomy**: 5 user roles (operator → collaborator → consultant → approver → observer). Autonomy independent of capability.

---

## Open-Source Implementations

| System | Architecture | Key Innovation |
|---|---|---|
| HiveTrust | 5 behavioral pillars, 5 tiers | Weighted: 35% success rate, 25% capital, 15% centrality, 15% identity, 10% compliance |
| AgentTrust (MCP) | Bayesian Beta distribution | 90-day exponential decay, 5 score types, dispute penalties |
| Fulcrum-Trust | Beta(α,β) trust engine | Circuit breaking, LangGraph integration, Redis IPC |
| TrustMesh | Bayesian Beta-Binomial | Time-weighted, portable scores, A2A-native |
| TRUCE (TATF) | Open standard | Relative scoring (vs. agent baseline), anomaly detection |
| Agent Rating Protocol v2 | 5-dimension rating | Bilateral blind protocol, anti-Goodhart metric rotation |
| AAIF Reputation Network | Foundational protocol | R = (C × T × RAP × PV) / VP formula |

---

## Feedback Loops & Decision Journals

### RLHF Pattern
- Pairwise comparisons more reliable than absolute ratings
- KL divergence penalty prevents policy drift from baseline
- Process Reward Models evaluate intermediate steps (better for reasoning agents)
- Iterative: collect data → train reward model → optimize policy → repeat

### Active Learning Pattern
- Query where model is most uncertain (not random)
- Calculate information gain vs annotation cost
- Self-label where confident, ask human for hard cases
- Adaptive feedback format (ranking vs classification vs correction)

### Contextual Bandits Pattern
- Thompson Sampling: maintain posterior, sample to balance explore/exploit
- UCB: select arm with highest upper confidence bound
- Trust-aware exploration: don't explore actions that violate trust
- Context-specific trust boundaries

### Cold-Start Solutions
- Empirical Bayes: pull toward platform mean (72% MSE reduction with ≤10 reviews)
- Feature-based transfer: similar agents inherit some trust
- LLM pseudo-observations: predict counterfactual rewards, decay weight as real data arrives
- Strategic promotion: allocate exploration budget to new agents

---

## 10 Universal Patterns Across All Systems

1. **Multi-dimensional assessment** — never collapse to single number
2. **Temporal dynamics** — decay without positive signals; recent behavior matters more
3. **Windowed aggregation** — last N transactions, not all-time
4. **Controllability filter** — penalize only what agent controls
5. **Tier-based capability gating** — trust score maps directly to allowed actions
6. **Feedback loops** — measure whether system drives behavior change
7. **Specification as auditable object** — write testable claims
8. **Cold-start mechanism** — bootstrap trust for new agents
9. **Reversibility** — restrictions should be reversible
10. **Transparency** — agents understand why score changed

---

## What Presidium Has Today vs. What's Needed

| Pattern | M2 (Shipped) | Gap |
|---|---|---|
| Multi-dimensional | ❌ Single scalar (0.0-1.0) | Need per-dimension scores |
| Temporal dynamics | ✅ Lazy decay (-0.01/hr) | Configurable decay schedules |
| Windowed aggregation | ❌ All-time aggregation | Need rolling windows |
| Controllability filter | ❌ All events weighted equally | Need signal classification |
| Tier-based gating | ✅ 3 tiers via CEL conditions | Extend to per-action tiers |
| Feedback loops | ❌ No behavioral response tracking | Need improvement measurement |
| Specification | ❌ Implicit in code | Need explicit trust spec per domain |
| Cold-start | ❌ Fixed 0.5 for everyone | Need Bayesian priors, sponsor transfer |
| Reversibility | ✅ set_value() for overrides | Need graduated deactivation |
| Transparency | ❌ No explainability | Need signal attribution |

---

## Sources

- eBay Cassini Algorithm (super-ds.com)
- Amazon AHR (aboutamazon.com)
- Uber/Lyft ratings (uber.com, quora.com, arxiv.org)
- Stack Overflow reputation (tudelft.nl, arxiv.org)
- FICO 10T (creditpur.com, myfico.com)
- Microsoft AGT (github.com/microsoft, techcommunity.microsoft.com)
- OpenAI Preparedness (deploymentsafety.openai.com)
- Anthropic RSP (anthropic.com)
- NIST AI RMF (nvlpubs.nist.gov)
- EU AI Act (digital-strategy.ec.europa.eu)
- A-Trust (arxiv.org/2506.02546)
- DynaTrust (arxiv.org/2603.15661)
- Trust-Vulnerability Paradox (arxiv.org/2510.18563)
- AgentReputation (arxiv.org/2605.00073)
- TrustFlow (arxiv.org/2603.19452)
- Ev-Trust (arxiv.org/2512.16167)
- Digital Apprentice (arxiv.org/2606.04321)
- MI9 (arxiv.org/2508.03858)
- Seven Security Challenges (nature.com/s44387-026-00128-9)
- RLHF (rlhfbook.com)
