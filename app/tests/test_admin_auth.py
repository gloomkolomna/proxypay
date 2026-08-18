"""VK ID аутентификация админки: vk-login, vk-callback (мок VK), me, allowlist, dev-login."""

import pytest


def test_me_without_token_401(client):
    assert client.get("/pay/api/auth/me").status_code == 401


def test_me_with_allowed_token(client, admin_headers):
    resp = client.get("/pay/api/auth/me", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == {"vk_id": 400977, "ok": True}


def test_me_with_foreign_vk_403(client):
    from auth import create_access_token
    headers = {"Authorization": f"Bearer {create_access_token(666)}"}
    assert client.get("/pay/api/auth/me", headers=headers).status_code == 403


def test_garbage_token_401(client):
    headers = {"Authorization": "Bearer not.a.jwt"}
    assert client.get("/pay/api/auth/me", headers=headers).status_code == 401


def test_vk_login_redirects_to_vk(client):
    resp = client.get("/pay/api/auth/vk-login", follow_redirects=False)
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert location.startswith("https://id.vk.ru/authorize")
    assert "code_challenge_method=S256" in location
    assert "pg_oauth_state" in resp.cookies


def test_vk_callback_denies_foreign_vk(client, monkeypatch):
    import routes.auth_admin as ra

    async def fake_exchange(code, verifier, device_id, state=""):
        return {"access_token": "tok"}

    async def fake_user_info(access_token):
        return {"user_id": 666}

    monkeypatch.setattr(ra, "exchange_vk_code", fake_exchange)
    monkeypatch.setattr(ra, "get_vk_user_info", fake_user_info)

    login = client.get("/pay/api/auth/vk-login", follow_redirects=False)
    state_cookie = login.cookies["pg_oauth_state"]
    resp = client.get(f"/pay/api/auth/vk-callback?code=x&state={state_cookie}")
    assert resp.status_code == 403


def test_vk_callback_success_sets_cookie(client, monkeypatch):
    import routes.auth_admin as ra

    async def fake_exchange(code, verifier, device_id, state=""):
        return {"access_token": "tok"}

    async def fake_user_info(access_token):
        return {"user_id": 400977}

    monkeypatch.setattr(ra, "exchange_vk_code", fake_exchange)
    monkeypatch.setattr(ra, "get_vk_user_info", fake_user_info)

    login = client.get("/pay/api/auth/vk-login", follow_redirects=False)
    state_cookie = login.cookies["pg_oauth_state"]

    resp = client.get(f"/pay/api/auth/vk-callback?code=x&state={state_cookie}",
                      follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "/pay/admin" in resp.headers["location"]
    assert "pg_admin_token" in resp.cookies
    # токен из cookie работает как авторизация
    me = client.get("/pay/api/auth/me")
    assert me.status_code == 200


def test_vk_callback_without_cookies_400(client):
    resp = client.get("/pay/api/auth/vk-callback?code=x")
    assert resp.status_code == 400


def test_dev_login_disabled_in_production(client):
    assert client.post("/pay/api/auth/dev-login", json={"vk_id": 400977}).status_code == 404


def test_dev_login_in_dev_env(client, monkeypatch):
    import config
    monkeypatch.setattr(config, "DEV_LOGIN_ENABLED", True)
    resp = client.post("/pay/api/auth/dev-login", json={"vk_id": 400977})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    me = client.get("/pay/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200


def test_logout_clears_cookie(client, monkeypatch):
    import routes.auth_admin as ra

    async def fake_exchange(code, verifier, device_id, state=""):
        return {"access_token": "tok"}

    async def fake_user_info(access_token):
        return {"user_id": 400977}

    monkeypatch.setattr(ra, "exchange_vk_code", fake_exchange)
    monkeypatch.setattr(ra, "get_vk_user_info", fake_user_info)

    login = client.get("/pay/api/auth/vk-login", follow_redirects=False)
    state_cookie = login.cookies["pg_oauth_state"]
    client.get(f"/pay/api/auth/vk-callback?code=x&state={state_cookie}",
               follow_redirects=False)
    assert client.get("/pay/api/auth/me").status_code == 200  # cookie работает

    resp = client.post("/pay/api/auth/logout")
    assert resp.status_code == 200
    assert client.get("/pay/api/auth/me").status_code == 401  # cookie сброшена
