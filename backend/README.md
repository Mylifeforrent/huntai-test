# backend — HuntAI Test API

后端源码与工程配置。配置从**仓库根目录** `.env` 加载（非 `backend/.env`）。

## 前置条件

- Python 3.14（`uv python install 3.14`）
- PostgreSQL（本地测试使用 14；`DATABASE_URL` 指向目标库）
- 仓库根 `.env` 已按 `.env.example` 填写全部必填键

## 安装依赖

```bash
cd backend
uv sync
```

## 数据库迁移

```bash
cd backend
uv run alembic upgrade head
```

回滚一步：

```bash
uv run alembic downgrade -1
```

## 启动服务

```bash
cd backend
uv run uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-8000} --reload
```

`APP_PORT` 取自仓库根 `.env` 的 `APP_PORT`。

## 前后端联调（OIDC + 会话 Cookie）

前端 Vite 将 `/api` 代理到 `http://127.0.0.1:8000`，浏览器侧请使用 `http://127.0.0.1:5173` 访问 SPA，API 走同源 `/api/v1`（无需把 `VITE_API_BASE_URL` 指到 `:8000`）。

本地 HTTP 联调时，浏览器会丢弃 `Secure` Cookie。仓库根 `.env` 必须显式设置：

- `SESSION_COOKIE_SECURE=false`（生产 HTTPS 设为 `true`）
- `SESSION_COOKIE_SAMESITE=Lax`（或按 IdP 要求）

OIDC 回调地址必须是**浏览器可达**的 URL，经 Vite 代理转发到后端，例如：

```text
OIDC_REDIRECT_URI=http://127.0.0.1:5173/api/v1/auth/oidc/callback
```

API-002 成功后会 `302` 到相对 `return_path`（如 `/projects`），并 `Set-Cookie` 会话；前端 SessionGate 经 API-005 探测会话后再渲染壳层。

典型联调步骤（含本地 mock IdP）：

1. 仓库根 `.env` 填齐 `.env.example` 键，本地建议：
   - `SESSION_COOKIE_SECURE=false`
   - `OIDC_REDIRECT_URI=http://127.0.0.1:5173/api/v1/auth/oidc/callback`
   - `OIDC_ISSUER=http://127.0.0.1:8090`
   - `OIDC_CLAIM_SUBJECT=sub`
2. `cd backend && uv run alembic upgrade head`
3. `uv run python scripts/seed_local_identity.py`（写入 `idp_subject=local-dev-user` 的租户/用户/项目，无 JIT）
4. 三个进程：`uv run uvicorn app.main:app --reload`、`uv run python scripts/mock_idp.py`、前端 `npm run dev`
5. 打开 `http://127.0.0.1:5173/` → SessionGate 跳到 mock IdP。无 mock SSO cookie 时出示合成账号表单（用户名 `local-dev-user` / 口令 `local-dev`，仅 loopback mock，不是产品密钥）。「模拟 SSO 失败返回应用」会回到 SPA 恢复面；再点「使用企业账号重新登录」会带 `prompt=login` 回到 IdP 表单。

`scripts/mock_idp.py` 仅 loopback，不是产品端点，不可用于非开发环境。

## 测试

```bash
cd backend
uv run pytest
```

## 静态检查

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app
```
