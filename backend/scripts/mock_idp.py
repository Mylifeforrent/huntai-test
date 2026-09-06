"""Local-only OIDC mock. Not a product API. Do not use outside development."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import uvicorn
from authlib.jose import JsonWebKey
from authlib.jose import jwt as jose_jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.core.config import get_settings

MOCK_SUBJECT = "local-dev-user"
# Local mock only (loopback). Not a HuntAI product password and not stored in the app DB.
MOCK_PASSWORD = "local-dev"
MOCK_SSO_COOKIE = "huntai_mock_sso"
CODE_TTL = timedelta(minutes=5)
ID_TOKEN_TTL = timedelta(minutes=5)


@dataclass
class AuthCode:
    redirect_uri: str
    nonce: str
    code_challenge: str
    client_id: str
    expires_at: datetime


_private_jwk: Any = None
_public_jwk_dict: dict[str, Any] | None = None
_codes: dict[str, AuthCode] = {}


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _s256(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())


def _ensure_key() -> None:
    global _private_jwk, _public_jwk_dict
    if _private_jwk is not None:
        return
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = rsa_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    _private_jwk = JsonWebKey.import_key(pem)
    public = dict(_private_jwk.as_dict(is_private=False))
    thumbprint = _private_jwk.thumbprint()
    public["kid"] = thumbprint if isinstance(thumbprint, str) else _b64url(thumbprint)
    public["use"] = "sig"
    public["alg"] = "RS256"
    _public_jwk_dict = public


def _issuer() -> str:
    return get_settings().oidc_issuer.rstrip("/")


def _require_loopback_issuer() -> None:
    parsed = urlparse(_issuer())
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise SystemExit("mock IdP only listens on loopback; set OIDC_ISSUER=http://127.0.0.1:8090")


app = FastAPI(title="HuntAI local mock IdP", docs_url=None, redoc_url=None)


@app.get("/.well-known/openid-configuration")
def openid_configuration() -> dict[str, str]:
    issuer = _issuer()
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "jwks_uri": f"{issuer}/jwks",
        "response_types_supported": "code",
        "id_token_signing_alg_values_supported": "RS256",
        "code_challenge_methods_supported": "S256",
    }


@app.get("/jwks")
def jwks() -> dict[str, list[dict[str, Any]]]:
    _ensure_key()
    assert _public_jwk_dict is not None
    return {"keys": [_public_jwk_dict]}


def _issue_code_redirect(
    *,
    redirect_uri: str,
    state: str,
    nonce: str,
    code_challenge: str,
    client_id: str,
    set_sso_cookie: bool,
) -> RedirectResponse:
    code = secrets.token_urlsafe(32)
    _codes[code] = AuthCode(
        redirect_uri=redirect_uri,
        nonce=nonce,
        code_challenge=code_challenge,
        client_id=client_id,
        expires_at=datetime.now(UTC) + CODE_TTL,
    )
    query = urlencode({"code": code, "state": state})
    response = RedirectResponse(url=f"{redirect_uri}?{query}", status_code=302)
    if set_sso_cookie:
        response.set_cookie(MOCK_SSO_COOKIE, "1", httponly=True, samesite="lax")
    return response


def _login_form(
    *,
    redirect_uri: str,
    state: str,
    nonce: str,
    code_challenge: str,
    client_id: str,
    message: str,
    error: str = "",
) -> HTMLResponse:
    error_html = f"<p style='color:#b42318'>{escape(error)}</p>" if error else ""
    return HTMLResponse(
        f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>Mock IdP</title></head>
<body style="font-family:sans-serif;max-width:32rem;margin:4rem auto;line-height:1.5">
  <h1>本地 Mock 身份提供商</h1>
  <p>这不是 HuntAI 产品登录页。企业 SSO 上线后由真实 IdP 替换。</p>
  <p>{escape(message)}</p>
  <p>合成账号 <code>{escape(MOCK_SUBJECT)}</code>
     须与库中 <code>users.idp_subject</code> 一致（无 JIT）。
     合成口令仅 mock 进程内比对，不是产品密钥。</p>
  {error_html}
  <form method="post" action="/authorize/complete">
    <input type="hidden" name="redirect_uri" value="{escape(redirect_uri, quote=True)}">
    <input type="hidden" name="state" value="{escape(state, quote=True)}">
    <input type="hidden" name="nonce" value="{escape(nonce, quote=True)}">
    <input type="hidden" name="code_challenge" value="{escape(code_challenge, quote=True)}">
    <input type="hidden" name="client_id" value="{escape(client_id, quote=True)}">
    <p><label>用户名 <input name="username" autocomplete="username"></label></p>
    <p>
      <label>密码
        <input name="password" type="password" autocomplete="current-password">
      </label>
    </p>
    <button type="submit" style="padding:.6rem 1rem">使用企业账号登录</button>
  </form>
  <form method="get" action="/authorize/fail" style="margin-top:1.5rem">
    <input type="hidden" name="redirect_uri" value="{escape(redirect_uri, quote=True)}">
    <input type="hidden" name="state" value="{escape(state, quote=True)}">
    <button type="submit">模拟 SSO 失败返回应用</button>
  </form>
</body>
</html>"""
    )


@app.get("/authorize")
def authorize(
    request: Request,
    response_type: str = Query(default=""),
    client_id: str = Query(default=""),
    redirect_uri: str = Query(default=""),
    state: str = Query(default=""),
    nonce: str = Query(default=""),
    code_challenge: str = Query(default=""),
    code_challenge_method: str = Query(default=""),
    scope: str = Query(default=""),
    prompt: str = Query(default=""),
) -> HTMLResponse | RedirectResponse:
    _ = scope
    settings = get_settings()
    errors: list[str] = []
    if response_type != "code":
        errors.append("response_type 必须是 code")
    if client_id != settings.oidc_client_id:
        errors.append("client_id 不匹配")
    if redirect_uri != settings.oidc_redirect_uri:
        errors.append("redirect_uri 不匹配")
    if not state or not nonce or not code_challenge:
        errors.append("缺少 state / nonce / code_challenge")
    if code_challenge_method != "S256":
        errors.append("code_challenge_method 必须是 S256")

    if errors:
        body = "<br>".join(errors)
        return HTMLResponse(f"<h1>Mock IdP 拒绝授权</h1><p>{body}</p>", status_code=400)

    if prompt != "login" and request.cookies.get(MOCK_SSO_COOKIE) == "1":
        return _issue_code_redirect(
            redirect_uri=redirect_uri,
            state=state,
            nonce=nonce,
            code_challenge=code_challenge,
            client_id=client_id,
            set_sso_cookie=False,
        )

    message = (
        "已按 prompt=login 要求出示账号密码表单。"
        if prompt == "login"
        else "企业 SSO 未成功，请输入公司账号密码。"
    )
    return _login_form(
        redirect_uri=redirect_uri,
        state=state,
        nonce=nonce,
        code_challenge=code_challenge,
        client_id=client_id,
        message=message,
    )


@app.post("/authorize/complete")
async def authorize_complete(request: Request) -> HTMLResponse | RedirectResponse:
    settings = get_settings()
    raw = (await request.body()).decode("utf-8")
    form = {key: values[-1] for key, values in parse_qs(raw, keep_blank_values=True).items()}
    redirect_uri = form.get("redirect_uri", "")
    state = form.get("state", "")
    nonce = form.get("nonce", "")
    code_challenge = form.get("code_challenge", "")
    client_id = form.get("client_id", "")
    username = form.get("username", "")
    password = form.get("password", "")
    if client_id != settings.oidc_client_id or redirect_uri != settings.oidc_redirect_uri:
        return HTMLResponse("<h1>Mock IdP 拒绝授权</h1>", status_code=400)
    if username != MOCK_SUBJECT or password != MOCK_PASSWORD:
        return _login_form(
            redirect_uri=redirect_uri,
            state=state,
            nonce=nonce,
            code_challenge=code_challenge,
            client_id=client_id,
            message="企业 SSO 未成功，请输入公司账号密码。",
            error="用户名或密码不正确。",
        )
    return _issue_code_redirect(
        redirect_uri=redirect_uri,
        state=state,
        nonce=nonce,
        code_challenge=code_challenge,
        client_id=client_id,
        set_sso_cookie=True,
    )


@app.get("/authorize/fail")
def authorize_fail(
    redirect_uri: str = Query(default=""),
    state: str = Query(default=""),
) -> RedirectResponse:
    settings = get_settings()
    if redirect_uri != settings.oidc_redirect_uri:
        return RedirectResponse(url="/authorize", status_code=303)
    query = urlencode({"error": "login_required", "state": state})
    return RedirectResponse(url=f"{redirect_uri}?{query}", status_code=302)


def _client_id_secret(request: Request, form: dict[str, str]) -> tuple[str, str]:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("basic "):
        raw = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
        client_id, _, client_secret = raw.partition(":")
        return client_id, client_secret
    return form.get("client_id", ""), form.get("client_secret", "")


@app.post("/token")
async def token(request: Request) -> JSONResponse:
    settings = get_settings()
    raw = (await request.body()).decode("utf-8")
    form = {key: values[-1] for key, values in parse_qs(raw, keep_blank_values=True).items()}
    client_id, client_secret = _client_id_secret(request, form)
    if client_id != settings.oidc_client_id or client_secret != settings.oidc_client_secret:
        return JSONResponse({"error": "invalid_client"}, status_code=401)
    if form.get("grant_type") != "authorization_code":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    code = form.get("code", "")
    record = _codes.pop(code, None)
    now = datetime.now(UTC)
    if record is None or now >= record.expires_at:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    if form.get("redirect_uri") != record.redirect_uri:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)
    verifier = form.get("code_verifier", "")
    if not verifier or _s256(verifier) != record.code_challenge:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)

    _ensure_key()
    assert _private_jwk is not None
    assert _public_jwk_dict is not None
    issued_at = int(now.timestamp())
    payload = {
        "iss": _issuer(),
        "aud": settings.oidc_client_id,
        "sub": MOCK_SUBJECT,
        "nonce": record.nonce,
        "iat": issued_at,
        "exp": issued_at + int(ID_TOKEN_TTL.total_seconds()),
        "email": "local-dev@example.test",
        "name": "Local Dev User",
    }
    header = {"alg": "RS256", "kid": _public_jwk_dict["kid"]}
    id_token = jose_jwt.encode(header, payload, _private_jwk)
    if isinstance(id_token, bytes):
        id_token = id_token.decode("ascii")
    return JSONResponse(
        {
            "access_token": "mock-access-not-used",
            "token_type": "Bearer",
            "expires_in": int(ID_TOKEN_TTL.total_seconds()),
            "id_token": id_token,
        }
    )


def main() -> None:
    _require_loopback_issuer()
    _ensure_key()
    parsed = urlparse(_issuer())
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8090
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
