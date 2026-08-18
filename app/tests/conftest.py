"""Общие фикстуры: in-memory SQLite, TestClient, игра, подписанные запросы, админ-токен."""

import os
import sys
import time

import hmac as hmac_mod
import hashlib

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)

# ENV — строго ДО импорта config
os.environ["TESTING"] = "1"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["APP_ENV"] = "production"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["ADMIN_VK_ALLOWED_IDS"] = "400977"
os.environ["ADMIN_VK_CLIENT_ID"] = "vk-app-123"
os.environ["MONETA_MNT_ID"] = "12345"
os.environ["MONETA_INTEGRITY_CODE"] = "integrity-code"
os.environ["MONETA_TEST_MODE"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import config  # noqa: E402
from db import Base, SessionLocal, engine  # noqa: E402


@pytest.fixture(autouse=True)
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client():
    from main import app
    # https — чтобы Secure-cookie (OAuth state, админ-токен) работали в тестах
    with TestClient(app, base_url="https://testserver") as c:
        yield c


ADMIN_VK = 400977


@pytest.fixture()
def admin_headers():
    from auth import create_access_token
    return {"Authorization": f"Bearer {create_access_token(ADMIN_VK)}"}


@pytest.fixture()
def game(db):
    from games import GameCreate, create_game
    g = create_game(db, GameCreate(
        game_id="dragons",
        name="Драконы",
        description_prefix="[Драконы]",
        webhook_url="http://127.0.0.1:59999/api/payment/webhook",
        success_url="https://example.com/done",
        fail_url="https://example.com/fail",
    ))
    return g


def sign_body(body: bytes, api_key: str) -> str:
    return hmac_mod.new(api_key.encode(), body, hashlib.sha256).hexdigest()


def game_headers(game, body: bytes, *, timestamp: int | None = None,
                 bad_sig: bool = False) -> dict:
    sig = sign_body(body, game.api_key)
    if bad_sig:
        sig = "0" * 64
    return {
        "X-Game-Id": game.game_id,
        "X-Timestamp": str(timestamp if timestamp is not None else int(time.time())),
        "X-Game-Signature": sig,
    }


@pytest.fixture()
def make_order(db, game):
    """Заказ напрямую через сервис (для колбэка/страниц/вебхуков)."""
    from services.order_service import create_order

    def _make(vk_id=123, amount_kop=10000, status="pending"):
        order = create_order(
            db, game, vk_id=vk_id, amount_kop=amount_kop,
            description="Набор «Стартовый»", receipt_email=None,
            receipt_items_json=None,
        )
        if status != "pending":
            order.status = status
            db.commit()
        return order

    return _make


def moneta_callback_params(order, amount_kop=None, mnt_id=None,
                           test_mode: str | None = None) -> dict:
    """Валидные параметры колбэка MONETA с подписью."""
    import hashlib
    params = {
        "MNT_ID": mnt_id or config.MONETA_MNT_ID,
        "MNT_TRANSACTION_ID": order.transaction_id,
        "MNT_OPERATION_ID": "777001",
        "MNT_AMOUNT": f"{(amount_kop if amount_kop is not None else order.amount_kop) / 100:.2f}",
        "MNT_CURRENCY_CODE": "RUB",
        "MNT_TEST_MODE": test_mode or ("1" if config.MONETA_TEST_MODE else "0"),
    }
    raw = (
        f"{params['MNT_ID']}{params['MNT_TRANSACTION_ID']}{params['MNT_OPERATION_ID']}"
        f"{params['MNT_AMOUNT']}{params['MNT_CURRENCY_CODE']}"
        f"{params['MNT_TEST_MODE']}{config.MONETA_INTEGRITY_CODE}"
    )
    params["MNT_SIGNATURE"] = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return params


@pytest.fixture()
def fake_webhook(monkeypatch):
    """Заглушка исходящих вебхуков: список вызовов + управляемый ответ."""
    calls: list[dict] = []

    class Resp:
        def __init__(self, status_code):
            self.status_code = status_code

    state = {"next_response": 200, "raise_exc": None}

    def _post(url, content=None, headers=None, timeout=None, **kwargs):
        calls.append({
            "url": url,
            "body": content,
            "headers": headers,
        })
        if state["raise_exc"]:
            raise state["raise_exc"]
        return Resp(state["next_response"])

    import services.webhook_dispatcher as wd
    monkeypatch.setattr(wd.httpx, "post", _post)
    return {"calls": calls, "state": state}
