"""HMAC-подписи: входящие запросы игр (POST /orders, GET /orders/{txn})
и исходящие вебхуки играм."""

import hashlib
import hmac
import time

TIMESTAMP_WINDOW_SECONDS = 300  # ±5 минут против replay


def sign_payload(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_signature(body: bytes, secret: str, signature: str) -> bool:
    if not secret or not signature:
        return False
    return hmac.compare_digest(sign_payload(body, secret), signature.strip().lower())


def verify_timestamp(timestamp_header: str | None) -> bool:
    if timestamp_header is None or not timestamp_header.strip():
        return False
    try:
        ts = int(timestamp_header.strip())
    except (ValueError, TypeError):
        return False
    return abs(time.time() - ts) <= TIMESTAMP_WINDOW_SECONDS
