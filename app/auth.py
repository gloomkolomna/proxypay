"""VK ID OAuth2 (PKCE) → JWT для админки шлюза.
Порт драконьего api/auth.py; таблицы пользователей нет — JWT stateless,
allowlist в ADMIN_VK_ALLOWED_IDS (план §2)."""

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx
import jwt
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

import config

VK_ID_AUTH_URL = "https://id.vk.ru/authorize"
VK_ID_TOKEN_URL = "https://id.vk.ru/oauth2/auth"
VK_ID_USER_INFO_URL = "https://id.vk.ru/oauth2/user_info"

STATE_COOKIE = "pg_oauth_state"
CODE_VERIFIER_COOKIE = "pg_code_verifier"
ADMIN_TOKEN_COOKIE = "pg_admin_token"
COOKIE_TTL = 600


def create_access_token(vk_id: int, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return jwt.encode({"sub": str(vk_id), "exp": expire},
                      config.SECRET_KEY, algorithm=config.ALGORITHM)


def generate_state() -> str:
    return secrets.token_urlsafe(32)


def generate_code_verifier() -> str:
    return secrets.token_urlsafe(64)


def compute_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def get_vk_login_url(state: str, code_challenge: str) -> str:
    return (
        f"{VK_ID_AUTH_URL}"
        f"?response_type=code"
        f"&client_id={config.ADMIN_VK_CLIENT_ID}"
        f"&redirect_uri={quote(config.ADMIN_VK_REDIRECT_URI, safe='')}"
        f"&state={state}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
    )


async def exchange_vk_code(code: str, code_verifier: str, device_id: str,
                           state: str = "") -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            VK_ID_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": config.ADMIN_VK_CLIENT_ID,
                "code_verifier": code_verifier,
                "code": code,
                "redirect_uri": config.ADMIN_VK_REDIRECT_URI,
                "device_id": device_id,
                "state": state,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        data = resp.json()
        if "error" in data:
            raise HTTPException(
                status_code=400,
                detail=f"VK error: {data.get('error_description', data['error'])}",
            )
        return data


async def get_vk_user_info(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            VK_ID_USER_INFO_URL,
            data={"client_id": config.ADMIN_VK_CLIENT_ID, "access_token": access_token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        data = resp.json()
        if "error" in data:
            raise HTTPException(
                status_code=400,
                detail=f"VK API error: {data.get('error_description', data['error'])}",
            )
        return data.get("user", data)


def is_admin_allowed(vk_id: int) -> bool:
    return vk_id in config.get_admin_vk_ids()


def set_oauth_cookies(response: Response, state: str, code_verifier: str) -> None:
    for key, value in [(STATE_COOKIE, state), (CODE_VERIFIER_COOKIE, code_verifier)]:
        response.set_cookie(
            key=key, value=value, max_age=COOKIE_TTL,
            httponly=True, samesite="lax", secure=True,
        )


async def get_current_admin(request: Request) -> int:
    """JWT (Authorization: Bearer или cookie pg_admin_token) → vk_id из allowlist."""
    credentials_exception = HTTPException(status_code=401, detail="Unauthorized")
    auth_header = request.headers.get("authorization") or ""
    token = auth_header.removeprefix("Bearer ").strip() or request.cookies.get(ADMIN_TOKEN_COOKIE)
    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
        sub = payload.get("sub")
        if sub is None or not str(sub).isdigit():
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    vk_id = int(sub)
    if not is_admin_allowed(vk_id):
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    return vk_id
