"""Customer order history: orders tie to the signed-in user; /my-orders filters."""

import pytest
from fastapi.testclient import TestClient

from createcart_api import create_app
from createcart_auth import MockProvider

ADMIN = {"X-Admin-Key": "createcart-admin"}
T = "test-tenant"
MENU = f"/api/{T}"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATECART_DATA_DIR", str(tmp_path))
    from createcart_api import config, deps

    config.settings.data_dir = tmp_path
    config.settings.storage = "sqlite"
    config.settings.db_path = str(tmp_path / "test.db")
    config.settings.payment_provider = "mock"
    config.settings.auth_provider = "mock"
    deps._database.cache_clear()
    deps._registry_for.cache_clear()
    deps._payment_provider.cache_clear()
    deps._auth_service.cache_clear()
    c = TestClient(create_app())
    c.post(f"{MENU}/items", json={"name": "Plain Dosa", "price": "60"}, headers=ADMIN)
    return c


def _order_as(client, cart_id, token):
    client.post(f"{MENU}/carts/{cart_id}/items", json={"item_id": "plain-dosa"})
    co = client.post(f"{MENU}/carts/{cart_id}/checkout").json()
    mp = co["mock_payment"]
    return client.post(
        f"{MENU}/payments/verify",
        json={"order_id": co["order_id"], "payment_id": mp["payment_id"],
              "signature": mp["signature"], "id_token": token,
              "customer": {"name": "X", "phone": "9"}},
    ).json()


def test_my_orders_returns_only_my_orders(client):
    asha = MockProvider().make_token(email="asha@gmail.com", name="Asha")
    ravi = MockProvider().make_token(email="ravi@gmail.com", name="Ravi")
    _order_as(client, "c-asha-1", asha)
    _order_as(client, "c-asha-2", asha)
    _order_as(client, "c-ravi-1", ravi)

    mine = client.get(f"{MENU}/my-orders", headers={"X-Auth-Token": asha}).json()
    assert len(mine) == 2
    assert all(o["customer"]["email"] == "asha@gmail.com" for o in mine)

    ravis = client.get(f"{MENU}/my-orders", headers={"X-Auth-Token": ravi}).json()
    assert len(ravis) == 1


def test_my_orders_requires_token(client):
    assert client.get(f"{MENU}/my-orders").status_code == 401
    assert client.get(f"{MENU}/my-orders",
                      headers={"X-Auth-Token": "garbage"}).status_code == 401


def test_order_stores_delivery_location(client):
    asha = MockProvider().make_token(email="asha@gmail.com", name="Asha")
    client.post(f"{MENU}/carts/loc1/items", json={"item_id": "plain-dosa"})
    co = client.post(f"{MENU}/carts/loc1/checkout").json()
    mp = co["mock_payment"]
    res = client.post(
        f"{MENU}/payments/verify",
        json={"order_id": co["order_id"], "payment_id": mp["payment_id"],
              "signature": mp["signature"], "id_token": asha,
              "customer": {"name": "Asha", "phone": "9", "lat": 17.4401, "lng": 78.3489}},
    ).json()
    oid = res["delivery_order_id"]
    order = [o for o in client.get(f"{MENU}/deliveries", headers=ADMIN).json()
             if o["id"] == oid][0]
    assert order["customer"]["lat"] == 17.4401
    assert order["customer"]["lng"] == 78.3489


def test_order_carries_subject_from_token(client):
    asha = MockProvider().make_token(email="asha@gmail.com", name="Asha")
    res = _order_as(client, "c1", asha)
    oid = res["delivery_order_id"]
    # admin can see the order has the subject attached
    order = [o for o in client.get(f"{MENU}/deliveries", headers=ADMIN).json()
             if o["id"] == oid][0]
    assert order["customer"]["subject"] == "mock-asha@gmail.com"
    assert order["customer"]["email"] == "asha@gmail.com"
