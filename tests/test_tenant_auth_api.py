"""Per-tenant password auth: client admins use their own password (X-Tenant-Key)."""

import pytest
from fastapi.testclient import TestClient

from createcart_api import create_app

PLATFORM = {"X-Admin-Key": "createcart-admin"}
T = "acme"


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
    # platform onboards a tenant with a password + base url
    c.post("/api/_tenants",
           json={"name": T, "password": "acme-pass", "base_url": "http://localhost:8000"},
           headers=PLATFORM)
    return c


def test_me_validates_correct_password(client):
    r = client.get(f"/api/{T}/admin/me", headers={"X-Tenant-Key": "acme-pass"})
    assert r.status_code == 200
    assert r.json()["tenant"] == T
    assert r.json()["base_url"] == "http://localhost:8000"


def test_me_rejects_wrong_password(client):
    assert client.get(f"/api/{T}/admin/me",
                      headers={"X-Tenant-Key": "nope"}).status_code == 401
    assert client.get(f"/api/{T}/admin/me").status_code == 401


def test_tenant_password_authorizes_menu_write(client):
    r = client.post(f"/api/{T}/items", json={"name": "Widget", "price": "10"},
                    headers={"X-Tenant-Key": "acme-pass"})
    assert r.status_code == 201


def test_wrong_tenant_password_blocks_write(client):
    r = client.post(f"/api/{T}/items", json={"name": "Widget", "price": "10"},
                    headers={"X-Tenant-Key": "wrong"})
    assert r.status_code == 401


def test_platform_key_still_superuser(client):
    r = client.post(f"/api/{T}/items", json={"name": "Widget", "price": "10"},
                    headers=PLATFORM)
    assert r.status_code == 201


def test_one_tenant_password_cannot_touch_another(client):
    # onboard a second tenant with a different password
    client.post("/api/_tenants", json={"name": "other", "password": "other-pass"},
                headers=PLATFORM)
    # acme's password must not authorize writes to 'other'
    r = client.post("/api/other/items", json={"name": "X", "price": "1"},
                    headers={"X-Tenant-Key": "acme-pass"})
    assert r.status_code == 401
