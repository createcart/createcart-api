import pytest
from fastapi.testclient import TestClient

from createcart_api import create_app

ADMIN = {"X-Admin-Key": "createcart-admin"}
T = "test-tenant"
MENU = f"/api/{T}"
CART = f"/api/{T}/carts/sess-del"
DELIV = f"/api/{T}/deliveries"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATECART_DATA_DIR", str(tmp_path))
    from createcart_api import config, deps

    config.settings.data_dir = tmp_path
    config.settings.storage = "sqlite"
    config.settings.db_path = str(tmp_path / "test.db")
    config.settings.payment_provider = "mock"
    deps._database.cache_clear()
    deps._registry_for.cache_clear()
    deps._payment_provider.cache_clear()
    c = TestClient(create_app())
    c.post(f"{MENU}/items", json={"name": "Plain Dosa", "price": "60"}, headers=ADMIN)
    return c


def _pay(client):
    """Run a full add->checkout->verify and return the verify response."""
    client.post(f"{CART}/items", json={"item_id": "plain-dosa", "quantity": 2})
    co = client.post(f"{CART}/checkout").json()
    mp = co["mock_payment"]
    return client.post(
        f"{MENU}/payments/verify",
        json={"order_id": co["order_id"], "payment_id": mp["payment_id"],
              "signature": mp["signature"],
              "customer": {"name": "Asha", "phone": "98...", "address": "Gachibowli"}},
    ).json()


def test_payment_creates_delivery_order(client):
    res = _pay(client)
    oid = res["delivery_order_id"]
    assert oid == res["order_id"]
    track = client.get(f"{DELIV}/{oid}").json()      # public tracking
    assert track["status"] == "placed"
    assert len(track["timeline"]) == 1


def test_track_unknown_404(client):
    assert client.get(f"{DELIV}/ghost").status_code == 404


def test_advance_lifecycle_admin(client):
    oid = _pay(client)["delivery_order_id"]
    for expected in ["confirmed", "preparing", "out_for_delivery", "delivered"]:
        r = client.post(f"{DELIV}/{oid}/advance", headers=ADMIN)
        assert r.json()["status"] == expected
    # past delivered -> 400
    assert client.post(f"{DELIV}/{oid}/advance", headers=ADMIN).status_code == 400


def test_advance_requires_admin(client):
    oid = _pay(client)["delivery_order_id"]
    assert client.post(f"{DELIV}/{oid}/advance").status_code == 401


def test_invalid_status_jump_rejected(client):
    oid = _pay(client)["delivery_order_id"]
    r = client.post(f"{DELIV}/{oid}/status", json={"status": "delivered"}, headers=ADMIN)
    assert r.status_code == 400


def test_cancel_and_courier_and_list(client):
    oid = _pay(client)["delivery_order_id"]
    client.post(f"{DELIV}/{oid}/courier",
                json={"name": "Ravi", "phone": "90..."}, headers=ADMIN)
    lst = client.get(DELIV, headers=ADMIN).json()
    assert len(lst) == 1 and lst[0]["courier"]["name"] == "Ravi"

    r = client.post(f"{DELIV}/{oid}/cancel", json={"reason": "test"}, headers=ADMIN)
    assert r.json()["status"] == "cancelled"
    assert [o["id"] for o in client.get(f"{DELIV}?status=cancelled", headers=ADMIN).json()] == [oid]
