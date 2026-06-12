# RFC-002: Multi-Dimensional Evaluation for Non-Deterministic Systems

**Status:** Seed (investigation needed)
**Author:** Jeryn Mathew
**Created:** 2026-06-11
**Milestone:** Post-M4 (requires dedicated research)

## Problem Statement

Current LLM evaluation produces scalar outputs (scores, booleans) from fundamentally non-deterministic, high-dimensional systems. This is a category error.

### The Mismatch

Traditional ML evaluation works because the output space is constrained — classification labels, regression values. A scalar metric (accuracy = 0.94) is meaningful because the task itself is scalar.

GenAI outputs are high-dimensional artifacts. A single response simultaneously has factuality, completeness, tone, structure, relevance, safety, and contextual appropriateness — all as independent dimensions. Collapsing these to "quality: 0.73" is lossy by definition.

### Specific Failures of Scalar Evaluation

1. **False precision**: "Faithfulness: 0.73" implies precision that doesn't exist. Run the same LLM-as-judge eval 10 times and you get a distribution (0.68, 0.77, 0.71...), not a point. The score IS a distribution but is reported as a point estimate.

2. **Dimensional collapse**: A response can be factually correct but tonally wrong. Complete but verbose. Safe but unhelpful. A single score conflates all dimensions. When it drops from 0.8 to 0.6, you don't know WHICH dimension degraded. Not actionable.

3. **LLM-as-judge circularity**: Using GPT-4 to evaluate GPT-4 shares biases, blind spots, and failure modes. "This answer is 0.9 quality" means "this is the kind of answer I would generate" — tautological.

4. **Context-free scoring**: "Is this response good?" depends entirely on context. A 3-sentence answer is perfect for chat, terrible for a research report. Current evals strip context.

## Core Insight

If the system being evaluated is multi-dimensional and non-deterministic, the evaluation output should reflect that.

Analogy: a neural network's output isn't a single number — it's a probability distribution across classes. We only collapse it to a prediction via argmax for operational convenience. But we keep the full distribution for calibration, uncertainty estimation, and active learning. Evals should do the same.

## What Multi-Dimensional Evaluation Could Look Like

```python
@dataclass
class DimensionResult:
    dimension: str              # "factuality", "completeness", "tone", "safety"
    mean: float                 # central estimate
    std_dev: float              # uncertainty
    n_samples: int              # how many evaluations produced this
    evidence: list[str]         # what drove the score
    conditions: dict[str, float]  # conditional scores

@dataclass
class EvalResult:
    dimensions: dict[str, DimensionResult]
    context: EvalContext         # under what conditions this evaluation holds
    eval_confidence: float       # meta-uncertainty: confidence in the evaluation itself
    caveats: list[str]          # explicit limitations of this evaluation
```

Instead of "quality: 0.73", you get:
- Factuality: mean=0.85, std=0.08 (5 samples), evidence: ["cites source correctly", "one date error"]
- Completeness: mean=0.60, std=0.12, evidence: ["missing conclusion", "covers 3/5 topics"]
- Tone: mean=0.92, std=0.03, evidence: ["appropriate formality"]
- Safety: mean=1.00, std=0.00, evidence: ["no PII", "no harmful content"]
- Caveat: "Completeness assumes all 5 topics are equally important"

## Implications for Presidium Trust Scoring

The M2 `TrustScorer` (0.0-1.0 scalar, 3 tiers) is correct for shipping. But the long-term trust model should be multi-dimensional:

```python
@dataclass
class TrustProfile:
    policy_compliance: DimensionResult
    output_quality: DimensionResult
    resource_efficiency: DimensionResult
    security_posture: DimensionResult
    collaboration: DimensionResult
    context_trust: dict[str, float]   # "trust for research" vs "trust for production writes"
    caveats: list[str]                # "insufficient data for security dimension"
```

CEL policies could then express:
```cel
agent.trust.dimensions.security_posture.mean >= 0.9 &&
agent.trust.dimensions.security_posture.n_samples >= 20
```

This says "I trust this agent's security posture AND I have enough observations to be confident."

## Open Questions (For Investigation)

1. How do you aggregate multi-dimensional trust into actionable decisions without collapsing back to a scalar?
2. What are the right dimensions for agent trust? Are they universal or domain-specific?
3. How do you handle the meta-uncertainty problem — evaluating the evaluator's confidence?
4. Can distributional trust scores be efficiently stored and queried (SQLite/Postgres)?
5. How do existing systems handle distributional outputs? (Bayesian neural networks, conformal prediction, ensemble methods)
6. What does the academic literature say about multi-dimensional evaluation of language models specifically?
7. How does this relate to the emerging field of "uncertainty quantification for LLMs"?

## Recommendation

This RFC is a **seed for future investigation**, not a proposal for implementation. The questions above need dedicated research before any design work.

The M2 TrustScorer (scalar, simple) ships as-is. The Protocol is designed to be extensible — a future `DistributionalTrustScorer` can return richer structures without breaking existing consumers that only read `.value` and `.tier`.

Investigation should happen post-M4, when the basic autonomy progression is working and we have real trust scoring data to analyze.
