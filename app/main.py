"""pay-gateway — FastAPI app.
Порядок роутов важен: /pay/{transaction_id} (catch-all) подключается ПОСЛЕДНИМ,
чтобы не перекрыть /pay/success, /pay/admin и статические пути (план §6)."""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.staticfiles import StaticFiles

import config
from db import Base, SessionLocal, engine
from models import Order
from routes import admin as admin_routes
from routes import auth_admin as auth_admin_routes
from routes import callback as callback_routes
from routes import orders as orders_routes
from routes import pay as pay_routes
from routes import redirects as redirect_routes
from routes import status as status_routes
from services import settings_service
from services.scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pay_gateway")

app = FastAPI(title="pay-gateway", docs_url=None, redoc_url=None)


@app.get("/pay/health")
def health():
    return {"ok": True, "moneta_test_mode": config.MONETA_TEST_MODE}


# ── Порядок: сначала конкретные пути, catch-all (/pay/{txn}) — ПОСЛЕДНИМ ──
app.include_router(auth_admin_routes.router)   # /pay/api/auth/*
app.include_router(admin_routes.router)        # /pay/api/admin/*
app.include_router(callback_routes.router)     # /pay/moneta/callback
app.include_router(redirect_routes.router)     # /pay/success /pay/fail /pay/return
app.include_router(orders_routes.router)       # /pay/orders, /pay/orders/{txn}
app.include_router(status_routes.router)       # /pay/status/{txn} (браузерный)
app.include_router(pay_routes.router)          # /pay/{transaction_id} — catch-all


# ── Статика админки (web/dist), до catch-all она и так раньше — но монтируем явно ──
_WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
if _WEB_DIST.exists():
    app.mount("/pay/admin", StaticFiles(directory=str(_WEB_DIST), html=True),
              name="admin-spa")
else:
    logger.info("web/dist not found — admin SPA not mounted")


@app.on_event("startup")
def on_startup():
    # Bootstrap: создаём таблицы, если их нет (дальше — alembic-миграции)
    from sqlalchemy import inspect
    insp = inspect(engine)
    if not insp.has_table(Order.__tablename__):
        Base.metadata.create_all(engine)
        logger.info("database bootstrap: tables created")
    db = SessionLocal()
    try:
        settings_service.seed_from_env(db)
    finally:
        db.close()
    start_scheduler()
    logger.info("pay-gateway started (env=%s, moneta_test=%s)",
                config.APP_ENV, config.MONETA_TEST_MODE)
