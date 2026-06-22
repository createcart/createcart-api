import pytest
from fastapi.testclient import TestClient

from createcart_api import create_app

ADMIN = {"X-Admin-Key": "createcart-admin"}
T = "test-tenant"
MENU = f"/api/{T}"
CART = f"/api/{T}/carts/sess-1"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATECART_DATA_DIR", str(tmp_path))
    from createcart_api import config, deps

    config.settings.data_dir = tmp_path
    config.settings.storage = "sqlite"
    config.settings.db_path = str(tmp_path / "test.db")
    deps._database.cache_clear()
    deps._registry_for.cache_clear()
    c = TestClient(create_app())
    # Seed a couple of menu items to add to the cart.
    c.post(f"{MENU}/items", json={"name": "Plain Dosa", "price": "60", "icon": "🫓"},
           headers=ADMIN)
    c.post(f"{MENU}/items", json={"name": "Pulihora", "price": "50"}, headers=ADMIN)
    c.post(f"{MENU}/items",
           json={"name": "Sold Out", "price": "99", "available": False}, headers=ADMIN)
    return c


def test_empty_cart(client):
    r = client.get(CART)
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.json()["totals"]["grand_total"] == "0.00"


def test_add_uses_server_price_not_client(client):
    # No price in the body — server pulls it from the menu.
    r = client.post(f"{CART}/items", json={"item_id": "plain-dosa", "quantity": 2})
    assert r.status_code == 201
    body = r.json()
    assert body["items"][0]["unit_price"] == "60.00"
    assert body["items"][0]["line_total"] == "120.00"
    assert body["totals"]["grand_total"] == "120.00"


def test_add_unknown_item_404(client):
    r = client.post(f"{CART}/items", json={"item_id": "ghost"})
    assert r.status_code == 404


def test_add_unavailable_item_409(client):
    r = client.post(f"{CART}/items", json={"item_id": "sold-out"})
    assert r.status_code == 409


def test_increment_decrement_remove(client):
    client.post(f"{CART}/items", json={"item_id": "plain-dosa"})
    r = client.post(f"{CART}/items/plain-dosa/increment", json={"by": 2})
    assert r.json()["items"][0]["quantity"] == 3
    r = client.post(f"{CART}/items/plain-dosa/decrement", json={"by": 1})
    assert r.json()["items"][0]["quantity"] == 2
    r = client.delete(f"{CART}/items/plain-dosa")
    assert r.json()["items"] == []


def test_set_quantity_zero_removes(client):
    client.post(f"{CART}/items", json={"item_id": "plain-dosa"})
    r = client.put(f"{CART}/items/plain-dosa", json={"quantity": 0})
    assert r.json()["items"] == []


def test_parcel_charge_requires_admin(client):
    client.post(f"{CART}/items", json={"item_id": "plain-dosa"})
    # shopper cannot set a charge
    r = client.post(f"{CART}/charges",
                    json={"code": "parcel", "label": "Parcel", "amount": "10"})
    assert r.status_code == 401
    # admin can
    r = client.post(f"{CART}/charges",
                    json={"code": "parcel", "label": "Parcel", "amount": "10"},
                    headers=ADMIN)
    assert r.json()["totals"]["charges_total"] == "10.00"
    assert r.json()["totals"]["grand_total"] == "70.00"  # 60 + 10


def test_discount_requires_admin(client):
    client.post(f"{CART}/items", json={"item_id": "plain-dosa"})  # 60
    # shopper cannot discount themselves
    assert client.post(f"{CART}/discount",
                       json={"kind": "percent", "value": "50"}).status_code == 401
    r = client.post(f"{CART}/discount", json={"kind": "percent", "value": "10"},
                    headers=ADMIN)
    assert r.json()["totals"]["discount_total"] == "6.00"
    assert r.json()["totals"]["grand_total"] == "54.00"


def test_cart_persists_and_is_isolated(client):
    client.post(f"{CART}/items", json={"item_id": "plain-dosa", "quantity": 2})
    # same cart id -> persisted
    assert client.get(CART).json()["items"][0]["quantity"] == 2
    # different cart id -> empty
    other = client.get(f"/api/{T}/carts/sess-2").json()
    assert other["items"] == []


def test_clear_cart(client):
    client.post(f"{CART}/items", json={"item_id": "plain-dosa"})
    r = client.post(f"{CART}/clear")
    assert r.json()["items"] == []
