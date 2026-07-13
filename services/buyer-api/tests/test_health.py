import pytest
from fastapi.testclient import TestClient

from app import main as main_module


class _FakeConnection:
    async def __aenter__(self) -> "_FakeConnection":
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False

    async def execute(self, *_args: object, **_kwargs: object) -> None:
        return None


class _FakeEngine:
    def connect(self) -> _FakeConnection:
        return _FakeConnection()


def test_health_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "engine", _FakeEngine())
    client = TestClient(main_module.app)

    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
