"""WER computation with text normalization."""

import re

import jiwer

# Contraction expansions
_CONTRACTIONS = {
    "don't": "do not",
    "won't": "will not",
    "can't": "cannot",
    "n't": " not",
    "'re": " are",
    "'ve": " have",
    "'ll": " will",
    "'d": " would",
    "'m": " am",
}


def _expand_contractions(text: str) -> str:
    lower = text.lower()
    for short, long in sorted(_CONTRACTIONS.items(), key=lambda x: -len(x[0])):
        lower = lower.replace(short, long)
    return lower


def normalize_text(text: str, strip_fillers: bool = False) -> str:
    """Normalize reference/hypothesis before WER."""
    t = text.lower()
    t = _expand_contractions(t)
    # Unicode-aware punctuation removal
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    t = re.sub(r"\s+", " ", t).strip()

    if strip_fillers:
        fillers = {"um", "uh", "erm", "ah"}
        t = " ".join(w for w in t.split() if w not in fillers)

    return t


def _jiwer_transform():
    return jiwer.Compose(
        [
            jiwer.ToLowerCase(),
            jiwer.RemovePunctuation(),
            jiwer.RemoveMultipleSpaces(),
            jiwer.Strip(),
        ]
    )


def compute_wer(reference: str, hypothesis: str) -> tuple[float, dict]:
    """Return (wer, details_dict)."""
    ref_norm = normalize_text(reference)
    hyp_norm = normalize_text(hypothesis)

    if not ref_norm.split():
        return (0.0 if not hyp_norm.split() else 1.0, {
            "substitutions": 0,
            "deletions": 0,
            "insertions": len(hyp_norm.split()),
            "hits": 0,
        })

    transform = _jiwer_transform()
    ref_t = transform(ref_norm)
    hyp_t = transform(hyp_norm)

    output = jiwer.process_words(ref_t, hyp_t)
    wer = output.wer
    details = {
        "substitutions": output.substitutions,
        "deletions": output.deletions,
        "insertions": output.insertions,
        "hits": output.hits,
    }
    return wer, details


def compute_chrf(reference: str, hypothesis: str) -> float:
    try:
        from sacrebleu.metrics import CHRF

        chrf = CHRF(word_order=0, char_order=6)
        score = chrf.sentence_score(hypothesis, [reference])
        s = float(score.score)
        # sacrebleu may return 0–1 or 0–100 depending on version
        if s <= 1.0:
            s *= 100.0
        return s
    except Exception:
        return 0.0


def compute_punctuation_f1(reference: str, hypothesis: str) -> float:
    punct = set(".,!?;:'\"-")
    ref_p = [c for c in reference if c in punct]
    hyp_p = [c for c in hypothesis if c in punct]
    if not ref_p and not hyp_p:
        return 1.0
    if not ref_p or not hyp_p:
        return 0.0

    ref_set = set(ref_p)
    hyp_set = set(hyp_p)
    tp = len(ref_set & hyp_set)
    precision = tp / len(hyp_set) if hyp_set else 0.0
    recall = tp / len(ref_set) if ref_set else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)
