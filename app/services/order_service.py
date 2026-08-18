"""Заказы шлюза: генерация txn, создание, отмена просрочки, mark_success
(+ постановка вебхука в ОДНОЙ транзакции — план §3)."""

from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import config
from games import GameRegistry
from models import Order, WebhookDelivery, log_event, parse_utc, to_msk_log, utc_iso, utcnow


def generate_txn(db: Session) -> str:
    """YYYYMMDD-NNNNNN — пер-дневной счётчик, retry при UNIQUE-конфликте."""
    prefix = utcnow().strftime("%Y%m%d")
    for _ in range(5):
        last = (
            db.query(Order.transaction_id)
            .filter(Order.transaction_id.like(f"{prefix}-%"))
            .order_by(Order.transaction_id.desc())
            .first()
        )
        next_num = 1
        if last and last[0]:
            try:
                next_num = int(last[0].split("-")[-1]) + 1
            except ValueError:
                next_num = 1
        txn = f"{prefix}-{next_num:06d}"
        exists = db.query(Order.id).filter(Order.transaction_id == txn).first()
        if exists:
            continue
        return txn
    raise RuntimeError("не удалось сгенерировать transaction_id")


def create_order(db: Session, game: GameRegistry, *, vk_id: int, amount_kop: int,
                 description: str, receipt_email: str | None,
                 receipt_items_json: str | None) -> Order:
    order = Order(
        transaction_id=generate_txn(db),
        game_id=game.game_id,
        vk_id=vk_id,
        amount_kop=amount_kop,
        description=description,
        receipt_email=receipt_email,
        receipt_items_json=receipt_items_json,
        status="pending",
        created_at=utc_iso(utcnow()),
        expires_at=utc_iso(utcnow() + timedelta(minutes=config.ORDER_TTL_MINUTES)),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    log_event(db, "order_created", order.transaction_id, game.game_id,
              detail=f"vk_id={vk_id} amount_kop={amount_kop}")
    return order


def is_expired(order: Order) -> bool:
    if order.status != "pending" or not order.expires_at:
        return False
    exp = parse_utc(order.expires_at)
    return exp is not None and utcnow() > exp


def cancel_expired(db: Session) -> list[Order]:
    """Отмена просроченных pending-заказов (scheduler)."""
    expired: list[Order] = []
    for order in db.query(Order).filter(Order.status == "pending").all():
        if is_expired(order):
            order.status = "cancelled"
            expired.append(order)
    if expired:
        db.commit()
        for o in expired:
            log_event(db, "order_expired_cancelled", o.transaction_id, o.game_id,
                      detail=f"vk_id={o.vk_id} amount_kop={o.amount_kop}")
    return expired


def mark_success(db: Session, order: Order, moneta_operation_id: str | None
                 ) -> WebhookDelivery | None:
    """success + постановка вебхука в одной транзакции. None = уже success (идемпотентно)."""
    if order.status == "success":
        return None
    was = order.status
    order.status = "success"
    order.completed_at = utc_iso(utcnow())
    order.moneta_operation_id = moneta_operation_id
    delivery = WebhookDelivery(
        order_id=order.id,
        attempt=0,
        status="queued",
        next_retry_at=utc_iso(utcnow()),
    )
    db.add(delivery)
    db.commit()
    log_event(
        db, "order_success", order.transaction_id, order.game_id,
        detail=(
            f"vk_id={order.vk_id} amount_kop={order.amount_kop} "
            f"prev_status={was} mnt_operation_id={moneta_operation_id or ''}"
        ),
    )
    db.refresh(order)
    db.refresh(delivery)
    return delivery


def order_to_dict(order: Order) -> dict:
    """Публичный статус (для игр; без лишнего — план §3)."""
    return {
        "transaction_id": order.transaction_id,
        "game_id": order.game_id,
        "status": order.status,
        "amount_kop": order.amount_kop,
        "paid_at": _msk(order.completed_at),
    }


def order_to_admin_dict(order: Order) -> dict:
    return {
        "id": order.id,
        "transaction_id": order.transaction_id,
        "game_id": order.game_id,
        "vk_id": order.vk_id,
        "amount_kop": order.amount_kop,
        "amount_rub": f"{order.amount_kop / 100:.2f}",
        "description": order.description,
        "receipt_email": order.receipt_email,
        "status": order.status,
        "moneta_operation_id": order.moneta_operation_id,
        "created_at": _msk(order.created_at),
        "completed_at": _msk(order.completed_at),
        "expires_at": _msk(order.expires_at),
    }


def _msk(value: str | None) -> str | None:
    dt = parse_utc(value)
    if dt is None:
        return value
    return to_msk_log(dt)
