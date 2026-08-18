"""POST/GET /pay/moneta/callback — колбэк MONETA (PayAnyWay).
Перенос логики драконьего /api/payment/moneta/callback (план §3):
подпись/IP → сумма → mark_success (+вебхук в одной транзакции) → SUCCESS."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

import config
from db import get_db
from models import Order, log_event
from moneta import verify_callback_signature
from services import webhook_dispatcher
from services.order_service import mark_success

router = APIRouter()


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


async def _collect_params(request: Request) -> dict:
    params = dict(request.query_params)
    try:
        form = await request.form()
        params.update({k: str(v) for k, v in form.items()})
    except Exception:
        pass
    return params


@router.api_route("/pay/moneta/callback", methods=["GET", "POST"])
async def moneta_callback(request: Request, db: Session = Depends(get_db)):
    client_ip = _client_ip(request)
    params = await _collect_params(request)

    mnt_transaction_id = params.get("MNT_TRANSACTION_ID")
    mnt_amount = params.get("MNT_AMOUNT")
    signature = params.get("MNT_SIGNATURE")
    no_sig_cb = config.MONETA_NO_SIGNATURE_CALLBACK

    log_event(db, "moneta_callback_raw", mnt_transaction_id,
              detail=f"ip={client_ip} params={params}")

    if not (mnt_transaction_id and mnt_amount and (signature or no_sig_cb)):
        log_event(db, "moneta_callback_bad_params", mnt_transaction_id,
                  detail=f"ip={client_ip}")
        raise HTTPException(status_code=400, detail="bad params")

    if no_sig_cb:
        if client_ip not in config.MONETA_CALLBACK_IPS:
            log_event(db, "moneta_callback_bad_ip", mnt_transaction_id,
                      detail=f"ip={client_ip} allowed={config.MONETA_CALLBACK_IPS}")
            raise HTTPException(status_code=400, detail="bad ip")
    elif not verify_callback_signature(params, config.MONETA_INTEGRITY_CODE):
        log_event(db, "moneta_callback_bad_sig", mnt_transaction_id,
                  detail=f"ip={client_ip}")
        raise HTTPException(status_code=400, detail="bad signature")

    order = db.query(Order).filter(Order.transaction_id == mnt_transaction_id).first()
    if not order:
        log_event(db, "moneta_callback_order_not_found", mnt_transaction_id,
                  detail=f"ip={client_ip}")
        raise HTTPException(status_code=400, detail="order not found")

    if order.status == "success":
        return PlainTextResponse("SUCCESS")

    try:
        paid = round(float(mnt_amount) * 100)
    except (ValueError, TypeError):
        paid = -1
    if abs(paid - order.amount_kop) > 1:
        log_event(db, "moneta_callback_amount_mismatch", mnt_transaction_id,
                  order.game_id,
                  detail=f"expected={order.amount_kop} got={paid} ip={client_ip}")
        raise HTTPException(status_code=400, detail="amount mismatch")

    # cancelled/failed/pending → success: деньги списаны, товар должен уйти (план §0)
    delivery = mark_success(db, order, params.get("MNT_OPERATION_ID"))

    # Лучшая попытка немедленной доставки; ретраи подберёт scheduler
    if delivery is not None:
        try:
            webhook_dispatcher.send_delivery(db, delivery, order)
        except Exception:
            pass

    return PlainTextResponse("SUCCESS")
