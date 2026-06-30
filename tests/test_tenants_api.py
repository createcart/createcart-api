import pytest
from fastapi.testclient import TestClient

from createcart_api import create_app

ADMIN = {"X-Admin-Key": "createcart-admin"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATECART_DATA_DIR", str(tmp_path))
    from createcart_api import config, deps

    config.settings.data_dir = tmp_path
    config.settings.storage = "sqlite"
    config.settings.db_path = str(tmp_path / "test.db")
    deps._database.cache_clear()
    deps._registry_for.cache_clear()
    return TestClient(create_app())


def test_list_requires_admin(client):
    assert client.get("/api/_tenants").status_code == 401


def test_create_assigns_sequential_ids(client):
    a = client.post("/api/_tenants", json={"name": "alpha"}, headers=ADMIN)
    b = client.post("/api/_tenants", json={"name": "beta"}, headers=ADMIN)
    assert a.json()["id"] == 0 and a.json()["name"] == "alpha"
    assert b.json()["id"] == 1
    # idempotent
    assert client.post("/api/_tenants", json={"name": "alpha"}, headers=ADMIN).json()["id"] == 0


def test_onboard_with_password_and_base_url(client):
    r = client.post("/api/_tenants",
                    json={"name": "gamma", "password": "secret123",
                          "base_url": "https://api.example.com"}, headers=ADMIN)
    assert r.json()["id"] == 0
    assert r.json()["base_url"] == "https://api.example.com"
    assert r.json()["has_password"] is True
    got = client.get("/api/_tenants/gamma", headers=ADMIN).json()
    assert got["base_url"] == "https://api.example.com"
    assert got["has_password"] is True


def test_explicit_id_onboarding(client):
    r = client.post("/api/_tenants", json={"name": "alpha", "id": 5}, headers=ADMIN)
    assert r.json()["id"] == 5


def test_list_and_get(client):
    client.post("/api/_tenants", json={"name": "alpha"}, headers=ADMIN)
    client.post("/api/_tenants", json={"name": "beta", "base_url": "http://b"},
                headers=ADMIN)
    lst = client.get("/api/_tenants", headers=ADMIN).json()
    assert [(t["id"], t["name"]) for t in lst] == [(0, "alpha"), (1, "beta")]
    assert client.get("/api/_tenants/beta", headers=ADMIN).json()["base_url"] == "http://b"


def test_get_unknown_404(client):
    assert client.get("/api/_tenants/ghost", headers=ADMIN).status_code == 404


def test_invalid_name_rejected(client):
    assert client.post("/api/_tenants", json={"name": "Bad Name"}, headers=ADMIN).status_code == 400


def test_using_a_tenant_registers_it(client):
    # creating a menu item under a new tenant should make it show up in the registry
    client.post("/api/gamma/items", json={"name": "X", "price": "1"}, headers=ADMIN)
    names = [t["name"] for t in client.get("/api/_tenants", headers=ADMIN).json()]
    assert "gamma" in names


def test_delete_requires_admin(client):
    client.post("/api/_tenants", json={"name": "alpha"}, headers=ADMIN)
    assert client.delete("/api/_tenants/alpha").status_code == 401


def test_delete_tenant_removes_it_and_its_data(client):
    # onboard + add a menu item (creates per-tenant tables)
    client.post("/api/_tenants", json={"name": "alpha", "password": "p"}, headers=ADMIN)
    client.post("/api/alpha/items", json={"name": "Dosa", "price": "60"}, headers=ADMIN)
    assert client.get("/api/alpha/items").json()  # has data

    r = client.delete("/api/_tenants/alpha", headers=ADMIN)
    assert r.status_code == 204
    # gone from the registry, and its data is gone (fresh empty tables on re-touch)
    assert client.get("/api/_tenants/alpha", headers=ADMIN).status_code == 404
    assert "alpha" not in [t["name"] for t in client.get("/api/_tenants", headers=ADMIN).json()]
    assert client.get("/api/alpha/items").json() == []


def test_delete_unknown_tenant_404(client):
    assert client.delete("/api/_tenants/ghost", headers=ADMIN).status_code == 404
