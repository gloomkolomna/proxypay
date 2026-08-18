"""/pay/api/admin/* — админ-API шлюза (JWT от VK ID, план §2).
Заказы, доставки вебхуков, журнал, CRUD реестра игр, настройки, статистика."""

import json
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import get_current_admin
from db import get_db
from games import (
    GameCreate, GameUpdate, create_game, delete_game, game_to_dict,
    get_game, list_games, rotate_secret, update_game,
)
from models import GatewayLog, Order, WebhookDelivery, log_event, to_msk_log, utc_iso, utcnow
from services import settings_service
from services.order_service import order_to_admin_dict
from services.webhook_dispatcher import delivery_to_dict, redeliver, send_delivery

router = APIRouter(prefix="/pay/api/admin", tags=["admin"],
                   dependencies=[Depends(get_current_admin)])


# ── Заказы ──

@router.get("/orders")
def list_orders(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    game_id: Optional[str] = None,
    status: Optional[str] = Query(None, pattern="^(pending|success|cancelled|failed)?$"),
    vk_id: Optional[int] = None,
    txn: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Order)
    if game_id:
        q = q.filter(Order.game_id == game_id)
    if status:
        q = q.filter(Order.status == status)
    if vk_id:
        q = q.filter(Order.vk_id == vk_id)
    if txn:
        q = q.filter(Order.transaction_id.contains(txn))
    total = q.count()
    items = (
        q.order_by(Order.id.desc())
        .offset((page - 1) * per_page).limit(per_page).all()
    )
    return {"total": total, "items": [order_to_admin_dict(o) for o in items]}


@router.get("/orders/{txn}")
def order_detail(txn: str, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.transaction_id == txn).first()
    if not order:
        raise HTTPException(status_code=404, detail="order not found")
    deliveries = (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.order_id == order.id)
        .order_by(WebhookDelivery.id.desc())
        .all()
    )
    return {"order": order_to_admin_dict(order),
            "deliveries": [delivery_to_dict(d) for d in deliveries]}


@router.post("/orders/{txn}/redeliver")
def order_redeliver(txn: str, db: Session = Depends(get_db),
                    actor: int = Depends(get_current_admin)):
    order = db.query(Order).filter(Order.transaction_id == txn).first()
    if not order:
        raise HTTPException(status_code=404, detail="order not found")
    if order.status != "success":
        raise HTTPException(status_code=409, detail="order is not success")
    delivery = redeliver(db, order, actor)
    try:  # немедленная попытка; ретраи подберёт scheduler
        send_delivery(db, delivery, order)
    except Exception:
        pass
    return {"ok": True, "delivery": delivery_to_dict(delivery)}


# ── Журнал ──

@router.get("/logs")
def list_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=500),
    event: Optional[str] = None,
    game_id: Optional[str] = None,
    transaction_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(GatewayLog)
    if event:
        q = q.filter(GatewayLog.event == event)
    if game_id:
        q = q.filter(GatewayLog.game_id == game_id)
    if transaction_id:
        q = q.filter(GatewayLog.transaction_id == transaction_id)
    total = q.count()
    items = q.order_by(GatewayLog.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return {
        "total": total,
        "items": [{
            "id": l.id, "event": l.event, "transaction_id": l.transaction_id,
            "game_id": l.game_id, "actor_vk_id": l.actor_vk_id,
            "detail": l.detail, "created_at": l.created_at,
        } for l in items],
    }


# ── Реестр игр (CRUD, ревизия 4) ──

@router.get("/games")
def admin_list_games(db: Session = Depends(get_db)):
    return {"items": [game_to_dict(g) for g in list_games(db)]}


@router.post("/games", status_code=201)
def admin_create_game(data: GameCreate, db: Session = Depends(get_db),
                      actor: int = Depends(get_current_admin)):
    try:
        game = create_game(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    log_event(db, "admin_action", game_id=game.game_id, actor_vk_id=actor,
              detail=f"game created: {game.game_id}")
    # Секреты показываются один раз — при создании
    return game_to_dict(game, include_secrets=True)


@router.get("/games/{game_id}")
def admin_get_game(game_id: str, reveal: bool = False,
                   db: Session = Depends(get_db)):
    game = get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="game not found")
    return game_to_dict(game, include_secrets=reveal)


@router.put("/games/{game_id}")
def admin_update_game(game_id: str, data: GameUpdate,
                      db: Session = Depends(get_db),
                      actor: int = Depends(get_current_admin)):
    game = get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="game not found")
    try:
        game = update_game(db, game, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    log_event(db, "admin_action", game_id=game_id, actor_vk_id=actor,
              detail=f"game updated (is_active={game.is_active})")
    return game_to_dict(game)


@router.delete("/games/{game_id}")
def admin_delete_game(game_id: str, db: Session = Depends(get_db),
                      actor: int = Depends(get_current_admin)):
    game = get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="game not found")
    try:
        delete_game(db, game)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    log_event(db, "admin_action", game_id=game_id, actor_vk_id=actor,
              detail="game deleted (no orders)")
    return {"ok": True}


class RotateBody(BaseModel):
    which: str  # 'api_key' | 'webhook_secret'


@router.post("/games/{game_id}/rotate")
def admin_rotate_game_secret(game_id: str, body: RotateBody,
                             db: Session = Depends(get_db),
                             actor: int = Depends(get_current_admin)):
    game = get_game(db, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="game not found")
    if body.which not in ("api_key", "webhook_secret"):
        raise HTTPException(status_code=422, detail="which: api_key | webhook_secret")
    new_value = rotate_secret(db, game, body.which)
    log_event(db, "admin_action", game_id=game_id, actor_vk_id=actor,
              detail=f"secret rotated: {body.which}")
    return {"ok": True, "which": body.which, "new_value": new_value}


# ── Настройки ──

class SettingsBody(BaseModel):
    payments_test_mode: Optional[bool] = None
    payments_test_vk_id: Optional[int] = None


@router.get("/settings")
def admin_get_settings(db: Session = Depends(get_db)):
    return settings_service.all_settings(db)


@router.put("/settings")
def admin_put_settings(body: SettingsBody, db: Session = Depends(get_db),
                       actor: int = Depends(get_current_admin)):
    if body.payments_test_mode is not None:
        settings_service.set_payments_test_mode(db, body.payments_test_mode, actor)
    if body.payments_test_vk_id is not None:
        settings_service.set_payments_test_vk_id(db, body.payments_test_vk_id, actor)
    log_event(db, "admin_action", actor_vk_id=actor,
              detail=f"settings updated: {body.model_dump(exclude_none=True)}")
    return settings_service.all_settings(db)


# ── Статистика (дашборд) ──

@router.get("/stats")
def admin_stats(db: Session = Depends(get_db)):
    since = utc_iso(utcnow() - timedelta(days=30))
    rows = (
        db.query(
            Order.game_id,
            Order.status,
            func.count(Order.id),
            func.coalesce(func.sum(Order.amount_kop), 0),
        )
        .filter(Order.created_at >= since)
        .group_by(Order.game_id, Order.status)
        .all()
    )
    per_game: dict = {}
    for game_id, status, cnt, amount in rows:
        g = per_game.setdefault(game_id, {
            "game_id": game_id, "orders": {}, "success_amount_kop": 0,
        })
        g["orders"][status] = cnt
        if status == "success":
            g["success_amount_kop"] = amount
    failed_deliveries = db.query(func.count(WebhookDelivery.id)).filter(
        WebhookDelivery.status == "failed").scalar() or 0
    queued_deliveries = db.query(func.count(WebhookDelivery.id)).filter(
        WebhookDelivery.status == "queued").scalar() or 0
    pending_orders = db.query(func.count(Order.id)).filter(
        Order.status == "pending").scalar() or 0
    return {
        "period_days": 30,
        "per_game": list(per_game.values()),
        "failed_deliveries": failed_deliveries,
        "queued_deliveries": queued_deliveries,
        "pending_orders": pending_orders,
        "generated_at": to_msk_log(utcnow()),
    }
