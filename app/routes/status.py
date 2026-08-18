"""GET /pay/status/{txn} — публичный статус заказа для браузерной страницы оплаты игры.

Страница статуса в игре (напр., /dragons/payment/status?txn=...) опрашивает этот
эндпоинт и показывает результат + ссылку обратно на сообщество/бота.

Отдаём МИНИМУМ полей: никакого vk_id, суммы, email — txn полу-публичен (дата +
последовательный счётчик), перечисление не должно ничего утечь.
Подпись не требуется — эндпоинт для браузера, ключей игры там нет.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from db import get_db
from models import Order, parse_utc, to_msk_iso
from routes.pay import TXN_RE

router = APIRouter()


@router.get("/pay/status/{transaction_id}")
def public_order_status(transaction_id: str, db: Session = Depends(get_db)):
    if not TXN_RE.match(transaction_id or ""):
        return JSONResponse({"error": "not found"}, status_code=404)
    order = db.query(Order).filter(Order.transaction_id == transaction_id).first()
    if not order:
        return JSONResponse({"error": "not found"}, status_code=404)
    return {
        "transaction_id": order.transaction_id,
        "status": order.status,               # pending|success|cancelled|failed
        "paid_at": to_msk_iso(parse_utc(order.completed_at)),
        "expires_at": to_msk_iso(parse_utc(order.expires_at)),
    }
