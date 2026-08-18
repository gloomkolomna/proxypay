"""Фоновый scheduler: отмена просроченных заказов + ретраи вебхуков.
Строго один процесс (воркер) — план §6."""

import logging
import threading
import time

import config
from db import SessionLocal
from services.order_service import cancel_expired
from services.webhook_dispatcher import dispatch_due

logger = logging.getLogger("pay_gateway_scheduler")

_started = False
_started_lock = threading.Lock()


def run_loop(interval: int):
    while True:
        try:
            db = SessionLocal()
            try:
                cancel_expired(db)
                dispatch_due(db)
            finally:
                db.close()
        except Exception as exc:
            logger.error(f"scheduler error: {exc}")
        time.sleep(interval)


def start_scheduler(interval: int | None = None):
    global _started
    with _started_lock:
        if _started:
            return
        _started = True
    if config.TESTING:
        logger.info("TESTING env set — scheduler disabled")
        return
    thread = threading.Thread(
        target=run_loop,
        args=(interval or config.SCHEDULER_INTERVAL_SECONDS,),
        daemon=True,
    )
    thread.start()
    logger.info("pay-gateway scheduler started")
