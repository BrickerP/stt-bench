from stt_bench.cli.main import _parse_providers


def test_parse_providers_comma_separated():
    assert _parse_providers(["whisper,deepgram"]) == ["whisper", "deepgram"]


def test_parse_providers_multiple_flags():
    assert _parse_providers(["whisper", "deepgram"]) == ["whisper", "deepgram"]


def test_parse_providers_strips_and_skips_empty():
    assert _parse_providers([" whisper , deepgram ", ""]) == ["whisper", "deepgram"]


def test_parse_providers_none_or_empty():
    assert _parse_providers(None) == []
    assert _parse_providers([]) == []
