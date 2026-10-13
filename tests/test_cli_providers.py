from stt_bench.cli.main import _default_model, _parse_providers
from stt_bench.settings import Settings


def test_parse_providers_comma_separated():
    assert _parse_providers(["whisper,deepgram"]) == ["whisper", "deepgram"]


def test_parse_providers_multiple_flags():
    assert _parse_providers(["whisper", "deepgram"]) == ["whisper", "deepgram"]


def test_parse_providers_strips_and_skips_empty():
    assert _parse_providers([" whisper , deepgram ", ""]) == ["whisper", "deepgram"]


def test_parse_providers_none_or_empty():
    assert _parse_providers(None) == []
    assert _parse_providers([]) == []


def test_default_model_google_and_azure():
    settings = Settings()
    assert _default_model("google", settings) == "latest_long"
    assert _default_model("azure", settings) == "fast"
