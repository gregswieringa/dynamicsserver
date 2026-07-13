import uuid
from typing import Any

from fastapi.testclient import TestClient

from .fake_db import FakeSession, make_integrity_error


def _user_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "email": "buyer@example.com",
        "display_name": "Test Buyer",
    }
    payload.update(overrides)
    return payload


def test_create_user_success(client: TestClient) -> None:
    resp = client.post("/users", json=_user_payload())

    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "buyer@example.com"
    assert body["display_name"] == "Test Buyer"
    assert body["email_verified"] is False
    assert body["account_status"] == "pending_verification"
    assert body["role"] == "buyer"
    assert body["locale"] == "en-US"
    assert body["currency"] == "USD"
    assert uuid.UUID(body["id"])
    assert body["created_at"]


def test_create_user_duplicate_email(client: TestClient, fake_session: FakeSession) -> None:
    fake_session.raise_on_commit = make_integrity_error(
        "users_email_key", "duplicate key value violates unique constraint"
    )

    resp = client.post("/users", json=_user_payload())

    assert resp.status_code == 409
    assert resp.json()["detail"] == "email already registered"


def test_create_user_other_constraint_violation_is_not_mislabeled(
    client: TestClient, fake_session: FakeSession
) -> None:
    # Regression test: a non-email constraint failure (e.g. the phone_e164 CHECK)
    # must not be reported as a duplicate-email conflict. See CLAUDE.md's
    # "Integrity-error handling pattern" note.
    fake_session.raise_on_commit = make_integrity_error(
        "users_phone_e164_check", "new row for relation \"users\" violates check constraint"
    )

    resp = client.post("/users", json=_user_payload(phone="+14155552671"))

    assert resp.status_code == 422
    assert resp.json()["detail"] == "new row for relation \"users\" violates check constraint"


def test_create_user_invalid_email(client: TestClient) -> None:
    resp = client.post("/users", json=_user_payload(email="not-an-email"))

    assert resp.status_code == 422


def test_create_user_invalid_phone(client: TestClient) -> None:
    resp = client.post("/users", json=_user_payload(phone="555-1234"))

    assert resp.status_code == 422


def test_create_user_missing_display_name(client: TestClient) -> None:
    payload = _user_payload()
    del payload["display_name"]

    resp = client.post("/users", json=payload)

    assert resp.status_code == 422


def test_create_user_invalid_role(client: TestClient) -> None:
    resp = client.post("/users", json=_user_payload(role="admin"))

    assert resp.status_code == 422


def test_get_user_found(client: TestClient) -> None:
    created = client.post("/users", json=_user_payload()).json()

    resp = client.get(f"/users/{created['id']}")

    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_user_not_found(client: TestClient) -> None:
    resp = client.get(f"/users/{uuid.uuid4()}")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "user not found"


def test_get_user_invalid_uuid(client: TestClient) -> None:
    resp = client.get("/users/not-a-uuid")

    assert resp.status_code == 422


def test_list_users_empty(client: TestClient) -> None:
    resp = client.get("/users")

    assert resp.status_code == 200
    assert resp.json() == []


def test_list_users_default_order(client: TestClient) -> None:
    for i in range(3):
        client.post("/users", json=_user_payload(email=f"user{i}@example.com"))

    resp = client.get("/users")

    assert resp.status_code == 200
    emails = [u["email"] for u in resp.json()]
    assert emails == ["user0@example.com", "user1@example.com", "user2@example.com"]


def test_list_users_limit_offset(client: TestClient) -> None:
    for i in range(5):
        client.post("/users", json=_user_payload(email=f"user{i}@example.com"))

    resp = client.get("/users", params={"limit": 2, "offset": 1})

    body = resp.json()
    assert len(body) == 2
    assert [u["email"] for u in body] == ["user1@example.com", "user2@example.com"]


def test_update_user_partial(client: TestClient) -> None:
    created = client.post("/users", json=_user_payload()).json()

    resp = client.patch(f"/users/{created['id']}", json={"display_name": "New Name"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["display_name"] == "New Name"
    assert body["email"] == created["email"]


def test_update_user_not_found(client: TestClient) -> None:
    resp = client.patch(f"/users/{uuid.uuid4()}", json={"display_name": "x"})

    assert resp.status_code == 404
    assert resp.json()["detail"] == "user not found"


def test_update_user_invalid_phone(client: TestClient) -> None:
    created = client.post("/users", json=_user_payload()).json()

    resp = client.patch(f"/users/{created['id']}", json={"phone": "not-a-phone"})

    assert resp.status_code == 422


def test_update_user_account_status(client: TestClient) -> None:
    created = client.post("/users", json=_user_payload()).json()

    resp = client.patch(f"/users/{created['id']}", json={"account_status": "active"})

    assert resp.status_code == 200
    assert resp.json()["account_status"] == "active"


def test_update_user_empty_payload_is_noop(client: TestClient) -> None:
    created = client.post("/users", json=_user_payload()).json()

    resp = client.patch(f"/users/{created['id']}", json={})

    assert resp.status_code == 200
    assert resp.json()["display_name"] == created["display_name"]
