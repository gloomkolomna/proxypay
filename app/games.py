"""Реестр игр: CRUD над таблицей games + валидация (ревизия 4 плана).
Секреты генерируются шлюзом; валидация — при записи (fail-fast старта больше нет)."""

import re
import secrets
from urllib.parse import urlparse

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models import GameRegistry, Order, log_event, to_msk_log, utcnow

GAME_ID_RE = re.compile(r"^[a-z0-9_]+$")


class ReceiptConfig(BaseModel):
    tax_code: str = Field(default="1105", min_length=1, max_length=10)
    payment_method: str = Field(default="full_payment", min_length=1, max_length=40)
    payment_object: str = Field(default="commodity", min_length=1, max_length=40)


class GameCreate(BaseModel):
    game_id: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=100)
    description_prefix: str = Field(default="", max_length=60)
    webhook_url: str = Field(min_length=1, max_length=500)
    success_url: str = Field(min_length=1, max_length=500)
    fail_url: str = Field(min_length=1, max_length=500)
    receipt: ReceiptConfig = Field(default_factory=ReceiptConfig)
    is_active: bool = True


class GameUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description_prefix: str = Field(default="", max_length=60)
    webhook_url: str = Field(min_length=1, max_length=500)
    success_url: str = Field(min_length=1, max_length=500)
    fail_url: str = Field(min_length=1, max_length=500)
    receipt: ReceiptConfig = Field(default_factory=ReceiptConfig)
    is_active: bool = True


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"Невалидный URL: {url}")


def validate_game_id(game_id: str) -> None:
    if not GAME_ID_RE.match(game_id):
        raise ValueError(
            "game_id обязан соответствовать ^[a-z0-9_]+$ "
            "(строчные латиница/цифры/подчёркивание)"
        )


def get_game(db: Session, game_id: str) -> GameRegistry | None:
    return db.query(GameRegistry).filter(GameRegistry.game_id == game_id).first()


def list_games(db: Session) -> list[GameRegistry]:
    return db.query(GameRegistry).order_by(GameRegistry.game_id).all()


def create_game(db: Session, data: GameCreate) -> GameRegistry:
    game_id = data.game_id.strip()
    validate_game_id(game_id)
    for url in (data.webhook_url, data.success_url, data.fail_url):
        _validate_url(url)
    if get_game(db, game_id):
        raise ValueError(f"Игра {game_id!r} уже существует")
    now = to_msk_log(utcnow()) or ""
    game = GameRegistry(
        game_id=game_id,
        name=data.name.strip(),
        description_prefix=data.description_prefix.strip(),
        webhook_url=data.webhook_url.strip(),
        success_url=data.success_url.strip(),
        fail_url=data.fail_url.strip(),
        api_key=secrets.token_urlsafe(32),
        webhook_secret=secrets.token_urlsafe(32),
        tax_code=data.receipt.tax_code,
        payment_method=data.receipt.payment_method,
        payment_object=data.receipt.payment_object,
        is_active=data.is_active,
        created_at=now,
        updated_at=now,
    )
    db.add(game)
    db.commit()
    db.refresh(game)
    return game


def update_game(db: Session, game: GameRegistry, data: GameUpdate) -> GameRegistry:
    for url in (data.webhook_url, data.success_url, data.fail_url):
        _validate_url(url)
    game.name = data.name.strip()
    game.description_prefix = data.description_prefix.strip()
    game.webhook_url = data.webhook_url.strip()
    game.success_url = data.success_url.strip()
    game.fail_url = data.fail_url.strip()
    game.tax_code = data.receipt.tax_code
    game.payment_method = data.receipt.payment_method
    game.payment_object = data.receipt.payment_object
    game.is_active = data.is_active
    game.updated_at = to_msk_log(utcnow()) or ""
    db.commit()
    db.refresh(game)
    return game


def delete_game(db: Session, game: GameRegistry) -> None:
    """Удаление запрещено при наличии заказов — история неотделима (план §2)."""
    has_orders = db.query(Order.id).filter(Order.game_id == game.game_id).first()
    if has_orders:
        raise ValueError(
            "У игры есть заказы — удаление запрещено. Используйте is_active=false."
        )
    db.delete(game)
    db.commit()


def rotate_secret(db: Session, game: GameRegistry, which: str) -> str:
    """which: 'api_key' | 'webhook_secret'. Старый секрет перестаёт работать мгновенно."""
    if which == "api_key":
        game.api_key = secrets.token_urlsafe(32)
        new_value = game.api_key
    elif which == "webhook_secret":
        game.webhook_secret = secrets.token_urlsafe(32)
        new_value = game.webhook_secret
    else:
        raise ValueError("which обязан быть 'api_key' или 'webhook_secret'")
    game.updated_at = to_msk_log(utcnow()) or ""
    db.commit()
    return new_value


def game_to_dict(game: GameRegistry, include_secrets: bool = False) -> dict:
    data = {
        "game_id": game.game_id,
        "name": game.name,
        "description_prefix": game.description_prefix,
        "webhook_url": game.webhook_url,
        "success_url": game.success_url,
        "fail_url": game.fail_url,
        "receipt": {
            "tax_code": game.tax_code,
            "payment_method": game.payment_method,
            "payment_object": game.payment_object,
        },
        "is_active": game.is_active,
        "created_at": game.created_at,
        "updated_at": game.updated_at,
    }
    if include_secrets:
        data["api_key"] = game.api_key
        data["webhook_secret"] = game.webhook_secret
    return data
