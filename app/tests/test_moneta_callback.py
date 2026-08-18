"""POST /pay/moneta/callback: подпись, IP, суммы, идемпотентность, paid-after-cancelled."""

from models import WebhookDelivery

from conftest import moneta_callback_params


def test_callback_success(client, db, game, make_order, fake_webhook):
    fake_webhook["state"]["next_response"] = 200
    order = make_order()
    resp = client.post("/pay/moneta/callback", data=moneta_callback_params(order))
    assert resp.status_code == 200
    assert resp.text == "SUCCESS"

    db.refresh(order)
    assert order.status == "success"
    assert order.moneta_operation_id == "777001"
    delivery = db.query(WebhookDelivery).filter_by(order_id=order.id).first()
    assert delivery is not None
    # вебхук ушёл немедленно (заглушка ответила 200)
    assert delivery.status == "delivered"
    assert len(fake_webhook["calls"]) == 1
    # подпись исходящего вебхука валидна секретом игры
    import json
    from security import verify_signature
    call = fake_webhook["calls"][0]
    assert verify_signature(call["body"], game.webhook_secret,
                            call["headers"]["X-Pay-Signature"])
    payload = json.loads(call["body"])
    assert payload["transaction_id"] == order.transaction_id
    assert payload["status"] == "success"
    assert payload["moneta_operation_id"] == "777001"


def test_callback_bad_signature(client, make_order):
    order = make_order()
    params = moneta_callback_params(order)
    params["MNT_SIGNATURE"] = "0" * 32
    resp = client.post("/pay/moneta/callback", data=params)
    assert resp.status_code == 400


def test_callback_order_not_found(client, game, make_order):
    order = make_order()
    params = moneta_callback_params(order)
    params["MNT_TRANSACTION_ID"] = "20990101-000009"
    resp = client.post("/pay/moneta/callback", data=params)
    assert resp.status_code == 400


def test_callback_amount_mismatch(client, make_order):
    order = make_order(amount_kop=10000)
    resp = client.post("/pay/moneta/callback",
                       data=moneta_callback_params(order, amount_kop=9000))
    assert resp.status_code == 400


def test_callback_idempotent(client, db, game, make_order, fake_webhook):
    fake_webhook["state"]["next_response"] = 500  # недоставлен — ретраи
    order = make_order()
    first = client.post("/pay/moneta/callback", data=moneta_callback_params(order))
    assert first.text == "SUCCESS"
    deliveries_after_first = db.query(WebhookDelivery).filter_by(order_id=order.id).count()

    second = client.post("/pay/moneta/callback", data=moneta_callback_params(order))
    assert second.text == "SUCCESS"
    deliveries_after_second = db.query(WebhookDelivery).filter_by(order_id=order.id).count()
    # повторный колбэк не плодит новые доставки
    assert deliveries_after_first == deliveries_after_second == 1


def test_callback_paid_after_cancelled(client, db, game, make_order, fake_webhook):
    """Оплачен отменённый заказ → всё равно success + вебхук (план §0)."""
    fake_webhook["state"]["next_response"] = 200
    order = make_order(status="cancelled")
    resp = client.post("/pay/moneta/callback", data=moneta_callback_params(order))
    assert resp.text == "SUCCESS"
    db.refresh(order)
    assert order.status == "success"
    assert db.query(WebhookDelivery).filter_by(order_id=order.id).count() == 1
    from models import GatewayLog
    assert db.query(GatewayLog).filter_by(
        event="order_success", transaction_id=order.transaction_id).first() is not None


def test_callback_no_sig_mode_bad_ip(client, db, monkeypatch, make_order):
    import config
    monkeypatch.setattr(config, "MONETA_NO_SIGNATURE_CALLBACK", True)
    monkeypatch.setattr(config, "MONETA_CALLBACK_IPS", ["193.176.92.70"])
    order = make_order()
    params = moneta_callback_params(order)
    params.pop("MNT_SIGNATURE")
    resp = client.post("/pay/moneta/callback", data=params,
                       headers={"X-Forwarded-For": "1.2.3.4"})
    assert resp.status_code == 400


def test_callback_no_sig_mode_good_ip(client, db, monkeypatch, make_order, fake_webhook):
    import config
    fake_webhook["state"]["next_response"] = 200
    monkeypatch.setattr(config, "MONETA_NO_SIGNATURE_CALLBACK", True)
    monkeypatch.setattr(config, "MONETA_CALLBACK_IPS", ["193.176.92.70"])
    order = make_order()
    params = moneta_callback_params(order)
    params.pop("MNT_SIGNATURE")
    resp = client.post("/pay/moneta/callback", data=params,
                       headers={"X-Forwarded-For": "193.176.92.70"})
    assert resp.status_code == 200
    db.refresh(order)
    assert order.status == "success"
