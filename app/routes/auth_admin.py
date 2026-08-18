"""/pay/api/auth/* — вход в админку через VK ID (PKCE), me, dev-login (только dev)."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

import config
from auth import (
    ADMIN_TOKEN_COOKIE, compute_code_challenge, create_access_token,
    exchange_vk_code, generate_code_verifier, generate_state, get_current_admin,
    get_vk_login_url, get_vk_user_info, is_admin_allowed, set_oauth_cookies,
    STATE_COOKIE, CODE_VERIFIER_COOKIE,
)

router = APIRouter(prefix="/pay/api/auth", tags=["admin-auth"])


@router.get("/vk-login")
def vk_login():
    state = generate_state()
    verifier = generate_code_verifier()
    response = RedirectResponse(get_vk_login_url(state, compute_code_challenge(verifier)))
    set_oauth_cookies(response, state, verifier)
    return response


@router.get("/vk-callback")
async def vk_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code:
        raise HTTPException(status_code=400, detail="missing code")

    cookie_state = request.cookies.get(STATE_COOKIE)
    verifier = request.cookies.get(CODE_VERIFIER_COOKIE)
    if not cookie_state or not verifier:
        raise HTTPException(status_code=400, detail="oauth cookies not found")
    if state and state != cookie_state:
        raise HTTPException(status_code=400, detail="state mismatch")

    # VK ID code_v2 привязывает код к device_id из колбэка — использовать его
    device_id = request.query_params.get("device_id") or secrets.token_hex(16)
    token_data = await exchange_vk_code(code, verifier, device_id, state or "")
    user_info = await get_vk_user_info(token_data.get("access_token", ""))
    try:
        vk_id = int(user_info.get("user_id") or user_info.get("id") or 0)
    except (ValueError, TypeError):
        vk_id = 0
    if not vk_id or not is_admin_allowed(vk_id):
        return JSONResponse({"error": "access denied"}, status_code=403)

    jwt_token = create_access_token(vk_id)
    redirect = RedirectResponse(f"{config.SITE_URL}/pay/admin/")
    redirect.set_cookie(
        key=ADMIN_TOKEN_COOKIE, value=jwt_token,
        max_age=config.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=False, samesite="lax", secure=True,
    )
    redirect.delete_cookie(STATE_COOKIE)
    redirect.delete_cookie(CODE_VERIFIER_COOKIE)
    return redirect


@router.get("/me")
def me(vk_id: int = Depends(get_current_admin)):
    return {"vk_id": vk_id, "ok": True}


@router.post("/logout")
def logout():
    """Сброс cookie-токена админки."""
    response = JSONResponse({"ok": True})
    response.delete_cookie(ADMIN_TOKEN_COOKIE)
    return response


class DevLoginBody(BaseModel):
    vk_id: int


@router.post("/dev-login")
def dev_login(body: DevLoginBody):
    """Только APP_ENV=dev (для локальной разработки/тестов без VK)."""
    if not config.DEV_LOGIN_ENABLED:
        raise HTTPException(status_code=404, detail="Not Found")
    if not is_admin_allowed(body.vk_id):
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    return {"access_token": create_access_token(body.vk_id), "token_type": "bearer"}
