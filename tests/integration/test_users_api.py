import uuid
from typing import Any


def _user_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "email": f"buyer-{uuid.uuid4()}@example.com",
        "display_name": "Test Buyer",
    }
    payload.update(overrides)
    return payload


# Covers item 6: create/get/list/update round-trip through a real commit
# against real Postgres (not the in-memory FakeSession from the unit suite).
def test_create_get_list_update_round_trip(client) -> None:
    created = client.post("/users", json=_user_payload()).json()
    assert created["account_status"] == "pending_verification"
    assert created["role"] == "buyer"

    fetched = client.get(f"/users/{created['id']}").json()
    assert fetched == created

    listed = client.get("/users").json()
    assert [u["id"] for u in listed] == [created["id"]]

    updated = client.patch(f"/users/{created['id']}", json={"display_name": "New Name"}).json()
    assert updated["display_name"] == "New Name"
    assert updated["email"] == created["email"]


# Covers item 2: proves the real asyncpg exception shape that routers/users.py
# unwraps (exc.orig.__cause__.constraint_name) actually matches what the real
# driver raises for users_email_key — the unit suite only asserted our
# assumption about that shape, this proves it against the real thing.
def test_duplicate_email_returns_409_from_real_unique_constraint(client) -> None:
    payload = _user_payload()

    first = client.post("/users", json=payload)
    assert first.status_code == 201

    second = client.post("/users", json=payload)
    assert second.status_code == 409
    assert second.json()["detail"] == "email already registered"


# Covers item 7: limit/offset ordering against real created_at timestamps
# from Postgres, not Python-side datetime.now() calls in a fake.
def test_list_users_pagination(client) -> None:
    ids = [
        client.post("/users", json=_user_payload()).json()["id"] for _ in range(5)
    ]

    page = client.get("/users", params={"limit": 2, "offset": 1}).json()

    assert [u["id"] for u in page] == ids[1:3]
