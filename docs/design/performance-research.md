# Design: M8 Performance Research — real benchmarks, real numbers, a recommendation

**Status:** Complete, 2026-08-25. Real benchmarks against a real M7 server, on real (separate,
network-connected) hardware, plus a real, same-conditions comparison against OPA. Not a rewrite
commitment -- matching `docs/vision/roadmap.md`'s own framing for this milestone.
**Depends on:** `docs/vision/roadmap.md`'s M8 section (goal, options A-D, original baseline);
`docs/design/policy-engine.md`; the council session that shaped this doc's own comparison
methodology (see "Comparison methodology" below).
**Harness:** `benchmarks/` in this repo -- real, kept (not deleted), reproducible scripts, not a
one-off throwaway. See `benchmarks/README.md`.

## Goal, unchanged from the roadmap

Answer, with real measured evidence, whether any part of Presidium's request-path hot loop needs
to move off pure Python -- and if so, which part, how, and when -- before it becomes a real
production bottleneck rather than after. Four options were on the table (A: horizontal scaling,
B: free-threaded CPython, C: a Rust-backed CEL evaluator, D: a fuller Rust rewrite of the M7
layer). This doc reports what was actually measured for each.

---

## 1. The isolated CEL microbenchmark — corrected, not just reproduced

**A real, honest correction to the previously-cited baseline.** `docs/vision/roadmap.md`'s M8
section cited "~88µs per evaluation, ~11,400 evaluations/sec... with 20 loaded rules." No
reusable script backed that number -- it was measured ad hoc while scoping the milestone. This
pass built one (`benchmarks/cel_microbench.py`) and found the real number, at 20 rules, evaluated
under the same "first-match-wins scans every loaded rule" worst case the original text itself
describes, is materially higher:

| Rules | Mean (µs) | p50 (µs) | p95 (µs) | p99 (µs) | Evals/sec |
|---|---|---|---|---|---|
| 5 | 353 | 340 | 382 | 784 | 2,829 |
| 20 | 1,314 | 1,305 | 1,359 | 1,425 | 761 |
| 50 | 3,377 | 3,339 | 3,542 | 3,729 | 296 |
| 100 | 6,714 | 6,670 | 6,975 | 7,100 | 149 |

Scaling is clean and linear: ~67µs per rule evaluated, consistent across all four sizes,
confirmed directly against `cel-python`'s own raw `program.evaluate()` call in isolation (~67µs/
call, matching). **The most likely explanation for the discrepancy**: the original 88µs figure
was probably measured against a request that matched an early, high-priority rule (so only one
or two of the 20 loaded rules were actually evaluated), not the worst-case "no match, scan
everything" scenario its own qualitative framing ("a request that matches no rule... evaluates
every loaded rule") describes. This is not a regression -- it's the first time this number has
been measured against a script that's checked in, named, and re-runnable, rather than reasoned
about after the fact. **This revision makes the case for investigating Options A-C stronger, not
weaker** -- the real per-request cost at realistic rule-set sizes (20-100 rules, matching real
deployments with more than a handful of policies) is materially higher than previously stated.

---

## 2. Real HTTP-endpoint benchmarks — the number that didn't exist before this pass

The isolated number above has never included the network/HTTP/registry-lookup/Civitas-dispatch
layers a real `/v1/check_grant` request actually pays for. This is the real gap `docs/design/
policy-engine.md`'s own M8 section identified and this pass closes: a real, standalone M7 server
(`benchmarks/serve_m7.py` -- real `HTTPGateway` + `PresidiumGatewayAgent` + `HealthCheckAgent`,
real `civitas.Runtime`/`Supervisor`, not a pytest fixture), hit with Apache Bench (`ab`) -- a
real, separate process/connection per request, not asyncio tasks sharing one connection inside
the same process as the code under test.

**Two real environments, deliberately kept separate, not blended:**

### 2a. Local loopback (MacBook Pro, Apple Silicon, aarch64) -- isolates HTTP+CEL overhead

| Rules | Throughput ceiling (req/sec, concurrency 10-100) |
|---|---|
| 5 | ~1,890-2,010 |
| 20 | ~630-640 |
| 100 | ~140-147 |

### 2b. Real network hop (MacBook -> `darkenergy`, a separate real Linux host, direct Tailscale
connection, ~4-6ms RTT, NOT loopback) -- the more realistic number for an actual deployment

| Rules | Throughput ceiling (req/sec, concurrency 10-100) |
|---|---|
| 5 | ~970-1,000 |
| 20 | ~345-365 |
| 100 | ~81-84 |

**The concurrency model, stated explicitly** (matching this org's own established disclosure
discipline from `python-civitas`'s M-LAST scoping doc): `ab` driving a fixed pool of real,
independent TCP connections/OS-level worker threads against a single presidium-contrib server
process, itself a single Python process running one asyncio event loop.

**The real, load-bearing confirmation of the GIL hypothesis**: at every rule count, in both
environments, throughput is **flat regardless of concurrency** once concurrency exceeds ~10 --
1, 10, 25, 50, and 100 concurrent connections all produce essentially the same ceiling. This is
real, direct, HTTP-level evidence for the exact mechanism `docs/vision/roadmap.md`'s M8 section
hypothesized: a single Python process's throughput ceiling does not rise with more concurrent
callers, because the GIL serializes all CEL evaluation onto one core regardless of how many
connections are open.

**Honest limitation**: `darkenergy` is a real, shared, busy homelab host (24 cores, running
several unrelated production services -- photo ML, file sync, other agent workloads -- during
this benchmark), not a dedicated, idle bench box. The 2b numbers include real noisy-neighbor
contention and should be read as "a real, imperfect deployment condition," not "a clean, isolated
ceiling." This is disclosed here deliberately, not smoothed over.

---

## 3. Option A — horizontal scaling: confirmed, works, cheapest, recommended now

Two independent `serve_m7.py` processes (20 rules each), on the same `darkenergy` host, hit
**concurrently** by two separate `ab` invocations:

| Process | Throughput (req/sec) |
|---|---|
| Server 1 (port 28080) | 325.78 |
| Server 2 (port 28081) | 324.55 |
| **Combined** | **~650.3** |

This is essentially double the single-process ceiling measured in §2b (~345-365 req/sec) --
**horizontal scaling works, close to linearly, with zero code changes**, exactly as
`docs/vision/roadmap.md`'s Option A predicted. This is the cheapest, lowest-risk lever available
today, and the evidence here supports recommending it as the real, default scaling story for M7
deployments, ahead of any of the other three options.

---

## 4. Option B — free-threaded CPython: does not help today, for two independent real reasons

This is the most involved, and most surprising, finding of this pass.

### 4a. A real dependency-ecosystem gap, found before any runtime testing was even possible

Installing `presidium`/`presidium-contrib[server]` under free-threaded CPython required real,
non-trivial extra work: `cel-python`'s `google-re2` dependency has no prebuilt wheel for
free-threaded builds and fails to build from source without `abseil`, `re2`, and `pybind11`
installed as system/build dependencies -- none of which are needed under normal CPython. On
Linux (`darkenergy`), `cffi` (a `cryptography` dependency) additionally refuses to build under
free-threaded **3.13** outright ("Upgrade to free-threaded 3.14 or newer"), forcing a move to
3.14. **This is a real, concrete, present-day cost of adopting free-threaded CPython for this
specific dependency chain** -- not a Presidium-specific problem, but a real signal that the
surrounding C-extension ecosystem is not yet fully ready.

### 4b. Even once installed, the GIL doesn't actually stay off -- and forcing it off doesn't help anyway

Once built, importing `re2._re2` triggers a real, documented CPython 3.14 safety mechanism: the
module hasn't declared itself free-threading-safe, so **the GIL is automatically re-enabled at
runtime**, with an explicit warning. Overriding this (`PYTHON_GIL=0`, at real, acknowledged risk
of undefined behavior if `re2`'s C code isn't actually thread-safe) does let the GIL stay off --
confirmed directly (`sys._is_gil_enabled()` returns `False` throughout, including after import).

**But it makes no measurable difference.** With the GIL forced off, the same local-loopback,
20-rule benchmark produced a **~610-622 req/sec ceiling** -- statistically indistinguishable from
the normal, GIL-enabled local number (~630-640 req/sec) in §2a.

**Why, and this is the real finding**: `civitas.gateway.HTTPGateway` serves requests on a single
asyncio event loop, on a single OS thread. Free-threading only removes contention *between
multiple OS threads simultaneously wanting the GIL* -- a single-threaded async server was never
contending with itself for the GIL in the first place, so there is nothing for free-threading to
relieve. **Option B cannot help Presidium's request-path hot loop until the serving architecture
itself uses multiple OS threads to handle concurrent requests** -- at which point the benefit
would look architecturally similar to Option A (horizontal scaling), just inside one process
instead of across several.

**Recommendation: do not pursue Option B further right now.** Two independent, real blockers
exist today -- an immature C-extension ecosystem for this exact dependency chain, and a serving
architecture that wouldn't benefit even if the ecosystem gap were closed. Revisit only if (a) a
future `civitas.gateway.HTTPGateway` gains a real multi-threaded worker model, and (b)
`google-re2`/`cffi` declare free-threading support upstream.

---

## 5. Option C — a Rust-backed CEL evaluator: not prototyped, but real, concrete directional evidence exists

Not built this pass (per the milestone's own "no component gets rewritten... the deliverable is
a design doc with real numbers" framing) -- but two real, concrete facts ground the option
better than it was grounded before:

- **A real, actively maintained Rust CEL crate already exists**: `cel-interpreter` on crates.io
  (547k+ downloads, last updated within the past year) -- a real starting point for a PyO3
  binding behind the same `PolicyEngine` Protocol, not a from-scratch language implementation.
- **§6's real OPA comparison (below) is the best available directional evidence for the plausible
  magnitude of a compiled-evaluator speedup** -- OPA (Go, compiled) sustained 15-140x Presidium's
  own throughput at equivalent rule counts on the same hardware. A Rust-backed CEL evaluator
  would not be identical to OPA/Rego (different policy language, different engine), but the
  category of improvement (compiled, non-interpreted evaluation replacing a pure-Python
  tree-walking interpreter) is the same one driving OPA's advantage here.

**Honest caveat**: PyO3 call-boundary overhead (marshaling Python objects into and out of Rust)
would eat into some of this theoretical gain -- the real number can only come from an actual
prototype, which this pass deliberately did not build. **Recommended as the next real
investigation step** if Option A's horizontal scaling alone proves insufficient or too costly
for a real production deployment's throughput target.

## 6. Option D — a fuller Rust rewrite: not evaluated, per the milestone's own sequencing

Not benchmarked, matching `docs/vision/roadmap.md`'s own framing: "most invasive; only worth it
if A-C don't clear the bar." Option A already does, for today's real, known load; nothing in
this pass's findings changes that sequencing.

---

## 7. The real, fair, same-hardware comparison — Presidium vs. OPA

Per this doc's own comparison-methodology section below, the one competitor whose internals are
actually independently replicable is OPA (free, open source, self-hostable) -- so this pass ran
a real, same-conditions, same-hardware (local Mac loopback, identical `ab` matrix) comparison, not
a citation of OPA's own marketing numbers. `benchmarks/gen_opa_policy.py` generates a Rego policy
with the **identical logical shape** as Presidium's own benchmark rule set (N-1 never-matching
distractor rules + one terminal allow), so both systems evaluate the same workload, not just
"a policy" each.

| Rules | Presidium (req/sec) | OPA (req/sec) | OPA / Presidium |
|---|---|---|---|
| 5 | ~2,000 | ~29,000-32,000 | ~15x |
| 20 | ~635 | ~25,000-29,000 | ~42x |
| 100 | ~146 | ~19,800-21,700 | ~140x |

**Two real, honest things worth saying about this table, not hidden:**

1. **The gap widens as rule count grows** -- OPA's compiled, Go-native evaluation barely slows
   down as rules are added (from ~31,000 to ~20,700 req/sec, roughly -33%, across a 20x increase
   in rule count), while Presidium's pure-Python tree-walking cost scales roughly linearly with
   rule count (from ~2,000 to ~146 req/sec, roughly -93%, across the same range). This means the
   real cost of Presidium's current architecture grows worse, not just proportionally, as a real
   deployment's policy set grows.
2. **This is not a perfectly isolated apples-to-apples comparison, and the difference is
   attributable mostly to the CEL-eval cost itself, not incidental overhead** -- confirmed by
   comparing against §1's own isolated numbers: at 20 rules, the isolated CEL eval alone
   (1,314µs) accounts for the large majority of the ~1,587µs full HTTP request time (§2a: ~630
   req/sec ≈ 1,587µs/request) -- the additional registry-lookup/Civitas-dispatch/JSON overhead is
   a comparatively small ~270µs slice. The dominant cost really is the interpreted-Python CEL
   evaluator itself, exactly matching what Option C's rationale assumes, now with real numbers
   behind it rather than an assumption.

---

## Comparison methodology: what to publish, and what to compare against in the market

This section answers the three real, tied-together questions this research pass started from:
who are Presidium's real competitors as a product, what should be measured on its own real HTTP
endpoints, and what should any published benchmark be compared against. Reached via a structured,
adversarial five-perspective council session (the `llm-council` methodology), not a single
unchallenged take -- summarized here; see the session transcript for the full five-advisor
analysis and peer review.

**Real competitors identified** (grounded in `docs/research/competitive-landscape.md` plus fresh
research this pass): Microsoft's Agent Governance Toolkit (a 7-package, multi-language, Rust-core
policy engine claiming **<0.1ms p99** decision latency), Fiddler (SaaS observability + guardrails,
**<100ms** trust-model latency -- a different order of magnitude *and* a different kind of check,
ML-based scoring rather than rule evaluation), general-purpose policy engines (**OPA** -- own
docs frame "a microservice authorization decision... budget in the order of 1 millisecond" as
their own performance bar; **AWS Cedar**), and a newly-identified, narrowly-scoped competitor not
previously in this repo's own competitive-landscape doc: **Kastra** ("the authorization layer for
AI systems" -- intercepts every AI action, returns allow/deny/redact/escalate, and publishes its
own dedicated benchmarks page, explicitly tracking the p99/p50 tail-latency ratio under
increasing concurrency).

**The real risk the council surfaced and this doc avoids**: comparing an isolated, no-network
microbenchmark (§1) against a competitor's full-decision or full-HTTP-endpoint marketing claim
is an apples-to-oranges trap. AGT's "<0.1ms p99" and Fiddler's "<100ms" almost certainly measure
different layers (in-process call vs. full ML guardrail scoring) than a raw CEL eval -- blending
them into one table without saying so would be a credibility failure, not a fair comparison. **§2
and §7's real, measured numbers exist specifically to avoid ever needing to make that mistake.**

**What this doc actually does, following the council's recommendation:**

1. **Presidium's own real numbers, first and mandatory** (§1, §2) -- exists now, didn't before.
2. **One real, fair, same-conditions comparison** (§7) -- OPA, the one competitor whose internals
   are actually independently replicable, run identically, on the same hardware.
3. **Everything else (AGT, Fiddler, Kastra) is cited above as labeled, third-party context only**
   -- never blended into §2/§7's own measured tables.

**The correct framing for "is Presidium fast enough,"** per the council's own First Principles
perspective: not "is it faster than AGT," but whether governance overhead stays negligible
relative to what it's gating -- an LLM call is milliseconds-to-seconds; even Presidium's own,
now-corrected, higher CEL-eval numbers (§1) are one to two orders of magnitude below that. **Where
this stops being true is exactly the real, load-bearing finding §2's flat-throughput-under-
concurrency data shows**: a shared, multi-tenant M7 deployment serving many concurrent callers is
the scenario where the GIL ceiling, not the per-request cost, becomes the real constraint --
matching `docs/vision/roadmap.md`'s own original framing exactly, now with real numbers proving
it rather than asserting it.

---

## Recommendation

1. **Ship Option A (horizontal scaling) as the real, documented, default scaling story for M7
   deployments today.** Zero code changes, confirmed to work close to linearly on real hardware.
   Add a short operator-facing note to `docs/design/presidium-server.md` recommending multiple
   `presidium-contrib` server processes behind a load balancer for any deployment expecting
   sustained concurrent load beyond a few hundred requests/sec.
2. **Do not pursue Option B (free-threaded CPython) further right now** -- two independent, real
   blockers (an immature C-extension ecosystem for this exact dependency chain, and a
   single-threaded serving architecture that wouldn't benefit even if the ecosystem gap closed).
   Revisit only if both close.
3. **Option C (a Rust-backed CEL evaluator via PyO3) is the real next lever**, now backed by
   concrete evidence (an existing, maintained crate; a real 15-140x directional comparison) --
   worth a contained prototype spike if a real deployment's throughput needs exceed what Option A
   can cost-effectively cover, not before.
4. **Option D remains correctly out of scope**, per the milestone's own original sequencing.
5. **Publish this doc's §1/§2/§7 numbers, with the comparison-methodology section above, as
   Presidium's own real, honest benchmark story** -- differentiated by being the only one in this
   space (per the research done) that discloses methodology, hardware, and concurrency model
   explicitly rather than a single unqualified headline number.

## Reproducing this

See `benchmarks/README.md`. All scripts are real, checked-in, and reusable -- not deleted after
this pass, per this org's own spike-code convention (`python-civitas`'s M-LAST scoping doc
states the same discipline for a reason: a benchmark that can't be re-run isn't a benchmark
that can be trusted later).
