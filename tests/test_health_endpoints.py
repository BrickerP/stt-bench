from fastapi.testclient import TestClient

from stt_bench.server.app import create_app


def test_healthz_readyz_version():
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/healthz").json()["status"] == "ok"
        ready = client.get("/readyz")
        assert ready.status_code == 200
        assert "checks" in ready.json()
        ver = client.get("/version").json()
        assert ver["cli"] == "stt-bench"
        assert ver["name"] == "stt-eval-bench"
