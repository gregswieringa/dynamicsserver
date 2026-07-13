import uuid
from typing import Any


def _user_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "email": f"buyer-{uuid.uuid4()}@example.com",
        "display_name": "Test Buyer",
    }
    payload.update(overrides)
    return payload


def _address_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "recipient_name": "Test Buyer",
        "line1": "123 Main St",
        "city": "Springfield",
        "postal_code": "12345",
        "country": "US",
    }
    payload.update(overrides)
    return payload


def _create_user(client, **overrides: Any) -> dict[str, Any]:
    return client.post("/users", json=_user_payload(**overrides)).json()


def _defaults_for_user(db_conn, user_id: str) -> list[str]:
    rows = db_conn.execute(
        "SELECT id, is_default FROM addresses WHERE user_id = %s", (user_id,)
    ).fetchall()
    return [str(row[0]) for row in rows if row[1] is True]


# Covers item 4: the single most important integration test. The unit suite's
# FakeSession never enforces uniqueness, so it can't catch a missing
# clear-old-default step actually violating the real partial unique index
# (one_default_address_per_user, WHERE is_default). This proves the
# create_address / set_default_address "clear then set" logic really
# satisfies that constraint against real Postgres.
def test_default_address_invariant_survives_real_unique_index(client, db_conn) -> None:
    user = _create_user(client)

    first = client.post(
        f"/users/{user['id']}/addresses", json=_address_payload(is_default=True)
    )
    assert first.status_code == 201
    first_id = first.json()["id"]
    assert _defaults_for_user(db_conn, user["id"]) == [first_id]

    second = client.post(
        f"/users/{user['id']}/addresses",
        json=_address_payload(line1="456 Oak Ave", is_default=True),
    )
    assert second.status_code == 201
    second_id = second.json()["id"]

    # No unique-violation from the insert, and exactly one default remains —
    # the old one really flipped to false in the database, not just in memory.
    assert _defaults_for_user(db_conn, user["id"]) == [second_id]

    user_row = db_conn.execute(
        "SELECT default_shipping_address_id FROM users WHERE id = %s", (user["id"],)
    ).fetchone()
    assert str(user_row[0]) == second_id

    # set-default back to the first address flips it again, still exactly one.
    resp = client.post(f"/users/{user['id']}/addresses/{first_id}/set-default")
    assert resp.status_code == 200
    assert _defaults_for_user(db_conn, user["id"]) == [first_id]
