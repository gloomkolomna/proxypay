"""Модели шлюза: заказы, доставки вебхуков, реестр игр, журнал, настройки."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text

from db import Base

MSK = timezone(timedelta(hours=3))


def utcnow() -> datetime:
    """Наивный UTC — внутренний формат всех datetime-колонок."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_iso(dt: datetime) -> str:
    """Наивный UTC ISO — формат хранения/сравнения (лексикографически сортируется)."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def to_msk_iso(dt: datetime | None) -> str | None:
    """'+03:00'-формат для API-ответов (как в плане)."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(MSK).isoformat()


def to_msk_log(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(MSK).strftime("%Y-%m-%dT%H:%M:%S")


class GameRegistry(Base):
    """Реестр игр — CRUD из админки (ревизия 4 плана)."""

    __tablename__ = "games"

    game_id = Column(String, primary_key=True)          # ^[a-z0-9_]+$
    name = Column(String, nullable=False)
    description_prefix = Column(String, default="")
    webhook_url = Column(String, nullable=False)
    success_url = Column(String, nullable=False)
    fail_url = Column(String, nullable=False)
    api_key = Column(String, nullable=False)             # входящие от игры (POST /orders)
    webhook_secret = Column(String, nullable=False)      # исходящие вебхуки игре
    tax_code = Column(String, default="1105")            # чек 54-ФЗ
    payment_method = Column(String, default="full_payment")
    payment_object = Column(String, default="commodity")
    is_active = Column(Boolean, default=True)
    created_at = Column(String, default="")
    updated_at = Column(String, default="")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_id = Column(String, unique=True, index=True)   # YYYYMMDD-NNNNNN
    game_id = Column(String, index=True, nullable=False)
    vk_id = Column(Integer, index=True, nullable=False)
    amount_kop = Column(Integer, nullable=False)
    description = Column(Text, default="")
    receipt_email = Column(String, nullable=True)
    receipt_items_json = Column(Text, nullable=True)           # позиции чека, если игра передала
    status = Column(String(20), default="pending")             # pending|success|cancelled|failed
    moneta_operation_id = Column(String, nullable=True)
    created_at = Column(String, default="")
    completed_at = Column(String, nullable=True)
    expires_at = Column(String, nullable=True)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    attempt = Column(Integer, default=0)
    status = Column(String(20), default="queued")       # queued|delivered|failed
    last_response_code = Column(Integer, nullable=True)
    last_error = Column(Text, default="")
    next_retry_at = Column(String, nullable=True)
    delivered_at = Column(String, nullable=True)


class GatewayLog(Base):
    """Журнал шлюза (аналог PaymentLog драконов)."""

    __tablename__ = "gateway_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event = Column(String(40), index=True)
    transaction_id = Column(String, nullable=True, index=True)
    game_id = Column(String, nullable=True, index=True)
    actor_vk_id = Column(Integer, nullable=True)        # для admin_action — кто нажал
    detail = Column(Text, default="")
    created_at = Column(String, default="", index=True)


class GatewaySetting(Base):
    """Runtime-настройки (переключаются в админке без рестарта)."""

    __tablename__ = "gateway_settings"

    key = Column(String, primary_key=True)
    value = Column(String, default="")
    updated_at = Column(String, default="")
    updated_by = Column(Integer, nullable=True)


def log_event(db, event: str, transaction_id: str | None = None,
              game_id: str | None = None, actor_vk_id: int | None = None,
              detail: str = "") -> None:
    """Запись в журнал (best-effort, не роняет вызывающего)."""
    try:
        db.add(GatewayLog(
            event=event[:40],
            transaction_id=transaction_id,
            game_id=game_id,
            actor_vk_id=actor_vk_id,
            detail=str(detail)[:8000],
            created_at=to_msk_log(utcnow()) or "",
        ))
        db.commit()
    except Exception:
        db.rollback()
