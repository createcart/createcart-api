import pytest
from fastapi.testclient import TestClient

from createcart_api import create_app

ADMIN = {"X-Admin-Key": "createcart-admin"}
T = "test-tenant"
MENU = f"/api/{T}"
CART = f"/api/{T}/carts/sess-notify"
DELIV = f"/api/{T}/deliveries"
PHONE = "+919876500000"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATECART_DATA_DIR", str(tmp_path))
    from createcart_api import config, deps

    config.settings.data_dir = tmp_path
    config.settings.storage = "sqlite"
    config.settings.db_path = str(tmp_path / "test.db")
    config.settings.payment_provider = "mock"
    config.settings.notify_enabled = True
    config.settings.notify_provider = "console"
    config.settings.notify_channel = "sms"
    deps._database.cache_clear()
    deps._registry_for.cache_clear()
    deps._payment_provider.cache_clear()
    deps._notify_service.cache_clear()
    c = TestClient(create_app())
    c.post(f"{MENU}/items", json={"name": "Plain Dosa", "price": "60"}, headers=ADMIN)
    return c


def _sent():
    """The console provider's recorded messages (shared singleton)."""
    from createcart_api import deps

    return deps._notify_service().provider.sent


def _pay_with_phone(client, phone=PHONE):
    client.post(f"{CART}/items", json={"item_id": "plain-dosa", "quantity": 1})
    co = client.post(f"{CART}/checkout").json()
    mp = co["mock_payment"]
    return client.post(
        f"{MENU}/payments/verify",
        json={"order_id": co["order_id"], "payment_id": mp["payment_id"],
              "signature": mp["signature"],
              "customer": {"name": "Asha", "phone": phone}},
    ).json()


def test_placed_notification_sent_on_payment(client):
    before = len(_sent())
    _pay_with_phone(client)
    new = _sent()[before:]
    assert len(new) == 1
    assert new[0]["to"] == PHONE
    assert new[0]["channel"] == "sms"
    assert "placed" in new[0]["text"].lower()


def test_notification_on_each_status_change(client):
    oid = _pay_with_phone(client)["delivery_order_id"]
    before = len(_sent())
    for expected in ["confirmed", "out for delivery", "delivered"]:
        if expected == "confirmed":
            client.post(f"{DELIV}/{oid}/advance", headers=ADMIN)
        elif expected == "out for delivery":
            client.post(f"{DELIV}/{oid}/advance", headers=ADMIN)  # preparing
            client.post(f"{DELIV}/{oid}/advance", headers=ADMIN)  # out_for_delivery
        else:
            client.post(f"{DELIV}/{oid}/advance", headers=ADMIN)  # delivered
    texts = [m["text"].lower() for m in _sent()[before:]]
    assert any("confirmed" in t for t in texts)
    assert any("out for delivery" in t for t in texts)
    assert any("delivered" in t for t in texts)
    assert all(m["to"] == PHONE for m in _sent()[before:])


def test_no_phone_no_notification(client):
    before = len(_sent())
    client.post(f"{CART}/items", json={"item_id": "plain-dosa"})
    co = client.post(f"{CART}/checkout").json()
    mp = co["mock_payment"]
    # no customer/phone provided
    client.post(f"{MENU}/payments/verify",
                json={"order_id": co["order_id"], "payment_id": mp["payment_id"],
                      "signature": mp["signature"]})
    assert len(_sent()) == before
