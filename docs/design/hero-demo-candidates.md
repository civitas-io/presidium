# Hero Demo Candidates

> Evaluating demo concepts for civitas-io. Targeting OSS developers, platform engineers, enterprise buyers, and AI/ML engineers. Must showcase Civitas runtime + Presidium governance together.
>
> Status: Ideation phase. No implementation decisions made.
> Last updated: 2026-06-14

---

## Candidate A: Praetor — SRE Incident Response Co-Pilot

Multi-agent triage→diagnose→propose→execute pipeline against synthetic production alerts.

**Topology:** AlertIngestor → DynamicSupervisor spawns IncidentHandler per alert → TriageAgent → parallel DiagnosticSupervisor (logs, metrics, traces) → RemediationProposer → ExecutionAgent (gated). ApprovalRouter, TrustObserver, AuditCollector as permanent agents.

**Wow moment:** Human approval rate drops from 100% to ~12% over compressed 5-minute timeline as agents earn trust on recurring alert patterns. Poisoned alert (`DROP TABLE users`) blocked by policy engine.

**Strengths:**
- Universal pain (everyone hates being paged)
- Governance has existential teeth (data loss vs safety)
- Trust progression visible in real time
- Fault tolerance demo (kill agent mid-run → supervisor restarts)
- Covers all Civitas + Presidium features naturally

**Weaknesses:**
- Needs quality synthetic alert data to feel real
- Dashboard is ~30% of effort
- More SRE/platform-eng than enterprise buyer

**Buyer:** VP Engineering / Director SRE
**Budget line:** Observability / incident management (PagerDuty, Opsgenie)
**Audiences:** Strong for OSS devs + platform engineers. Moderate for enterprise.
**Effort:** ~5-7 days

---

## Candidate B: Quaestor — Vendor Onboarding & Spend Control ⭐

Multi-agent system triages vendor requests, runs security/financial/sanctions diligence, drafts contracts, and routes for approval with risk-tiered autonomy.

**Topology:** IntakeAgent → SecurityReviewAgent → FinancialHealthAgent → SanctionsScreener → ContractAnalyzer → ApprovalRouter. DynamicSupervisor spawns per-vendor review pipeline.

**Wow moment:** Agent auto-approves $3K office supplies vendor in seconds (earned trust on low-risk category). Same agent blocks "AcmeAI" vendor requesting prod data access — policy requires CISO grant regardless of trust. Shadow-AI vendor with full data access auto-approved in OFF mode → breach scenario.

**Strengths:**
- Universal buyer (every company has procurement, CPO signs the MSA)
- Shadow-AI panic is the 2026-2027 zeitgeist ("what AI vendors have our data?")
- Earned autonomy demos beautifully: categories naturally tier (office supplies → SaaS → AI/data tools)
- Multi-agent is obvious: security, financial, sanctions, contract — clearly different specializations
- Cheapest to mock: vendor intake form, fake D&B lookup, public OFAC SDN list, mock approval Slack

**Weaknesses:**
- Less technically exciting for OSS developer audience
- Procurement workflows vary significantly across companies

**Buyer:** CPO (Chief Procurement Officer), co-signed by CFO + CISO
**Budget line:** P2P/S2P platform (Coupa, Ariba, Zip) + Third-Party Risk Management (OneTrust, ProcessUnity)
**Horror story (OFF):** Agent auto-approves shadow AI vendor with prod data access → breach. Or autopays $80K phishing invoice spoofing real supplier (BEC fraud, $2.9B losses 2023 per FBI IC3).
**Regulations:** SOX 404, OFAC sanctions, GDPR Art. 28 (processor DPAs), DORA Art. 28 (EU financial)
**vs. Today:** 6-week vendor approval cycle, 8 procurement analysts ($110K each), Coupa + OneTrust + manual email ping-pong
**Deal size:** Mid-market to Enterprise: $150K-$750K ARR. Broadest TAM of any concept.
**Effort:** ~5-7 days

---

## Candidate C: Lictor — Trade Surveillance Co-Pilot

Multi-agent system monitors trader comms + order flow, drafts SAR filings, and auto-closes false-positive alerts after earning trust.

**Topology:** CommsIngestionAgent → PatternDetectionAgent → TriageClassifier → SARDraftAgent → FilingApprovalRouter. TrustObserver tracks per-analyst-type performance.

**Wow moment:** 98%+ of surveillance alerts are false positives today. Agent earns trust to auto-close cafeteria/HR chatter false positives but NEVER auto-files a SAR. Show OFF: spurious SAR filing → FINRA inquiry. Show ON: precision-filtered queue with audit trail.

**Strengths:**
- Highest deal sizes ($750K-$3M ARR)
- Most defensible against "ChatGPT can do this" (audit trail IS the product)
- Strongest regulatory teeth (FINRA fines are existential: JPM $200M spoofing fine)
- FS buyers respond to peers — one credible demo unlocks the vertical

**Weaknesses:**
- Narrow audience (financial services only)
- Niche mocks needed (Bloomberg chat format, OMS trade tape, SAR portal)
- Compliance domain expertise needed to be credible

**Buyer:** Chief Compliance Officer (CCO) or Head of Surveillance
**Budget line:** RegTech / Surveillance Technology (NICE Actimize, Nasdaq SMARTS, Behavox replacement)
**Horror story (OFF):** Auto-files spurious SAR → FINRA inquiry + relationship damage. Or misses front-running pattern → $50M+ fine.
**Regulations:** FINRA 3110, SEC 17a-4, MAR (EU), MiFID II Art. 16, FINRA Reg Notice 24-09 (AI in compliance)
**vs. Today:** ~200 surveillance analysts at $150K reviewing alerts where 98%+ are false positives. Bloomberg surveillance ($2K/seat) + Actimize installs $2M+.
**Deal size:** Enterprise: $750K-$3M ARR
**Effort:** ~7-10 days (domain complexity)

---

## Candidate D: Curator — Prior Authorization & Clinical Documentation

Multi-agent system extracts clinical data from charts, matches against payer criteria, drafts PA requests and appeals, with earned autonomy per condition category.

**Topology:** ChartExtractorAgent → CriteriaMatcherAgent → PayerRuleEngine → AppealDrafterAgent → ClinicianReviewRouter.

**Wow moment:** Diabetes med refill auto-approved in seconds (high trust, routine). Oncology case always routes to board-certified physician reviewer regardless of trust score — policy hardcodes it. Show OFF: auto-denies cancer treatment meeting NCCN guidelines → patient harm + regulatory investigation.

**Strengths:**
- Highest ceiling deal sizes ($1M-$5M ARR)
- Regulatory forcing function: CMS-0057-F mandates 72hr urgent / 7-day standard from 2026
- Patient impact stories are visceral
- Enormous market ($30B+ prior auth / revenue cycle)

**Weaknesses:**
- Healthcare demos need domain credibility — non-clinician audiences may not feel the pain
- HIPAA compliance adds real complexity even for demos
- Mock FHIR endpoints and clinical criteria need domain expertise

**Buyer:** (Payer) CMO + VP Utilization Management. (Provider) VP Revenue Cycle + CFO
**Budget line:** UM platform / RCM automation (Cohere Health, Olive AI space)
**Horror story (OFF):** Auto-denies oncology case meeting NCCN guidelines → state insurance commissioner investigation + viral patient story (cf. Cigna PXDX lawsuit, 2023). Or PHI leak across patient records → HIPAA penalty.
**Regulations:** HIPAA, HITECH, CMS-0057-F (Interoperability & Prior Auth Final Rule, 2026-2027), state PA reform laws
**vs. Today:** Nurse reviewers ($85K) at $1.50-$3/PA, 5-15 day turnaround
**Deal size:** Enterprise: $1M-$5M ARR
**Effort:** ~10+ days (domain-heavy)

---

## Candidate E: Vigil — SOC Tier-1 Alert Triage

Multi-agent system triages SIEM alerts, performs IOC enrichment, executes containment playbooks, and escalates Tier-2-worthy incidents with privileged-action governance.

**Topology:** AlertIntakeAgent → EnrichmentAgent (threat intel) → ContainmentAgent → CommsAgent → EscalationRouter.

**Wow moment:** Containment agent quarantines compromised dev endpoint autonomously (earned trust). Production/executive endpoints always require HITL. CEL condition: `resource.criticality != "executive"`. Show OFF: isolates CEO laptop mid-board-meeting. Show ON: asks for approval first.

**Strengths:**
- Hot market (CISO budgets growing, SOC analyst shortage acute)
- Clear tiered autonomy: dev VLAN vs production vs executive
- SEC Cyber Disclosure Rule (4-day 8-K) creates regulatory urgency
- CISO is a powerful internal buyer

**Weaknesses:**
- Adjacent to Praetor (SRE) — may feel redundant in same demo deck
- SIEM mock data needs to look credible (Splunk/Sentinel format)

**Buyer:** CISO + Director of Security Operations
**Budget line:** MDR/MSSP (Arctic Wolf, Expel, Red Canary) + SOAR (Splunk SOAR, Tines)
**Horror story (OFF):** Fails to contain ransomware → 4-day SEC reporting clock missed → material disclosure + shareholder lawsuit. Or posts incident details to wrong Slack channel → public disclosure.
**Regulations:** SEC Cyber Disclosure Rule (4-day 8-K), NIS2 (EU), DORA, NYDFS Part 500
**vs. Today:** $200K-$500K/yr MDR contracts; in-house SOC analysts at $130K with 80% false-positive fatigue
**Deal size:** Mid-market to Enterprise: $250K-$1.5M ARR
**Effort:** ~5-7 days

---

## Candidate F: Censor — M&A Contract Diligence

Multi-agent system reviews target company contracts during due diligence, flags change-of-control / IP / liability risks, generates risk-scored disclosure schedules.

**Topology:** DocumentClassifier → ClauseExtractor → RiskScorer → ComparisonAgent (vs. precedent) → ScheduleDrafter.

**Wow moment:** Boilerplate jurisdiction clauses auto-tagged (earned trust after 1K examples). Change-of-control and IP assignment clauses always require partner sign-off — missing one could cost $XX0M in EV miscalculation.

**Strengths:**
- Very high per-deal value ($50K-$200K per deal, or $300K-$1.5M ARR)
- Audit trail = privilege log evidence (governance IS the legal requirement)

**Weaknesses:**
- Episodic spend (deal-driven, not recurring)
- Legal industry slow to buy
- Needs convincing document corpus to demo

**Buyer:** General Counsel + Head of Corporate Development; or PE firm Operating Partner
**Budget line:** Legal tech (Kira, Luminance, Harvey) + outside counsel substitution
**vs. Today:** BigLaw at $1,200-$1,800/hr, 12-week diligence, $2M+ per deal
**Deal size:** $300K-$1.5M ARR or $50K-$200K per deal
**Effort:** ~7-10 days

---

## Comparison Matrix

| Candidate | Buyer Reach | Demo Drama | Regulatory Teeth | Deal Size | 1-Week Build | 2027-Proof |
|---|---|---|---|---|---|---|
| **A. Praetor** (SRE) | ★★★★ engineers | ★★★★ data loss | ★★ weak | $150-500K | ★★★★★ | ★★★★ |
| **B. Quaestor** (Procurement) ⭐ | ★★★★★ universal | ★★★★ fraud + shadow AI | ★★★ SOX/OFAC | $150-750K | ★★★★★ | ★★★★★ |
| **C. Lictor** (Trade Surv.) | ★★ FS only | ★★★★★ FINRA fines | ★★★★★ FINRA/MAR | $750K-3M | ★★★ niche | ★★★★ |
| **D. Curator** (Prior Auth) | ★★★ healthcare | ★★★★★ patient harm | ★★★★★ CMS-0057-F | $1-5M | ★★ domain-heavy | ★★★★★ |
| **E. Vigil** (SOC) | ★★★★ CISOs | ★★★★ CEO laptop | ★★★★ SEC 4-day | $250K-1.5M | ★★★★ | ★★★★ |
| **F. Censor** (M&A) | ★★ legal/PE | ★★★★ deal-killer | ★★★ UPL rules | $300K-1.5M | ★★★ corpus | ★★★ |

## Notes

- **Quaestor (B)** is the strongest hero demo for broad enterprise reach — every company has procurement, shadow-AI is the hot topic, and it's the cheapest to mock.
- **Lictor (C)** is the vertical-specific "we're serious about regulated industries" demo — highest deal sizes, strongest regulatory story.
- **Praetor (A)** remains the best for OSS developer + platform engineer audiences.
- A two-demo strategy (Quaestor for enterprise sales + Praetor for developer adoption) covers all audiences.
- **Curator (D)** has the highest ceiling but needs domain investment to be credible.
- **Censor (F)** is lowest priority — episodic spend, slow buyers.

## Evaluation Criteria (Enterprise)

1. Does it showcase earned autonomy (HITL → autonomous progression)?
2. Does it demonstrate governance ON vs OFF with clear business impact?
3. Does it resonate with enterprise buyers who sign contracts?
4. Is the use case something companies are actively budgeting for?
5. Is it buildable in ~1 week with mock services?
6. Will it still be compelling in mid-2027?
7. Can it serve as a conference talk / blog post / README hero example?

---
---

# OSS Community Demos

> Free, useful tools meant to drive adoption and start conversations on HN, Reddit, Twitter/X.
> Goal: get developers to `pip install civitas presidium` and actually USE it.
> Key rule: position as standalone tools that *happen to* run on Civitas/Presidium. Governance should be discovered, not announced.

---

## Candidate G: CodeGuard — Seatbelts for AI Coding Agents

**HN title:** *"I gave Claude Code root and didn't lose my homedir (open-source guardrails for AI coding agents)"*

A sidecar that wraps any coding agent (Cursor, Claude Code, Aider, OpenCode, Codex CLI, Gemini CLI) and intercepts shell exec, filesystem writes, and network calls. CEL policies declare what's allowed: no `rm -rf` outside `/tmp`, no `curl | bash`, no `git push --force` to main, no writes to `~/.ssh`. New agents start with trust score 0.2 and earn capabilities through successful operations. HITL prompts for anything risky.

**Why devs use it:** Everyone has the YOLO agent horror story — Cursor that `rm -rf`'d the wrong directory, Aider that pushed to main, an agent that `npm install`'d a malicious package. This is the seatbelt people want but nobody built well.

**Governance angle:** Pre-execution policy is the killer feature — agents *can't* do the dangerous thing even if prompt-injected. Trust scoring means you don't manually approve every `ls`, just the scary stuff. Audit log = "what did the agent actually do today."

**Show, don't tell:** Side-by-side terminal. Left: unsupervised agent given a prompt-injected README, runs malicious bash. Right: same agent, CodeGuard intercepts with `BLOCKED: curl | bash matches policy denylist`, trust drops to 0.05, forensic audit entry written.

**Local model:** N/A — works as governance layer for any agent regardless of model. Works with Claude, GPT, AND local Ollama agents.

**Effort:** 1.5-2 weeks (shell interception via PTY wrapping is the hard part)

---

## Candidate H: AgentOps — htop for AI Agents

**HN title:** *"htop, but for AI agents — real-time visibility into autonomous systems"*

A Textual TUI that attaches to any Civitas runtime and shows every running agent in real-time: SPIFFE identity, trust score, current tool call, message flow between agents, token spend, time-in-state. Hotkeys: suspend, kill, force HITL on next action, dump decision history. Like Erlang Observer or k9s, but for agents.

**Why devs use it:** Multi-agent systems are currently impossible to debug. People stitch together LangSmith traces and CloudWatch logs. A beautiful, instant, local TUI is what you actually want at 2am when an agent loop is burning $40/hr.

**Governance angle:** Identity is the unlock — every agent has a cryptographic SPIFFE URI, not an opaque uuid. Trust scores visible as live gauges (red = recently policy-denied). Kill switches use Presidium's revocation. The "force HITL" hotkey is governance-as-debugging.

**Show, don't tell:** Screen recording: 12 agents in a supervisor tree (left), live message bus (center), trust-score gauges with one decaying as it fails post-execution checks (right). User presses `k`, supervisor respawns with reset trust. Cinematic.

**Local model:** 100% runtime-agnostic.

**Effort:** 1-1.5 weeks (Textual makes this fast)

---

## Candidate I: AgentTrap — I Left an Agent on the Internet

**HN title:** *"I left a vulnerable AI agent on the public internet for a week. Here's the attempted-hijack log."*

A deliberately-exposed agent (web scraper, RSS summarizer — something that consumes adversarial input) deployed publicly with full forensic logging. Then a comparison run with Presidium policies enabled. Output is BOTH a reproducible repo AND a research blog post documenting every real-world prompt injection / tool-call hijack / data exfiltration attempt observed.

**Why devs use it:** The blog post is the lead magnet. The repo gives them a forensics framework to deploy themselves. This becomes the canonical reference for "is prompt injection real?" debates.

**Governance angle:** Trust-score decay is the star — every successful injection attempt drops the source's trust. Agent stops trusting that source's inputs. Audit enrichment means every blocked attack has a full trace: what the attacker tried, what the agent would have done, what policy denied it.

**Show, don't tell:** Chart in the blog: "23 hijack attempts in 7 days. Without Presidium: 19 succeeded. With Presidium: 0 succeeded, 23 logged, average attacker trust score: 0.02."

**Local model:** Yes — run the honeypot on Qwen/Llama 4. MORE compelling that way ("a 7B model didn't get pwned because of governance, not intelligence").

**Effort:** 1 week build + 1 week running for content

---

## Candidate J: Padlock — Docker for MCP Servers

**HN title:** *"Docker for MCP servers — safely run that random GitHub MCP without trusting it"*

A wrapper that runs any MCP server in a capability-sandboxed environment. Declare what the server SHOULD be able to do (filesystem read on `~/projects`, network to `api.github.com`, no shell). Presidium enforces at the boundary. Each MCP server gets its own SPIFFE identity, trust score, and audit log. Drop-in: `padlock run npx @some/mcp-server` instead of `npx @some/mcp-server`.

**Why devs use it:** The MCP ecosystem is exploding and nobody is auditing these servers. Installing a random MCP server today is `curl | bash` energy. This is the safety net for trying new MCPs without paranoia.

**Governance angle:** Capability declaration is the differentiator — most sandboxes are all-or-nothing. Presidium policies let you say "this MCP can read `~/Documents` but cannot read `~/Documents/taxes`." Trust scores let dodgy MCPs lose access over time. Audit log = "what did the GitHub MCP actually do this week?"

**Show, don't tell:** Install a deliberately-malicious MCP server. Unsandboxed: reads `~/.aws/credentials` and exfiltrates. Padlock: policy denies, trust → 0, server quarantined, audit log shows attempted exfiltration with exact payload. Then: "Here's how to write a Padlock policy in 4 lines of CEL."

**Local model:** Runtime-agnostic. Works for any MCP client (Claude Desktop, Cursor, Continue, etc.).

**Effort:** 1.5-2 weeks (process isolation is hard — start with Linux namespaces / macOS sandbox-exec)

---

## Candidate K: AgentWolf — Local LLMs Play Werewolf

**HN title:** *"I made 8 local LLMs play Werewolf and watched them invent deception"*

Multi-agent social deduction game. 8 Ollama-powered agents play Werewolf/Mafia. Each agent has a real SPIFFE identity (cheating provably impossible — you can prove who said what). Audit logs reveal post-game "who knew what when." Watch emergent lying, coalition-building, and trust dynamics. Run tournaments between model families.

**Why devs use it:** Pure curiosity + entertainment + benchmark. People will run this just to see if Qwen-72B can out-lie Llama-4. Also a legitimate multi-agent testbed — more interesting than yet another RAG demo. Educators use it to teach multi-agent concepts.

**Governance angle:** Identity becomes a game mechanic. Trust scoring becomes meta (which model is the most "trustworthy" liar?). Audit replay shows Agent #4 tried to send a private message to the wrong channel — supervision tree caught it. Governance features feel natural because the game NEEDS them.

**Show, don't tell:** 90-second video: 8 agent portraits with live chat, voting phase, a werewolf accusing an innocent, the village voting wrong, post-game reveal showing werewolves' private coordination. Tweetable.

**Local model:** PRIMARY use case. Fully Ollama. Mix Qwen, Llama, DeepSeek, Phi in one game.

**Effort:** ~1 week (game logic is straightforward, magic is presentation)

---

## Candidate L: Provenance — Cite-or-Die Research Agent

**HN title:** *"Local Deep Research that physically can't hallucinate citations"*

Multi-agent research pipeline: planner → searchers → synthesizer → critic. Presidium POST_LLM policy: every factual claim MUST link to a source the agent actually fetched, with content hash verified. If the synthesizer outputs an unsourced claim, the policy rejects it and forces a re-write. Audit log is a full provenance graph: claim → quote → URL → fetch timestamp → content hash.

**Why devs use it:** Local alternative to OpenAI Deep Research / Perplexity Pro that solves the actual problem — trustworthy citations. Journalists, researchers, anyone doing due diligence has been burned by hallucinated URLs.

**Governance angle:** Post-execution policy is the differentiator most agent frameworks don't have. Hallucination becomes architecturally impossible, not "hopefully won't happen." Audit enrichment IS the deliverable — user gets the provenance graph as output.

**Show, don't tell:** Research question → final report where every sentence is highlightable, hover shows exact source paragraph + content hash. Then: same question, governance disabled — 3 hallucinated citations marked red after manual verification.

**Local model:** Yes — Qwen for synthesis, smaller models for search/critic. SearXNG for free search.

**Effort:** ~2 weeks (claim→source matching is the substantive engineering)

---

## OSS Comparison Matrix

| Candidate | Virality | Utility | Governance Showcase | Local Model | Build Time | HN Appeal |
|---|---|---|---|---|---|---|
| **G. CodeGuard** | ★★★★ | ★★★★★ daily use | ★★★★★ pre-exec policy | ★★★★★ any agent | 1.5-2wk | ★★★★★ |
| **H. AgentOps** | ★★★★ | ★★★★★ debugging | ★★★★ identity + trust | ★★★★★ agnostic | 1-1.5wk | ★★★★★ |
| **I. AgentTrap** | ★★★★★ blog post | ★★★ research | ★★★★★ forensics | ★★★★★ 7B model | 1+1wk | ★★★★★ |
| **J. Padlock** | ★★★★ MCP wave | ★★★★★ daily use | ★★★★★ capability sandbox | ★★★★★ any client | 1.5-2wk | ★★★★ |
| **K. AgentWolf** | ★★★★★ viral | ★★★ entertainment | ★★★ identity + audit | ★★★★★ Ollama | ~1wk | ★★★★★ |
| **L. Provenance** | ★★★★ | ★★★★★ real tool | ★★★★★ post-exec policy | ★★★★ needs capable model | ~2wk | ★★★★ |

## OSS Ship Order (Recommended)

| Order | Concept | Why |
|---|---|---|
| **#1** | **AgentWolf (K)** | Lowest effort, highest virality. Gets people installing for FUN — trojan horse for the stack |
| **#2** | **AgentOps (H)** | Beautiful demos sell themselves. Everyone with agents wants this |
| **#3** | **CodeGuard (G)** | The "seatbelt I needed" moment. Biggest organic growth potential |
| **#4** | **AgentTrap (I)** | Best for starting conversations. Blog post is the asset, repo is the proof |
| **#5** | **Padlock (J)** | Rides the MCP wave. Useful timing as ecosystem matures |
| **#6** | **Provenance (L)** | Highest effort, but quietly the most important. Ships when you can do it right |

## Key Positioning Rule

> Don't position any of these as "Presidium demos." Position them as standalone tools that *happen to* run on Civitas/Presidium. The governance angle should be discovered, not announced. README opens with user value, not the framework. HN rejects framework-first projects ruthlessly.
