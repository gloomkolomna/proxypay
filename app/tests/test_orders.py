"""POST /pay/orders и GET /pay/orders/{txn}: аутентификация, валидация, тест-блок."""

import re
import time

from conftest import game_headers, sign_body


def _payload(vk_id=123, amount_kop=10000, **kw):
    body = {"vk_id": vk_id, "amount_kop": amount_kop,
            "description": "Набор «Стартовый»"}
    body.update(kw)
    return body


def _post(client, game, payload, **kw):
    import json
    raw = json.dumps(payload).encode()
    return client.post("/pay/orders", content=raw,
                       headers=game_headers(game, raw, **kw))


def test_create_order_ok(client, game):
    resp = _post(client, game, _payload())
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert re.match(r"^\d{8}-\d{6}$", data["transaction_id"])
    assert data["payment_url"].endswith(f"/pay/{data['transaction_id']}")
    assert data["amount_kop"] == 10000
    assert data["expires_at"]


def test_create_order_missing_game_id(client, game):
    resp = client.post("/pay/orders", json=_payload())
    assert resp.status_code == 401


def test_create_order_unknown_game(client, game):
    import json
    raw = json.dumps(_payload()).encode()
    headers = game_headers(game, raw)
    headers["X-Game-Id"] = "unknown"
    resp = client.post("/pay/orders", content=raw, headers=headers)
    assert resp.status_code == 401


def test_create_order_disabled_game(client, db, game):
    game.is_active = False
    db.commit()
    resp = _post(client, game, _payload())
    assert resp.status_code == 403


def test_create_order_bad_signature(client, game):
    resp = _post(client, game, _payload(), bad_sig=True)
    assert resp.status_code == 401


def test_create_order_missing_timestamp(client, game):
    import json
    raw = json.dumps(_payload()).encode()
    headers = game_headers(game, raw)
    del headers["X-Timestamp"]
    resp = client.post("/pay/orders", content=raw, headers=headers)
    assert resp.status_code == 401


def test_create_order_stale_timestamp(client, game):
    resp = _post(client, game, _payload(), timestamp=int(time.time()) - 3600)
    assert resp.status_code == 401


def test_create_order_bad_payload(client, game):
    resp = _post(client, game, _payload(amount_kop=0))
    assert resp.status_code == 422


def test_create_order_bad_email(client, game):
    resp = _post(client, game, _payload(receipt_email="not-an-email"))
    assert resp.status_code == 422


def test_test_block_blocks_others_but_tester(client, db, game):
    from services import settings_service
    settings_service.set_payments_test_mode(db, True, None)
    resp = _post(client, game, _payload(vk_id=999))
    assert resp.status_code == 403
    assert resp.json()["error"] == "test_blocked"

    tester = settings_service.payments_test_vk_id(db)
    resp = _post(client, game, _payload(vk_id=tester))
    assert resp.status_code == 201


def test_receipt_items_stored_and_used(client, db, game):
    resp = _post(client, game, _payload(
        receipt_items=[{"name": "Пин-код", "price_kop": 5000, "quantity": 2}],
    ))
    assert resp.status_code == 201
    from models import Order
    order = db.query(Order).filter_by(
        transaction_id=resp.json()["transaction_id"]).first()
    assert order is not None
    assert "Пин-код" in (order.receipt_items_json or "")


def test_get_order_status_ok(client, game):
    created = _post(client, game, _payload())
    txn = created.json()["transaction_id"]

    import json
    raw = b""
    resp = client.get(f"/pay/orders/{txn}",
                      headers=game_headers(game, raw))
    assert resp.status_code == 200
    data = resp.json()
    assert data["transaction_id"] == txn
    assert data["status"] == "pending"
    assert "vk_id" not in data  # план §3: vk_id не отдаём


def test_get_order_status_not_found(client, game):
    raw = b""
    resp = client.get("/pay/orders/20990101-000001",
                      headers=game_headers(game, raw))
    assert resp.status_code == 404
