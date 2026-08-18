"""PayAnyWay (MONETA.Assistant): подписи формы + колбэка.
Перенос из драконьего api/services/moneta_service.py 1:1 (план §8)."""

import hashlib


def _md5(raw: str) -> str:
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def format_amount(amount_kop: int) -> str:
    return f"{amount_kop / 100:.2f}"


def build_payment_signature(mnt_id: str, mnt_trx: str, amount_str: str,
                            code: str, test_mode: str) -> str:
    raw = f"{mnt_id}{mnt_trx}{amount_str}RUB{test_mode}{code}"
    return _md5(raw)


def verify_callback_signature(params: dict, code: str) -> bool:
    if not code:
        return False
    signature = params.get("MNT_SIGNATURE")
    if not signature:
        return False
    mnt_id = params.get("MNT_ID", "")
    mnt_trx = params.get("MNT_TRANSACTION_ID", "")
    mnt_operation_id = params.get("MNT_OPERATION_ID", "")
    mnt_amount = params.get("MNT_AMOUNT", "")
    mnt_currency = params.get("MNT_CURRENCY_CODE", "")
    mnt_subscriber = params.get("MNT_SUBSCRIBER_ID", "")
    mnt_test = params.get("MNT_TEST_MODE", "0")
    raw = (
        f"{mnt_id}{mnt_trx}{mnt_operation_id}{mnt_amount}{mnt_currency}"
        f"{mnt_subscriber}{mnt_test}{code}"
    )
    return _md5(raw).lower() == str(signature).lower()
