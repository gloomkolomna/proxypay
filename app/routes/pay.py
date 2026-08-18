"""GET /pay/{txn} — HTML-страница с auto-submit формой в MONETA.
Перенос текущего GET /api/payment/pay/{order_id} драконов (план §3)."""

import html as html_mod
import json
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

import config
from db import get_db
from games import get_game
from models import Order, log_event
from moneta import build_payment_signature, format_amount
from services.order_service import is_expired

router = APIRouter()

TXN_RE = re.compile(r"^\d{8}-\d{6}$")

_DARK_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Оплата</title></head>
<body style="background:#1a1a2e;color:#e0d6c2;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
<div style="text-align:center">
<p>{message}</p>
</div>
</body></html>"""


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


def _build_inventory(order: Order, game) -> str:
    """MNT_CUSTOM2 — инвентарь чека (54-ФЗ), 1:1 с драконьим форматом."""
    items = []
    raw = None
    if order.receipt_items_json:
        try:
            raw = json.loads(order.receipt_items_json)
        except (ValueError, TypeError):
            raw = None
    if raw:
        for it in raw:
            items.append({
                "n": str(it.get("name", "Товар"))[:200],
                "p": format_amount(int(it.get("price_kop", order.amount_kop))),
                "q": str(int(it.get("quantity", 1))),
                "t": game.tax_code,
                "pm": game.payment_method,
                "po": game.payment_object,
            })
    else:
        items.append({
            "n": order.description or "Товар",
            "p": format_amount(order.amount_kop),
            "q": "1",
            "t": game.tax_code,
            "pm": game.payment_method,
            "po": game.payment_object,
        })
    inventory: dict = {"items": items}
    if order.receipt_email:
        inventory["customer"] = order.receipt_email
    return json.dumps(inventory, ensure_ascii=False, separators=(",", ":"))


@router.get("/pay/{transaction_id}")
def payment_redirect_page(transaction_id: str, request: Request,
                          db: Session = Depends(get_db)):
    client_ip = _client_ip(request)
    if not TXN_RE.match(transaction_id or ""):
        return HTMLResponse(_page("Заказ не найден"), status_code=404)

    order = db.query(Order).filter(Order.transaction_id == transaction_id).first()
    if not order:
        log_event(db, "pay_not_found", transaction_id, detail=f"ip={client_ip}")
        return HTMLResponse(_page("Заказ не найден"), status_code=404)
    if is_expired(order):
        log_event(db, "pay_expired", transaction_id, order.game_id,
                  detail=f"ip={client_ip}")
        return HTMLResponse(
            _page("Заказ просрочен<br><small>Время оплаты истекло. Создай новый заказ.</small>"),
            status_code=410,
        )
    if order.status != "pending":
        log_event(db, f"pay_already_{order.status}", transaction_id, order.game_id,
                  detail=f"ip={client_ip}")
        return HTMLResponse(_page(f"Заказ уже {order.status}"), status_code=400)

    game = get_game(db, order.game_id)
    if not game:
        log_event(db, "pay_game_missing", transaction_id, order.game_id,
                  detail=f"ip={client_ip}")
        return HTMLResponse(_page("Заказ временно недоступен"), status_code=500)

    mnt_id = config.MONETA_MNT_ID
    mnt_trx = order.transaction_id
    amount_str = format_amount(order.amount_kop)
    test_mode = "1" if config.MONETA_TEST_MODE else "0"
    signature = build_payment_signature(
        mnt_id, mnt_trx, amount_str, config.MONETA_INTEGRITY_CODE, test_mode,
    )
    description = f"{game.description_prefix} {order.description}".strip()
    custom2 = _build_inventory(order, game)

    fields = [
        ("MNT_ID", mnt_id),
        ("MNT_TRANSACTION_ID", mnt_trx),
        ("MNT_CURRENCY_CODE", "RUB"),
        ("MNT_AMOUNT", amount_str),
        ("MNT_DESCRIPTION", description),
        ("MNT_TEST_MODE", test_mode),
        ("MNT_CUSTOM2", custom2),
        ("MNT_SUCCESS_URL", f"{config.SITE_URL}/pay/success?txn={mnt_trx}"),
        ("MNT_FAIL_URL", f"{config.SITE_URL}/pay/fail?txn={mnt_trx}"),
        ("MNT_RETURN_URL", f"{config.SITE_URL}/pay/return?txn={mnt_trx}"),
    ]
    if not config.MONETA_NO_SIGNATURE_FORM:
        fields.append(("MNT_SIGNATURE", signature))

    inputs = "\n".join(
        f'<input type="hidden" name="{k}" value="{html_mod.escape(str(v), quote=True)}" />'
        for k, v in fields
    )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Оплата</title></head>
<body style="background:#1a1a2e;color:#e0d6c2;font-family:sans-serif;display:flex;align-content:center;justify-content:center;align-items:center;height:100vh;margin:0">
<div style="text-align:center">
<p>Перенаправление на страницу оплаты...</p>
<form id="f" action="{config.moneta_assistant_url()}" method="POST">
{inputs}
</form>
<script>document.getElementById('f').submit();</script>
</div>
</body></html>"""

    log_event(db, "moneta_form_created", transaction_id, order.game_id,
              detail=(f"ip={client_ip} mnt_id={mnt_id} amount={amount_str} "
                      f"test_mode={test_mode}"))
    return HTMLResponse(html)


def _page(message: str) -> str:
    return _DARK_PAGE.replace("{message}", message)
