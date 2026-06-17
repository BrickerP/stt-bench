"""Tests for WER normalization."""

from stt_bench.metrics.wer import compute_wer, normalize_text


def test_normalize_lowercase_and_punctuation():
    ref = "Hello, World!"
    assert normalize_text(ref) == "hello world"


def test_normalize_contractions():
    assert "do not" in normalize_text("Don't stop")


def test_perfect_wer():
    ref = "HE HOPED THERE WOULD BE STEW"
    hyp = "he hoped there would be stew"
    wer, details = compute_wer(ref, hyp)
    assert wer == 0.0
    assert details["hits"] > 0


def test_wer_with_insertions():
    ref = "he hoped there would be stew for dinner"
    hyp = "he hoped there would be stew for dinner extra words"
    wer, details = compute_wer(ref, hyp)
    assert wer > 0
    assert details["insertions"] >= 1
