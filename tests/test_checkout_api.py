import pytest
from fastapi.testclient import TestClient

from createcart_api import create_app

ADMIN = {"X-Admin-Key": "createcart-admin"}
T = "test-tenant"
MENU = f"/api/{T}"
CART = f"/api/{T}/carts/sess-pay"


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


def test_checkout_empty_cart_400(client):
    assert client.post(f"{CART}/checkout").status_code == 400


def test_checkout_prices_from_cart(client):
    client.post(f"{CART}/items", json={"item_id": "plain-dosa", "quantity": 2})
    r = client.post(f"{CART}/checkout")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "mock"
    assert body["amount"] == 12000           # 120.00 INR -> paise
    assert body["order_id"].startswith("order_")
    assert "mock_payment" in body            # ready-to-verify pair for local


def test_full_payment_round_trip_clears_cart(client):
    client.post(f"{CART}/items", json={"item_id": "plain-dosa", "quantity": 2})
    co = client.post(f"{CART}/checkout").json()
    mp = co["mock_payment"]
    r = client.post(
        f"{MENU}/payments/verify",
        json={"order_id": co["order_id"], "payment_id": mp["payment_id"],
              "signature": mp["signature"]},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "paid"
    # cart was cleared on successful payment
    assert client.get(CART).json()["items"] == []


def test_bad_signature_rejected_and_cart_kept(client):
    client.post(f"{CART}/items", json={"item_id": "plain-dosa"})
    co = client.post(f"{CART}/checkout").json()
    r = client.post(
        f"{MENU}/payments/verify",
        json={"order_id": co["order_id"], "payment_id": "pay_x", "signature": "bad"},
    )
    assert r.status_code == 400
    # cart NOT cleared since payment failed
    assert len(client.get(CART).json()["items"]) == 1
