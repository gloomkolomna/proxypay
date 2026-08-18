"""pay-gateway configuration (ENV). Game registry lives in DB, not here."""

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, "")).strip())
    except (ValueError, TypeError):
        return default


# ── Общие ──
APP_ENV = _env("APP_ENV", "production").lower()          # production | dev
DEV_LOGIN_ENABLED = APP_ENV == "dev"
DATABASE_URL = _env("DATABASE_URL", f"sqlite:///{REPO_ROOT / 'pay-gateway.db'}")
SITE_URL = _env("SITE_URL", "https://belovolovhome.ru").rstrip("/")

# ── JWT админки ──
SECRET_KEY = _env("SECRET_KEY", "change-me")
ALGORITHM = _env("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = _env_int("ACCESS_TOKEN_EXPIRE_MINUTES", 43200)

# ── Админка: VK ID (отдельное приложение, не драконье) ──
ADMIN_VK_CLIENT_ID = _env("ADMIN_VK_CLIENT_ID")
ADMIN_VK_CLIENT_SECRET = _env("ADMIN_VK_CLIENT_SECRET")
ADMIN_VK_REDIRECT_URI = _env(
    "ADMIN_VK_REDIRECT_URI", f"{SITE_URL}/pay/api/auth/vk-callback"
)
TESTING = _env_bool("TESTING", False)


def get_admin_vk_ids() -> set[int]:
    """Allowlist администраторов (аналог VK_ALLOWED_IDS драконов)."""
    raw = _env("ADMIN_VK_ALLOWED_IDS")
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


# ── MONETA (PayAnyWay) ──
MONETA_MNT_ID = _env("MONETA_MNT_ID")
MONETA_INTEGRITY_CODE = _env("MONETA_INTEGRITY_CODE")
MONETA_TEST_MODE = _env("MONETA_TEST_MODE", "1").strip() == "1"
MONETA_NO_SIGNATURE_FORM = _env_bool("MONETA_NO_SIGNATURE_FORM", False)
MONETA_NO_SIGNATURE_CALLBACK = _env_bool("MONETA_NO_SIGNATURE_CALLBACK", False)
MONETA_CALLBACK_IPS = [
    ip.strip() for ip in _env("MONETA_CALLBACK_IPS", "193.176.92.70").split(",") if ip.strip()
]


def moneta_assistant_url() -> str:
    if MONETA_TEST_MODE:
        return "https://demo.moneta.ru/assistant.htm"
    return "https://www.payanyway.ru/assistant.htm"


# ── Заказы / тест-блок (начальные значения; дальше живут в БД, см. settings_service) ──
ORDER_TTL_MINUTES = _env_int("ORDER_TTL_MINUTES", 60)
INIT_PAYMENTS_TEST_MODE = _env_bool("PAYMENTS_TEST_MODE", False)
INIT_PAYMENTS_TEST_VK_ID = _env_int("PAYMENTS_TEST_VK_ID", 400977)

# ── Вебхуки: ретраи (экспонента до 24 ч) ──
WEBHOOK_RETRY_DELAYS = [60, 300, 900, 3600, 14400, 86400]
WEBHOOK_TIMEOUT_SECONDS = _env_int("WEBHOOK_TIMEOUT_SECONDS", 10)

# ── Scheduler ──
SCHEDULER_INTERVAL_SECONDS = _env_int("SCHEDULER_INTERVAL_SECONDS", 30)
