"""Human-readable formulas used by STT Bench metrics and scoring."""

from rich.console import Console
from rich.markdown import Markdown

MATH_DOC = """
# STT Bench — Metrics & Scoring Formulas

## 1. Word Error Rate (WER)

After **normalization** (lowercase, expand contractions, strip punctuation, collapse whitespace):

```
WER = (S + D + I) / N
```

| Symbol | Meaning |
|--------|---------|
| **S** | Substitutions — wrong words |
| **D** | Deletions — reference words missing in hypothesis |
| **I** | Insertions — extra words in hypothesis |
| **N** | Word count in normalized reference |

Alignment via dynamic programming (Levenshtein at word level, `jiwer`).

**Example:** reference 6 words, 1 substitution → WER = 1/6 ≈ 16.7%

---

## 2. chrF (optional)

Character n-gram F-score (order 6) on raw strings — rewards punctuation/casing match WER ignores.

---

## 3. Punctuation F1

```
precision = |punct_in_ref ∩ punct_in_hyp| / |punct_in_hyp|
recall    = |punct_in_ref ∩ punct_in_hyp| / |punct_in_ref|
F1        = 2 × precision × recall / (precision + recall)
```

Punctuation set: `.,!?;:'"-`

---

## 4. Latency

**TTFT (streaming only):** time from first audio byte sent → first non-empty partial/final token (ms).

**Total time:** end of audio send → final stable transcript (ms).

**RTF (Real-Time Factor):**

```
RTF = total_ms / (audio_duration_s × 1000)
```

RTF < 1.0 means faster than real-time. Batch providers (Whisper) have no meaningful TTFT; score uses neutral 0.5.

**Aggregates:** p50 and p95 via linear interpolation on sorted samples.

---

## 5. Cost

```
cost_usd = (audio_duration_s / 60) × rate_usd_per_minute
```

Rates from `config/pricing.yaml` (e.g. Whisper $0.006/min, Deepgram nova-2 $0.0043/min).

Benchmark aggregate:

```
cost_per_minute = sum(cost_usd) / (total_audio_duration_s / 60)
```

---

## 6. Partial revision rate (streaming only)

How often an interim hypothesis **rewrites words already emitted**, rather than only appending. Batch providers do not capture interims, so the metric is **not applicable** (`null`), not zero.

Hypotheses are split into segments at each final result. A segment is its non-final partials plus that segment's non-empty final. Empty finals are endpoint markers and are dropped. Pairs never cross a segment boundary.

Each hypothesis is normalized with the WER normalizer (lowercase, expand contractions, strip punctuation, collapse whitespace). An **interim update** is a consecutive pair in a segment. It is a **revision** when the previous word list is not a prefix of the next one.

```
partial_revision_rate = revising_updates / interim_updates
revised_word_count    = Σ (substitutions + deletions) over those updates
word_churn            = revised_word_count / words in the normalized final transcript
```

Word alignment is the same Levenshtein alignment WER uses. Insertions of new words are not revised words. A word inserted in the middle still counts as a revising update (the old sequence was not a stable prefix) and adds 0 to `revised_word_count` when every previous word survives.

| Case | Result |
|------|--------|
| No interims captured (batch) | not applicable |
| No pair to compare (empty, or a single partial) | not applicable |
| Identical repeat, or a change of only case/punctuation | update, not a revision |
| Pure append (`cat` → `cat sat`) | update, not a revision |
| Empty partial after words (`hello world` → ``) | revision; every previous word is deleted |
| Leading empty partial (` ` → `hello`) | update, not a revision (nothing was emitted yet) |
| Normalized final has no words | rate and revised-word count still apply; `word_churn` is not applicable |

---

## 7. Vibe Score (composite, 0–100)

Each component mapped to quality ∈ [0, 1]:

| Component | Formula | Notes |
|-----------|---------|-------|
| **WER** | `1 − wer_mean` | Higher is better |
| **TTFT** | `1 / (1 + ttft_p50_ms / 200)` | Streaming only; batch → 0.5 neutral |
| **RTF** | `1 / (1 + rtf_mean)` | Lower RTF → higher score |
| **Cost** | `1 / (1 + cost_per_minute / 0.01)` | Cheaper → higher score |
| **Confidence** | provider confidence or 0.5 default | When available |

**Default weights** (`config/scoring_weights.yaml`):

```
wer=0.35  ttft=0.25  rtf=0.15  cost=0.15  confidence=0.10
```

Unavailable components (e.g. TTFT for batch) are excluded; remaining weights renormalized:

```
vibe = 100 × Σ (quality_k × weight_k / Σ active_weights)
```

---

## 8. No ground truth?

When reference text is missing, WER/chrF/punctuation F1 are **skipped**. The system can still report:

- TTFT, total time, RTF, cost
- Provider confidence (if returned)
- Re-run consistency (same audio twice, text diff)
- Cross-provider agreement (pseudo-reference from majority vote — weak with only 2 providers)

Vibe score reweights to latency + cost + confidence only.
"""


def print_math_doc(console: Console | None = None) -> None:
    c = console or Console()
    c.print(Markdown(MATH_DOC))
