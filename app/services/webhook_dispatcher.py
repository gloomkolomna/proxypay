"""Доставка вебхуков играм: HMAC-SHA256, at-least-once, экспоненциальные ретраи
(1м/5м/15м/1ч/4ч/24ч). 404 от игры — ретраибельная ошибка (гонка unknown txn)."""

import json
import sys
from datetime import timedelta

import httpx
from sqlalchemy.orm import Session

import config
from games import get_game
from models import Order, WebhookDelivery, log_event, parse_utc, to_msk_iso, to_msk_log, utc_iso, utcnow
from security import sign_payload


def build_payload(order) -> dict:
    paid_at = to_msk_iso(parse_utc(order.completed_at))
    return {
        "transaction_id": order.transaction_id,
        "game_id": order.game_id,
        "vk_id": order.vk_id,
        "amount_kop": order.amount_kop,
        "status": "success",
        "paid_at": paid_at,
        "moneta_operation_id": order.moneta_operation_id,
    }


def _next_delay_seconds(attempt: int) -> int | None:
    """attempt — номер только что сделанной попытки (1-based).
    Пауза после попытки N = RETRY_DELAYS[N-1] (1м/5м/15м/1ч/4ч/24ч).
    None = попытки исчерпаны (1 первичная + 6 ретраев)."""
    if 1 <= attempt <= len(config.WEBHOOK_RETRY_DELAYS):
        return config.WEBHOOK_RETRY_DELAYS[attempt - 1]
    return None


def send_delivery(db: Session, delivery: WebhookDelivery, order) -> None:
    """Одна попытка доставки. Меняет статус/расписание, логирует."""
    game = get_game(db, order.game_id)
    if not game:
        delivery.last_error = f"game {order.game_id!r} not found in registry"
        delivery.status = "failed"
        db.commit()
        log_event(db, "webhook_failed", order.transaction_id, order.game_id,
                  detail=delivery.last_error)
        return

    body = json.dumps(build_payload(order), ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")
    signature = sign_payload(body, game.webhook_secret)
    delivery.attempt += 1
    try:
        resp = httpx.post(
            game.webhook_url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Pay-Signature": signature,
            },
            timeout=config.WEBHOOK_TIMEOUT_SECONDS,
        )
        delivery.last_response_code = resp.status_code
        delivery.last_error = ""
        ok = 200 <= resp.status_code < 300
        retryable_404 = resp.status_code == 404  # гонка «вебхук раньше сохранения txn»
    except Exception as exc:  # сеть/таймаут
        delivery.last_response_code = None
        delivery.last_error = f"{type(exc).__name__}: {exc}"[:2000]
        ok = False
        retryable_404 = False

    now = utcnow()
    if ok:
        delivery.status = "delivered"
        delivery.delivered_at = utc_iso(now)
        delivery.next_retry_at = None
        db.commit()
        log_event(db, "webhook_delivered", order.transaction_id, order.game_id,
                  detail=f"attempt={delivery.attempt} code={delivery.last_response_code}")
        return

    delay = _next_delay_seconds(delivery.attempt)
    if delay is None:
        delivery.status = "failed"
        delivery.next_retry_at = None
        db.commit()
        log_event(db, "webhook_failed", order.transaction_id, order.game_id,
                  detail=(f"attempt={delivery.attempt} "
                          f"code={delivery.last_response_code} err={delivery.last_error}"))
        print(
            f"[PayGateway] webhook FAILED order={order.transaction_id} "
            f"game={order.game_id} code={delivery.last_response_code}",
            file=sys.stderr, flush=True,
        )
        return

    delivery.next_retry_at = utc_iso(now + timedelta(seconds=delay))
    db.commit()
    log_event(db, "webhook_retry_scheduled", order.transaction_id, order.game_id,
              detail=(f"attempt={delivery.attempt} code={delivery.last_response_code} "
                      f"retryable_404={retryable_404} next_in={delay}s "
                      f"err={delivery.last_error}"))


def dispatch_due(db: Session) -> int:
    """Отправить все queued-доставки, чей next_retry_at настал. Возвращает кол-во попыток."""
    now_s = utc_iso(utcnow())
    due = (
        db.query(WebhookDelivery)
        .join(Order, WebhookDelivery.order_id == Order.id)
        .filter(WebhookDelivery.status == "queued",
                WebhookDelivery.next_retry_at <= now_s)
        .all()
    )
    for delivery in due:
        order = db.query(Order).filter(Order.id == delivery.order_id).first()
        if order is None:
            delivery.status = "failed"
            delivery.last_error = f"order {delivery.order_id} not found"
            db.commit()
            continue
        send_delivery(db, delivery, order)
    return len(due)


def redeliver(db: Session, order, actor_vk_id: int | None) -> WebhookDelivery:
    """Ручная переотправка из админки: новая queued-доставка."""
    delivery = WebhookDelivery(
        order_id=order.id,
        attempt=0,
        status="queued",
        next_retry_at=utc_iso(utcnow()),
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    log_event(db, "admin_action", order.transaction_id, order.game_id,
              actor_vk_id=actor_vk_id, detail="webhook redeliver (manual)")
    return delivery


def delivery_to_dict(delivery: WebhookDelivery) -> dict:
    def msk(v):
        dt = parse_utc(v)
        return to_msk_log(dt) if dt else v

    return {
        "id": delivery.id,
        "attempt": delivery.attempt,
        "status": delivery.status,
        "last_response_code": delivery.last_response_code,
        "last_error": delivery.last_error,
        "next_retry_at": msk(delivery.next_retry_at),
        "delivered_at": msk(delivery.delivered_at),
    }
