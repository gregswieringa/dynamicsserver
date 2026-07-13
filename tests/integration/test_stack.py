# Covers item 1: the stack (real Postgres + the built buyer-api image) comes
# up clean and /health proves a real DB connection, not a mocked one.


def test_health(client) -> None:
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
