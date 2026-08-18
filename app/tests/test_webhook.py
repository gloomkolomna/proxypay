"""Доставка вебхуков: 2xx/404/5xx, ретраи, исчерпание, dispatch_due, redeliver."""

from datetime import timedelta

from models import WebhookDelivery, utc_iso, utcnow
from services import webhook_dispatcher as wd


def _delivery(db, order):
    return db.query(WebhookDelivery).filter_by(order_id=order.id).first()


def test_delivered_on_2xx(db, game, make_order, fake_webhook):
    fake_webhook["state"]["next_response"] = 200
    order = make_order()
    d = wd.redeliver(db, order, None)
    wd.send_delivery(db, d, order)
    db.refresh(d)
    assert d.status == "delivered"
    assert d.attempt == 1
    assert d.delivered_at is not None


def test_404_is_retryable(db, game, make_order, fake_webhook):
    """404 = гонка «вебхук раньше сохранения txn» → ретрай, не отказ."""
    fake_webhook["state"]["next_response"] = 404
    order = make_order()
    d = wd.redeliver(db, order, None)
    wd.send_delivery(db, d, order)
    db.refresh(d)
    assert d.status == "queued"
    assert d.attempt == 1
    assert d.next_retry_at is not None


def test_5xx_is_retryable_with_exponential_delay(db, game, make_order, fake_webhook):
    fake_webhook["state"]["next_response"] = 500
    order = make_order()
    d = wd.redeliver(db, order, None)
    wd.send_delivery(db, d, order)   # attempt 1 → +60s
    wd.send_delivery(db, d, order)   # attempt 2 → +300s
    db.refresh(d)
    assert d.status == "queued"
    assert d.attempt == 2
    from models import parse_utc
    delay = parse_utc(d.next_retry_at) - utcnow()
    assert 290 <= delay.total_seconds() <= 310


def test_attempts_exhausted_marks_failed(db, game, make_order, fake_webhook):
    import config
    fake_webhook["state"]["next_response"] = 500
    order = make_order()
    d = wd.redeliver(db, order, None)
    d.attempt = len(config.WEBHOOK_RETRY_DELAYS) + 1  # 1 первичная + 6 ретраев сделаны
    db.commit()
    wd.send_delivery(db, d, order)
    db.refresh(d)
    assert d.status == "failed"
    assert d.next_retry_at is None


def test_network_error_is_retryable(db, game, make_order, fake_webhook):
    fake_webhook["state"]["raise_exc"] = ConnectionError("boom")
    order = make_order()
    d = wd.redeliver(db, order, None)
    wd.send_delivery(db, d, order)
    db.refresh(d)
    assert d.status == "queued"
    assert "boom" in (d.last_error or "")


def test_dispatch_due_sends_only_due(db, game, make_order, fake_webhook):
    fake_webhook["state"]["next_response"] = 200
    order = make_order()
    d1 = wd.redeliver(db, order, None)          # due (next = now)
    d2 = wd.redeliver(db, order, None)          # not due
    d2.next_retry_at = utc_iso(utcnow() + timedelta(hours=1))
    db.commit()

    sent = wd.dispatch_due(db)
    assert sent == 1
    db.refresh(d1)
    db.refresh(d2)
    assert d1.status == "delivered"
    assert d2.status == "queued"


def test_payload_shape_and_signature(db, game, make_order, fake_webhook):
    import json
    fake_webhook["state"]["next_response"] = 200
    order = make_order(status="success")
    d = wd.redeliver(db, order, None)
    wd.send_delivery(db, d, order)
    call = fake_webhook["calls"][0]
    payload = json.loads(call["body"])
    assert set(payload) == {
        "transaction_id", "game_id", "vk_id", "amount_kop",
        "status", "paid_at", "moneta_operation_id",
    }
    assert payload["vk_id"] == order.vk_id
    assert payload["amount_kop"] == order.amount_kop


def test_redeliver_endpoint_admin_only(client, game, make_order):
    order = make_order(status="success")
    resp = client.post(f"/pay/api/admin/orders/{order.transaction_id}/redeliver")
    assert resp.status_code == 401


def test_redeliver_endpoint_creates_delivery(client, db, game, make_order,
                                             fake_webhook, admin_headers):
    fake_webhook["state"]["next_response"] = 200
    order = make_order(status="success")
    resp = client.post(f"/pay/api/admin/orders/{order.transaction_id}/redeliver",
                       headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["delivery"]["status"] == "delivered"
