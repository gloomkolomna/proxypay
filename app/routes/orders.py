"""POST /pay/orders — создать заказ (вызывает игра).
GET /pay/orders/{txn} — статус заказа (подпись игры, минимум полей)."""

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

import config
from db import get_db
from games import get_game
from models import Order, log_event
from security import verify_signature, verify_timestamp
from services import settings_service
from services.order_service import create_order, order_to_dict

router = APIRouter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ReceiptItem(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    price_kop: int = Field(gt=0)
    quantity: int = Field(gt=0, le=1000)


class OrderCreate(BaseModel):
    vk_id: int = Field(gt=0)
    amount_kop: int = Field(gt=0)
    description: str = Field(min_length=1, max_length=500)
    receipt_email: str | None = None
    receipt_items: list[ReceiptItem] | None = None

    @field_validator("receipt_email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("invalid email")
        return v


def _game_auth_error(detail: str, status: int = 401) -> JSONResponse:
    return JSONResponse({"error": detail}, status_code=status)


async def _authorize_game(request: Request, db: Session):
    """X-Game-Id + X-Timestamp + X-Game-Signature(HMAC raw body). Возвращает (game, raw_body, err_response)."""
    raw_body = await request.body()
    game_id = (request.headers.get("x-game-id") or "").strip()
    if not game_id:
        return None, raw_body, _game_auth_error("missing X-Game-Id")
    game = get_game(db, game_id)
    if game is None:
        log_event(db, "orders_auth_unknown_game", game_id=game_id, detail=f"ip={_client_ip(request)}")
        return None, raw_body, _game_auth_error("unknown game")
    if not game.is_active:
        log_event(db, "orders_auth_disabled_game", game_id=game_id, detail=f"ip={_client_ip(request)}")
        return None, raw_body, JSONResponse({"error": "game disabled"}, status_code=403)
    if not verify_timestamp(request.headers.get("x-timestamp")):
        return None, raw_body, _game_auth_error("bad or missing X-Timestamp")
    signature = request.headers.get("x-game-signature") or ""
    if not verify_signature(raw_body, game.api_key, signature):
        log_event(db, "orders_auth_bad_sig", game_id=game_id, detail=f"ip={_client_ip(request)}")
        return None, raw_body, _game_auth_error("bad signature")
    return game, raw_body, None


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


@router.post("/pay/orders")
async def post_order(request: Request, db: Session = Depends(get_db)):
    game, raw_body, err = await _authorize_game(request, db)
    if err:
        return err

    try:
        payload = OrderCreate.model_validate_json(raw_body or b"{}")
    except Exception as exc:
        return JSONResponse({"error": "bad payload", "detail": str(exc)[:300]}, status_code=422)

    if settings_service.is_payment_blocked_for(db, payload.vk_id):
        log_event(db, "orders_test_blocked", game_id=game.game_id,
                  detail=f"vk_id={payload.vk_id}")
        return JSONResponse({"error": "test_blocked"}, status_code=403)

    receipt_items_json = None
    if payload.receipt_items:
        receipt_items_json = json.dumps(
            [it.model_dump() for it in payload.receipt_items],
            ensure_ascii=False, separators=(",", ":"),
        )

    order = create_order(
        db, game,
        vk_id=payload.vk_id,
        amount_kop=payload.amount_kop,
        description=payload.description,
        receipt_email=str(payload.receipt_email).strip().lower() if payload.receipt_email else None,
        receipt_items_json=receipt_items_json,
    )
    return JSONResponse({
        "transaction_id": order.transaction_id,
        "payment_url": f"{config.SITE_URL}/pay/{order.transaction_id}",
        "amount_kop": order.amount_kop,
        "expires_at": _msk_expires(order),
    }, status_code=201)


def _msk_expires(order: Order) -> str | None:
    from models import parse_utc, to_msk_iso
    return to_msk_iso(parse_utc(order.expires_at))


@router.get("/pay/orders/{transaction_id}")
async def get_order_status(transaction_id: str, request: Request,
                           db: Session = Depends(get_db)):
    game, _, err = await _authorize_game(request, db)
    if err:
        return err
    order = db.query(Order).filter(Order.transaction_id == transaction_id).first()
    if not order:
        return JSONResponse({"error": "not found"}, status_code=404)
    return order_to_dict(order)
