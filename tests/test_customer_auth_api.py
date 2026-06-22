import pytest
from fastapi.testclient import TestClient

from createcart_api import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATECART_DATA_DIR", str(tmp_path))
    from createcart_api import config, deps

    config.settings.data_dir = tmp_path
    config.settings.storage = "sqlite"
    config.settings.db_path = str(tmp_path / "test.db")
    config.settings.auth_provider = "mock"
    deps._database.cache_clear()
    deps._auth_service.cache_clear()
    return TestClient(create_app())


def test_auth_config_mock(client):
    assert client.get("/api/auth/config").json() == {"provider": "mock"}


def test_google_login_mock_demo(client):
    r = client.post("/api/auth/google", json={"id_token": "mock"})
    assert r.status_code == 200
    u = r.json()
    assert u["provider"] == "mock"
    assert u["email"] == "demo@example.com"
    assert u["name"] == "Demo User"


def test_google_login_custom_mock_token(client):
    from createcart_auth import MockProvider

    token = MockProvider().make_token(email="asha@gmail.com", name="Asha")
    u = client.post("/api/auth/google", json={"id_token": token}).json()
    assert u["email"] == "asha@gmail.com" and u["name"] == "Asha"


def test_bad_token_rejected(client):
    assert client.post("/api/auth/google",
                       json={"id_token": "garbage"}).status_code == 401


def test_config_reports_google_when_configured(client, monkeypatch):
    from createcart_api import config, deps

    config.settings.auth_provider = "google"
    config.settings.google_client_id = "abc.apps.googleusercontent.com"
    deps._auth_service.cache_clear()
    cfg = client.get("/api/auth/config").json()
    assert cfg["provider"] == "google"
    assert cfg["client_id"] == "abc.apps.googleusercontent.com"
    # reset so other tests keep using mock
    config.settings.auth_provider = "mock"
    deps._auth_service.cache_clear()
