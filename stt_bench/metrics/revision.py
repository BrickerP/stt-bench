"""Streaming partial revision rate.

Measures how often a streaming provider rewrites words it already emitted,
instead of only appending new ones. The same ``normalize_text`` path used for
WER is applied first, so casing, punctuation, and contractions do not count
as revisions.

Definition
----------
Hypotheses are grouped into segments. A segment is the non-final partials
that precede a final result, followed by that final when it contains
non-whitespace text. Empty finals are endpoint markers and are omitted.
Comparisons never cross a segment boundary (a later utterance is not a
rewrite of the previous one).

After normalization, an **interim update** is a consecutive pair inside a
segment. The update **revises** when the previous word sequence is not a
prefix of the next one: previously emitted words were substituted, deleted,
or split by an insertion. An identical repeat, a pure append, and a pair
that differs only by case or punctuation are not revisions.

```
partial_revision_rate = revising_updates / interim_updates
revised_word_count    = Σ (substitutions + deletions) over updates
word_churn            = revised_word_count / word_count(normalized final)
```

Substitutions and deletions come from the same word-level alignment as WER
(``jiwer``). Insertions of new words are not revised words. A middle
insertion still counts as a revising update, because the previously emitted
sequence was not a stable prefix, but it adds nothing to ``revised_word_count``
when every previous word is preserved.

Not applicable (all three values are ``None``, never ``0``):

- interims were not captured (batch / non-streaming providers)
- the grouped hypotheses contain no consecutive pair (no partials, or a
  single partial with no distinct closing final)

``word_churn`` is also ``None`` when the normalized final transcript has no
words, because there is no length to normalize by. ``revised_word_count`` is
still reported in that case.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import jiwer

from stt_bench.metrics.wer import normalize_text


@dataclass(frozen=True)
class PartialRevisionStats:
    partial_revision_rate: float | None
    revised_word_count: int | None
    word_churn: float | None
    interim_updates: int = 0
    revising_updates: int = 0


def group_interim_hypotheses(partials: Sequence[tuple[str, bool]]) -> list[list[str]]:
    """Group ``(text, is_final)`` events into per-segment hypothesis lists.

    Each inner list is one utterance: non-final partials in emission order,
    then that segment's final text when it is non-empty after stripping.
    A whitespace-only final closes the segment without becoming a hypothesis.
    """
    segments: list[list[str]] = []
    current: list[str] = []
    for text, is_final in partials:
        if is_final:
            if text.strip():
                current.append(text)
            if current:
                segments.append(current)
            current = []
        else:
            current.append(text)
    if current:
        segments.append(current)
    return segments


def _is_stable_prefix(previous: list[str], current: list[str]) -> bool:
    if len(previous) > len(current):
        return False
    return current[: len(previous)] == previous


def _revised_words(previous: str, current: str) -> int:
    """Words in ``previous`` that alignment substitutes or deletes."""
    prev_words = previous.split()
    if not prev_words:
        return 0
    if not current.split():
        return len(prev_words)
    output = jiwer.process_words(previous, current)
    return int(output.substitutions + output.deletions)


def compute_partial_revision(
    interim_hypotheses: list[list[str]] | None,
    *,
    final_text: str | None = None,
) -> PartialRevisionStats:
    """Score grouped interim hypotheses. ``None`` input is not applicable."""
    if interim_hypotheses is None:
        return PartialRevisionStats(None, None, None)

    interim_updates = 0
    revising_updates = 0
    revised_word_count = 0
    for segment in interim_hypotheses:
        normalized = [normalize_text(text) for text in segment]
        for index in range(1, len(normalized)):
            interim_updates += 1
            previous = normalized[index - 1]
            current = normalized[index]
            if not _is_stable_prefix(previous.split(), current.split()):
                revising_updates += 1
            revised_word_count += _revised_words(previous, current)

    if interim_updates == 0:
        return PartialRevisionStats(None, None, None)

    rate = revising_updates / interim_updates
    final_words = normalize_text(final_text or "").split()
    word_churn = (revised_word_count / len(final_words)) if final_words else None
    return PartialRevisionStats(
        partial_revision_rate=rate,
        revised_word_count=revised_word_count,
        word_churn=word_churn,
        interim_updates=interim_updates,
        revising_updates=revising_updates,
    )
