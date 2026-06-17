import pytest
import typer

from stt_bench.cli.main import (
    _looks_like_placeholder_api_key,
    _print_run_summary,
    _validate_provider_credentials,
)
from stt_bench.settings import Settings


def test_looks_like_placeholder_api_key():
    assert _looks_like_placeholder_api_key("sk-...")
    assert _looks_like_placeholder_api_key("...")
    assert not _looks_like_placeholder_api_key("sk-" + "a" * 40)


def test_validate_provider_credentials_rejects_missing():
    settings = Settings(openai_api_key=None, deepgram_api_key=None)
    with pytest.raises(typer.Exit) as exc:
        _validate_provider_credentials(["whisper", "deepgram"], settings)
    assert exc.value.exit_code == 1


def test_validate_provider_credentials_rejects_placeholders():
    settings = Settings(openai_api_key="sk-...", deepgram_api_key="...")
    with pytest.raises(typer.Exit) as exc:
        _validate_provider_credentials(["whisper", "deepgram"], settings)
    assert exc.value.exit_code == 1


def test_validate_provider_credentials_allows_mock():
    settings = Settings(openai_api_key=None, deepgram_api_key=None)
    _validate_provider_credentials(["mock"], settings)


def test_print_run_summary_failed(capsys):
    _print_run_summary(
        {
            "id": "run_test",
            "status": "failed",
            "sample_count": 1,
            "config": {"provider": "whisper", "transport_mode": "batch"},
            "error": "auth failed",
        }
    )
    captured = capsys.readouterr()
    assert "Run run_test" in captured.out
    assert "Status: failed" in captured.out
    assert "auth failed" in captured.err
