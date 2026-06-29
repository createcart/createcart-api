import pytest
from fastapi.testclient import TestClient

from createcart_api import create_app

ADMIN = {"X-Admin-Key": "createcart-admin"}
T = "test-tenant"
BASE = f"/api/{T}"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Point data at a temp dir and reset the per-tenant registry cache so each
    # test gets a clean, isolated catalog.
    monkeypatch.setenv("CREATECART_DATA_DIR", str(tmp_path))
    from createcart_api import config, deps

    config.settings.data_dir = tmp_path
    config.settings.storage = "sqlite"
    config.settings.db_path = str(tmp_path / "test.db")
    deps._database.cache_clear()
    deps._registry_for.cache_clear()
    return TestClient(create_app())


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_empty_menu(client):
    r = client.get(f"{BASE}/menu")
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_create_requires_admin(client):
    r = client.post(f"{BASE}/items", json={"name": "Dosa", "price": "60"})
    assert r.status_code == 401


def test_create_and_get_item(client):
    r = client.post(
        f"{BASE}/items",
        json={"name": "Plain Dosa", "price": "60", "icon": "🫓", "tags": ["SPECIAL"]},
        headers=ADMIN,
    )
    assert r.status_code == 201
    item = r.json()
    assert item["id"] == "plain-dosa"
    assert item["price"] == "60.00"

    got = client.get(f"{BASE}/items/plain-dosa")
    assert got.status_code == 200
    assert got.json()["name"] == "Plain Dosa"


def test_get_missing_item_404(client):
    assert client.get(f"{BASE}/items/nope").status_code == 404


def test_price_and_availability_and_stock_flow(client):
    client.post(f"{BASE}/items", json={"name": "Dosa", "stock": 2}, headers=ADMIN)

    assert client.post(
        f"{BASE}/items/dosa/price", json={"price": "75"}, headers=ADMIN
    ).json()["price"] == "75.00"

    r = client.post(
        f"{BASE}/items/dosa/stock/adjust", json={"delta": -2}, headers=ADMIN
    )
    assert r.json()["stock"] == 0

    # Now out of stock -> further consumption is a 400.
    r = client.post(
        f"{BASE}/items/dosa/stock/adjust", json={"delta": -1}, headers=ADMIN
    )
    assert r.status_code == 400

    r = client.post(
        f"{BASE}/items/dosa/availability", json={"available": False}, headers=ADMIN
    )
    assert r.json()["available"] is False


def test_filters_and_search(client):
    client.post(
        f"{BASE}/items",
        json={"name": "Plain Dosa", "category": "dosa", "tags": ["SPECIAL"]},
        headers=ADMIN,
    )
    client.post(
        f"{BASE}/items",
        json={"name": "Pulihora", "category": "rice", "available": False},
        headers=ADMIN,
    )
    assert len(client.get(f"{BASE}/items?category=dosa").json()) == 1
    assert len(client.get(f"{BASE}/items?available_only=true").json()) == 1
    assert client.get(f"{BASE}/items?q=puli").json()[0]["id"] == "pulihora"


def test_patch_and_delete(client):
    client.post(f"{BASE}/items", json={"name": "Dosa"}, headers=ADMIN)
    r = client.patch(
        f"{BASE}/items/dosa", json={"description": "crisp"}, headers=ADMIN
    )
    assert r.json()["description"] == "crisp"

    assert client.delete(f"{BASE}/items/dosa", headers=ADMIN).status_code == 204
    assert client.get(f"{BASE}/items/dosa").status_code == 404


def test_combo_rejects_unknown_item(client):
    r = client.post(
        f"{BASE}/combos",
        json={"name": "Combo", "price": "100", "item_ids": ["ghost"]},
        headers=ADMIN,
    )
    assert r.status_code == 404


def test_persistence_across_app_instances(client, tmp_path, monkeypatch):
    client.post(f"{BASE}/items", json={"name": "Pulihora", "price": "50"}, headers=ADMIN)
    # New app instance, same data dir -> item is still there.
    from createcart_api import deps

    deps._registry_for.cache_clear()
    client2 = TestClient(create_app())
    assert client2.get(f"{BASE}/items/pulihora").json()["price"] == "50.00"


def test_tenant_isolation(client):
    client.post(f"{BASE}/items", json={"name": "Dosa"}, headers=ADMIN)
    other = client.get("/api/other-tenant/menu").json()
    assert other["items"] == []


def test_registry_not_process_cached(client):
    """Serverless consistency guard.

    Reads must reflect the database, never a cached in-memory snapshot — that
    snapshot is what made admin menu edits show up late / wrong on the website
    (a different serverless instance kept serving its stale copy). So:
      • each get_registry() must be a fresh instance, and
      • a write made through one must be visible to the very next read,
        with no cache_clear() in between.
    """
    from createcart_api import deps

    assert deps.get_registry(T) is not deps.get_registry(T)

    deps.get_registry(T).add_item(name="Bobbatlu", price="40")
    assert deps.get_registry(T).find_item("bobbatlu") is not None


def test_menu_responses_are_not_cacheable(client):
    """Belt-and-suspenders: no browser/proxy should cache menu data."""
    assert client.get(f"{BASE}/menu").headers.get("cache-control") == "no-store"
