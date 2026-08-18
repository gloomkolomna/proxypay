"""Runtime-настройки в БД: тумблер тест-режима и тестовый vk_id.
.env задаёт только начальные значения; дальше — переключение в админке без рестарта."""

import config
from models import GatewaySetting, to_msk_log, utcnow
from sqlalchemy.orm import Session

KEY_PAYMENTS_TEST_MODE = "payments_test_mode"
KEY_PAYMENTS_TEST_VK_ID = "payments_test_vk_id"


def _get(db: Session, key: str) -> str | None:
    row = db.query(GatewaySetting).filter(GatewaySetting.key == key).first()
    return row.value if row else None


def _set(db: Session, key: str, value: str, actor_vk_id: int | None = None) -> None:
    row = db.query(GatewaySetting).filter(GatewaySetting.key == key).first()
    if row:
        row.value = value
        row.updated_at = to_msk_log(utcnow()) or ""
        row.updated_by = actor_vk_id
    else:
        db.add(GatewaySetting(
            key=key, value=value,
            updated_at=to_msk_log(utcnow()) or "",
            updated_by=actor_vk_id,
        ))
    db.commit()


def seed_from_env(db: Session) -> None:
    """При старте: если настройки отсутствуют — посеять из ENV."""
    if _get(db, KEY_PAYMENTS_TEST_MODE) is None:
        _set(db, KEY_PAYMENTS_TEST_MODE, "1" if config.INIT_PAYMENTS_TEST_MODE else "0")
    if _get(db, KEY_PAYMENTS_TEST_VK_ID) is None:
        _set(db, KEY_PAYMENTS_TEST_VK_ID, str(config.INIT_PAYMENTS_TEST_VK_ID))


def payments_test_mode(db: Session) -> bool:
    return (_get(db, KEY_PAYMENTS_TEST_MODE) or "0") == "1"


def payments_test_vk_id(db: Session) -> int:
    raw = _get(db, KEY_PAYMENTS_TEST_VK_ID) or str(config.INIT_PAYMENTS_TEST_VK_ID)
    try:
        return int(raw)
    except (ValueError, TypeError):
        return config.INIT_PAYMENTS_TEST_VK_ID


def is_payment_blocked_for(db: Session, vk_id: int) -> bool:
    return payments_test_mode(db) and vk_id != payments_test_vk_id(db)


def set_payments_test_mode(db: Session, enabled: bool, actor_vk_id: int | None) -> None:
    _set(db, KEY_PAYMENTS_TEST_MODE, "1" if enabled else "0", actor_vk_id)


def set_payments_test_vk_id(db: Session, vk_id: int, actor_vk_id: int | None) -> None:
    _set(db, KEY_PAYMENTS_TEST_VK_ID, str(vk_id), actor_vk_id)


def all_settings(db: Session) -> dict:
    return {
        "payments_test_mode": payments_test_mode(db),
        "payments_test_vk_id": payments_test_vk_id(db),
        "moneta_test_mode": config.MONETA_TEST_MODE,
        "moneta_mnt_id": config.MONETA_MNT_ID,
        "order_ttl_minutes": config.ORDER_TTL_MINUTES,
    }
