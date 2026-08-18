"""Реестр игр: CRUD-валидация, секреты, ротация, is_active, запрет удаления с заказами."""

from games import GameCreate, create_game, get_game, rotate_secret


def _payload(**kw):
    body = {
        "game_id": "newgame",
        "name": "Новая игра",
        "webhook_url": "http://127.0.0.1:8005/api/payment/webhook",
        "success_url": "https://example.com/ok",
        "fail_url": "https://example.com/fail",
    }
    body.update(kw)
    return body


def test_create_game_generates_secrets(client, db, admin_headers):
    resp = client.post("/pay/api/admin/games", json=_payload(),
                       headers=admin_headers)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["api_key"] and len(data["api_key"]) >= 32
    assert data["webhook_secret"] and len(data["webhook_secret"]) >= 32
    assert data["is_active"] is True
    assert data["receipt"]["tax_code"] == "1105"


def test_create_game_requires_auth(client):
    assert client.post("/pay/api/admin/games", json=_payload()).status_code == 401


def test_duplicate_game_id_rejected(client, db, game, admin_headers):
    resp = client.post("/pay/api/admin/games", json=_payload(game_id="dragons"),
                       headers=admin_headers)
    assert resp.status_code == 422


def test_bad_game_id_rejected(client, admin_headers):
    for bad in ("Dragons", "lost-world", "драконы", ""):
        resp = client.post("/pay/api/admin/games", json=_payload(game_id=bad),
                           headers=admin_headers)
        assert resp.status_code == 422, bad


def test_bad_url_rejected(client, admin_headers):
    resp = client.post("/pay/api/admin/games",
                       json=_payload(webhook_url="ftp://nope"),
                       headers=admin_headers)
    assert resp.status_code == 422


def test_update_game(client, db, game, admin_headers):
    resp = client.put(
        f"/pay/api/admin/games/{game.game_id}",
        json={
            "name": "Драконы 2", "description_prefix": "[Драконы]",
            "webhook_url": game.webhook_url,
            "success_url": "https://example.com/done2",
            "fail_url": game.fail_url,
            "is_active": False,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 200
    db.refresh(game)
    assert game.name == "Драконы 2"
    assert game.is_active is False


def test_rotate_secrets(client, db, game, admin_headers):
    old_api, old_secret = game.api_key, game.webhook_secret
    resp = client.post(f"/pay/api/admin/games/{game.game_id}/rotate",
                       json={"which": "api_key"}, headers=admin_headers)
    assert resp.status_code == 200
    new_api = resp.json()["new_value"]
    assert new_api != old_api and len(new_api) >= 32
    db.refresh(game)
    assert game.api_key == new_api
    assert game.webhook_secret == old_secret  # второй секрет не тронут

    resp = client.post(f"/pay/api/admin/games/{game.game_id}/rotate",
                       json={"which": "webhook_secret"}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["new_value"] != old_secret


def test_rotate_bad_which(client, game, admin_headers):
    resp = client.post(f"/pay/api/admin/games/{game.game_id}/rotate",
                       json={"which": "nope"}, headers=admin_headers)
    assert resp.status_code == 422


def test_delete_game_without_orders_ok(client, db, admin_headers):
    create_game(db, GameCreate(**_payload()))
    resp = client.delete("/pay/api/admin/games/newgame", headers=admin_headers)
    assert resp.status_code == 200
    assert get_game(db, "newgame") is None


def test_delete_game_with_orders_forbidden(client, db, game, make_order, admin_headers):
    make_order()
    resp = client.delete(f"/pay/api/admin/games/{game.game_id}",
                         headers=admin_headers)
    assert resp.status_code == 409
    assert get_game(db, game.game_id) is not None


def test_disabled_game_blocks_orders(client, db, game, admin_headers):
    from conftest import game_headers
    import json
    game.is_active = False
    db.commit()
    raw = json.dumps({"vk_id": 1, "amount_kop": 100,
                      "description": "x"}).encode()
    resp = client.post("/pay/orders", content=raw,
                       headers=game_headers(game, raw))
    assert resp.status_code == 403
