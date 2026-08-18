"""GET /pay/{txn} — HTML-форма MONETA: форматы, статусы, чек (MNT_CUSTOM2)."""

import json
from datetime import timedelta

from models import utc_iso, utcnow


def test_pay_bad_format_404(client):
    assert client.get("/pay/not-a-txn").status_code == 404
    # /pay/success — это редирект, а не страница заказа
    assert client.get("/pay/success", follow_redirects=False).status_code in (302, 307)


def test_pay_not_found(client):
    assert client.get("/pay/20990101-000001").status_code == 404


def test_pay_pending_renders_form(client, game, make_order):
    order = make_order(amount_kop=15000)
    resp = client.get(f"/pay/{order.transaction_id}")
    assert resp.status_code == 200
    html = resp.text
    assert "demo.moneta.ru/assistant.htm" in html  # MONETA_TEST_MODE=1
    assert f'name="MNT_TRANSACTION_ID" value="{order.transaction_id}"' in html
    assert 'name="MNT_AMOUNT" value="150.00"' in html
    assert "MNT_SIGNATURE" in html
    assert "[Драконы]" in html  # description_prefix
    # чек: одна позиция из description, tax_code из карточки игры
    custom2 = _field(html, "MNT_CUSTOM2")
    inv = json.loads(custom2.replace("&quot;", '"').replace("&amp;", "&"))
    assert inv["items"][0]["t"] == game.tax_code
    assert inv["items"][0]["pm"] == "full_payment"


def test_pay_receipt_email_in_custom2(client, db, game, make_order):
    order = make_order()
    order.receipt_email = "buyer@example.com"
    db.commit()
    html = client.get(f"/pay/{order.transaction_id}").text
    custom2 = _field(html, "MNT_CUSTOM2")
    assert "buyer@example.com" in custom2


def test_pay_expired_410(client, db, make_order):
    order = make_order()
    order.expires_at = utc_iso(utcnow() - timedelta(minutes=1))
    db.commit()
    assert client.get(f"/pay/{order.transaction_id}").status_code == 410


def test_pay_already_success_400(client, db, make_order):
    order = make_order(status="success")
    assert client.get(f"/pay/{order.transaction_id}").status_code == 400


def test_pay_success_url_contains_txn(client, game, make_order):
    order = make_order()
    html = client.get(f"/pay/{order.transaction_id}").text
    assert f"/pay/success?txn={order.transaction_id}" in html
    assert f"/pay/fail?txn={order.transaction_id}" in html


def _field(html: str, name: str) -> str:
    marker = f'name="{name}" value="'
    start = html.index(marker) + len(marker)
    end = html.index('"', start)
    return html[start:end]
