"""GET /pay/status/{txn} — публичный браузерный статус для страницы оплаты игры."""


def test_status_pending_no_signature_needed(client, game, make_order):
    order = make_order()
    resp = client.get(f"/pay/status/{order.transaction_id}")  # без подписи — браузер
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert data["transaction_id"] == order.transaction_id
    assert data["expires_at"]


def test_status_success_after_callback(client, db, game, make_order, fake_webhook):
    fake_webhook["state"]["next_response"] = 200
    from conftest import moneta_callback_params
    order = make_order()
    client.post("/pay/moneta/callback", data=moneta_callback_params(order))
    resp = client.get(f"/pay/status/{order.transaction_id}")
    assert resp.json()["status"] == "success"
    assert resp.json()["paid_at"]


def test_status_minimal_fields_no_leak(client, game, make_order):
    """txn полу-публичен: никакого vk_id, суммы, email, описания."""
    order = make_order(vk_id=987654, amount_kop=77700)
    order.receipt_email = "secret@example.com"
    db = None  # (commit в make_order уже был; email не влияет на ответ)
    data = client.get(f"/pay/status/{order.transaction_id}").json()
    assert set(data) == {"transaction_id", "status", "paid_at", "expires_at"}


def test_status_unknown_txn_404(client):
    assert client.get("/pay/status/20990101-000001").status_code == 404


def test_status_bad_format_404(client):
    assert client.get("/pay/status/garbage").status_code == 404
