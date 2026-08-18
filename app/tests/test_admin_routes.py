"""Админ-API: заказы (фильтры, деталь), журнал, настройки, статистика."""

from services.order_service import create_order
from games import GameCreate, create_game


def test_orders_list_and_filters(client, db, game, make_order, admin_headers):
    o1 = make_order(vk_id=1)
    o2 = make_order(vk_id=2, status="success")

    resp = client.get("/pay/api/admin/orders", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2

    resp = client.get("/pay/api/admin/orders?status=success", headers=admin_headers)
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["transaction_id"] == o2.transaction_id

    resp = client.get(f"/pay/api/admin/orders?vk_id=1", headers=admin_headers)
    assert resp.json()["total"] == 1

    resp = client.get(f"/pay/api/admin/orders?txn={o1.transaction_id[-6:]}",
                      headers=admin_headers)
    assert resp.json()["total"] == 1


def test_orders_require_auth(client):
    assert client.get("/pay/api/admin/orders").status_code == 401


def test_order_detail_with_deliveries(client, db, game, make_order,
                                      fake_webhook, admin_headers):
    fake_webhook["state"]["next_response"] = 200
    from services.webhook_dispatcher import redeliver, send_delivery
    order = make_order(status="success")
    d = redeliver(db, order, None)
    send_delivery(db, d, order)

    resp = client.get(f"/pay/api/admin/orders/{order.transaction_id}",
                      headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["order"]["transaction_id"] == order.transaction_id
    assert len(body["deliveries"]) == 1
    assert body["deliveries"][0]["status"] == "delivered"
    assert body["order"]["amount_rub"] == "100.00"


def test_logs_endpoint(client, db, game, make_order, admin_headers):
    make_order()  # создаёт запись order_created
    resp = client.get("/pay/api/admin/logs?event=order_created", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
    item = resp.json()["items"][0]
    assert item["event"] == "order_created"
    assert item["transaction_id"]


def test_settings_toggle_affects_orders(client, db, game, admin_headers):
    from conftest import game_headers
    import json

    # тест-режим выключен — любой vk проходит
    raw = json.dumps({"vk_id": 777, "amount_kop": 100, "description": "x"}).encode()
    assert client.post("/pay/orders", content=raw,
                       headers=game_headers(game, raw)).status_code == 201

    # включаем тест-режим через админку
    resp = client.put("/pay/api/admin/settings",
                      json={"payments_test_mode": True}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["payments_test_mode"] is True

    # теперь чужой vk заблокирован, тестер проходит
    assert client.post("/pay/orders", content=raw,
                       headers=game_headers(game, raw)).status_code == 403
    raw_tester = json.dumps({"vk_id": 400977, "amount_kop": 100,
                             "description": "x"}).encode()
    assert client.post("/pay/orders", content=raw_tester,
                       headers=game_headers(game, raw_tester)).status_code == 201

    # в журнале зафиксировано действие админа
    resp = client.get("/pay/api/admin/logs?event=admin_action", headers=admin_headers)
    assert resp.json()["total"] >= 1


def test_stats_endpoint(client, db, game, make_order, admin_headers):
    make_order(vk_id=1)
    make_order(vk_id=2, status="success")
    resp = client.get("/pay/api/admin/stats", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["period_days"] == 30
    per_game = {g["game_id"]: g for g in body["per_game"]}
    assert "dragons" in per_game
    assert per_game["dragons"]["orders"] == {
        "pending": 1, "success": 1,
    }
    assert body["pending_orders"] == 1


def test_games_list_hides_secrets(client, db, game, admin_headers):
    resp = client.get("/pay/api/admin/games", headers=admin_headers)
    data = resp.json()["items"][0]
    assert "api_key" not in data
    assert "webhook_secret" not in data

    resp = client.get(f"/pay/api/admin/games/{game.game_id}?reveal=true",
                      headers=admin_headers)
    assert resp.json()["api_key"] == game.api_key
