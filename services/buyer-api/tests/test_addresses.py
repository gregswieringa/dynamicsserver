import uuid
from typing import Any

from fastapi.testclient import TestClient


def _user_payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "email": "buyer@example.com",
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


def _create_user(client: TestClient, **overrides: Any) -> dict[str, Any]:
    return client.post("/users", json=_user_payload(**overrides)).json()


def test_create_address_user_not_found(client: TestClient) -> None:
    resp = client.post(f"/users/{uuid.uuid4()}/addresses", json=_address_payload())

    assert resp.status_code == 404
    assert resp.json()["detail"] == "user not found"


def test_create_address_non_default_leaves_user_pointer_unset(client: TestClient) -> None:
    user = _create_user(client)

    resp = client.post(f"/users/{user['id']}/addresses", json=_address_payload())

    assert resp.status_code == 201
    assert resp.json()["is_default"] is False
    user_after = client.get(f"/users/{user['id']}").json()
    assert user_after["default_shipping_address_id"] is None


def test_create_address_default_sets_user_pointer_and_clears_prior_default(client: TestClient) -> None:
    user = _create_user(client)

    first = client.post(
        f"/users/{user['id']}/addresses", json=_address_payload(is_default=True)
    ).json()
    assert first["is_default"] is True
    user_after_first = client.get(f"/users/{user['id']}").json()
    assert user_after_first["default_shipping_address_id"] == first["id"]

    second = client.post(
        f"/users/{user['id']}/addresses",
        json=_address_payload(line1="456 Oak Ave", is_default=True),
    ).json()
    assert second["is_default"] is True

    addresses = client.get(f"/users/{user['id']}/addresses").json()
    first_reloaded = next(a for a in addresses if a["id"] == first["id"])
    assert first_reloaded["is_default"] is False

    user_after_second = client.get(f"/users/{user['id']}").json()
    assert user_after_second["default_shipping_address_id"] == second["id"]


def test_list_addresses_user_not_found(client: TestClient) -> None:
    resp = client.get(f"/users/{uuid.uuid4()}/addresses")

    assert resp.status_code == 404


def test_list_addresses_scoped_to_user(client: TestClient) -> None:
    user1 = _create_user(client)
    user2 = _create_user(client, email="other@example.com")
    client.post(f"/users/{user1['id']}/addresses", json=_address_payload())
    client.post(f"/users/{user2['id']}/addresses", json=_address_payload())

    resp = client.get(f"/users/{user1['id']}/addresses")

    body = resp.json()
    assert len(body) == 1
    assert body[0]["user_id"] == user1["id"]


def test_set_default_address_user_not_found(client: TestClient) -> None:
    resp = client.post(f"/users/{uuid.uuid4()}/addresses/{uuid.uuid4()}/set-default")

    assert resp.status_code == 404


def test_set_default_address_address_not_found(client: TestClient) -> None:
    user = _create_user(client)

    resp = client.post(f"/users/{user['id']}/addresses/{uuid.uuid4()}/set-default")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "address not found"


def test_set_default_address_belonging_to_other_user(client: TestClient) -> None:
    user1 = _create_user(client)
    user2 = _create_user(client, email="other@example.com")
    other_address = client.post(
        f"/users/{user2['id']}/addresses", json=_address_payload()
    ).json()

    resp = client.post(f"/users/{user1['id']}/addresses/{other_address['id']}/set-default")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "address not found"


def test_set_default_address_success(client: TestClient) -> None:
    user = _create_user(client)
    first = client.post(
        f"/users/{user['id']}/addresses", json=_address_payload(is_default=True)
    ).json()
    second = client.post(
        f"/users/{user['id']}/addresses", json=_address_payload(line1="456 Oak Ave")
    ).json()

    resp = client.post(f"/users/{user['id']}/addresses/{second['id']}/set-default")

    assert resp.status_code == 200
    assert resp.json()["is_default"] is True

    addresses = client.get(f"/users/{user['id']}/addresses").json()
    first_reloaded = next(a for a in addresses if a["id"] == first["id"])
    assert first_reloaded["is_default"] is False

    user_after = client.get(f"/users/{user['id']}").json()
    assert user_after["default_shipping_address_id"] == second["id"]
