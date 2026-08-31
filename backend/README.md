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
