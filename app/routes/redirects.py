"""GET /pay/success, /pay/fail, /pay/return — редирект игрока в игру (?txn=...)."""

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import config
from db import get_db
from games import get_game
from models import Order

router = APIRouter()


@router.get("/pay/success")
def payment_success(request: Request, db: Session = Depends(get_db)):
    return _game_redirect(request, db, kind="success")


@router.get("/pay/fail")
def payment_fail(request: Request, db: Session = Depends(get_db)):
    return _game_redirect(request, db, kind="fail")


@router.get("/pay/return")
def payment_return(request: Request, db: Session = Depends(get_db)):
    return _game_redirect(request, db, kind="success")


def _game_redirect(request: Request, db: Session, kind: str) -> RedirectResponse:
    txn = request.query_params.get("txn") or request.query_params.get("MNT_TRANSACTION_ID")
    if not txn:
        return RedirectResponse(config.SITE_URL, status_code=302)
    order = db.query(Order).filter(Order.transaction_id == txn).first()
    if not order:
        return RedirectResponse(config.SITE_URL, status_code=302)
    game = get_game(db, order.game_id)
    if not game:
        return RedirectResponse(config.SITE_URL, status_code=302)
    target = game.success_url if kind == "success" else game.fail_url
    sep = "&" if urlparse(target).query else "?"
    return RedirectResponse(f"{target}{sep}txn={txn}", status_code=302)
