# Stage 12 · 部署方案、环境配置、CI/CD 与回滚预案

> - **阶段**：Stage 12（`docs/12_deployment`）—— 发布和部署
> - **日期**：2026-09-12
> - **代码基线**：分支 `feat/stage12-deployment`（基于 `main` `f7025d5`）
> - **权威**：部署形态与硬约束引用 [tech_stack_decision-v1.0.md](../06_architecture_design/tech_stack_decision-v1.0.md) §3.8、[AGENTS.md](../../AGENTS.md) §1/§6、[project_rules.md](../00_setup/project_rules.md) §2/§5.3。本文**不新增** US / FR / AC / API 编号，**不发明** TBD 数值（RPO/RTO、SLO、会话秒数、K8s 时点等一律留空并登记）。
> - **配套产出**：`backend/Dockerfile`、`backend/.dockerignore`、`frontend/Dockerfile`、`frontend/nginx.conf`、`frontend/.dockerignore`；探针代码 `backend/app/api/ops.py`

## 1. 范围与冻结约束

`docs/12_deployment/README.md` 要求本文覆盖四项：部署方案、环境配置说明、CI/CD 配置说明、发布清单与回滚预案。

来自已冻结决策的硬约束（不得用实现便利覆盖）：

| 约束 | 出处 |
|---|---|
| 构建产物是**容器镜像**；前端打静态资源，**禁止单独跑 Node 运行时** | `AGENTS.md` §6；`tech_stack_decision-v1.0.md` §3.8 |
| 前期 docker compose 单机 → 后期**同一批镜像**上 Kubernetes；**只换编排层，不改应用代码形态** | `tech_stack_decision-v1.0.md` §3.8 |
| 配置**全部经环境变量注入**；**日志写 stdout**；**进程无本地业务状态**（M0/M1 制品卷是唯一例外） | `tech_stack_decision-v1.0.md` §3.8 |
| 依赖管理 uv 0.12.7 + `uv.lock`；npm + `package-lock.json`；锁文件变更独立成 commit | `tech_stack_decision-v1.0.md` §3.8 |
| M0/M1 秘密经 `.env` + Docker secret；业务库只存引用；`.env.example` 只含键名 | `AGENTS.md` §4 |
| M0/M1 数据面只有单 PostgreSQL；Temporal / Redis / MinIO / Vault **不启用** | `architecture.md` §15.1 |
| 无法本地验证的变更必须记录验证方式与验证人 | `project_rules.md` §5.3 |

## 2. 镜像与构建

### 2.1 后端 `backend/Dockerfile`

多阶段，构建上下文为 `backend/`：

1. **builder**（`python:3.14-slim`）：从 `ghcr.io/astral-sh/uv:0.12.7` 复制 uv（冻结版本），`uv sync --frozen --no-dev` 装到 `/opt/venv`，再 `playwright install chromium` 只取浏览器二进制。
2. **runtime**（`python:3.14-slim`）：先复制 venv，再 `playwright install-deps chromium` 装浏览器所需的系统库（顺序不可颠倒——`install-deps` 从 venv 解析 CLI），复制浏览器目录与应用层，`useradd` 后以非 root（uid 10001）运行。

| 项 | 值 |
|---|---|
| 入口 | `uvicorn app.main:app --host 0.0.0.0 --port ${APP_PORT:-8000}` |
| 端口 | 8000（`APP_PORT`） |
| 构建期秘密 | **无**。配置在运行时注入；`.dockerignore` 排除 `.env`、`.env.*`、`*.pem`、`*.key`，即使上下文放宽也不会把秘密打进镜像 |
| 镜像内默认制品目录 | `/data/artifacts`（仅让裸 `docker run` 不因首次写制品失败；实际路径由 `ARTIFACT_ROOT` 决定，必须挂持久卷） |
| 自检 | `HEALTHCHECK` 打 `/healthz` |

**关于 Playwright（取舍）**：`playwright` 属于主依赖组，M2 的 Web 执行由 `playwright_worker.py` 以子进程调用它，镜像不装浏览器则容器内 Web 用例不可用。因此默认装 chromium。**代价是镜像体积显著增大**；替代方案是拆分「执行器镜像」（Web/性能 worker 单独镜像，API 镜像保持精简）——见 §11 开放项。

**关于 `pytest` 出现在运行时镜像**：`locust`（性能执行包装，S-M3-01 主依赖）自身依赖 `pytest`，因此 `--no-dev` 后 `pytest` 仍会随 `locust` 进入镜像。这是传递依赖，不是 `--no-dev` 失效——`ruff` / `mypy` / `pytest-asyncio` 确认不在运行时依赖中。

### 2.2 前端 `frontend/Dockerfile`

多阶段，构建上下文为 `frontend/`：

1. **builder**（`node:24-slim`，冻结 Node 24 LTS）：`npm ci`（自动读取 `.npmrc` 的 `legacy-peer-deps=true`）→ `npm run build`（`tsc -b && vite build`）。
2. **runtime**（`nginx:alpine`）：只复制 `dist/` 与站点配置，**不含 Node 运行时**。

| 项 | 值 |
|---|---|
| 端口 | 80 |
| API 基址 | 默认**同源** `/api/v1`（`VITE_API_BASE_URL` 留空）。该值由 Vite 在**构建期**静态替换，故仅在需要跨源 API 时用 `--build-arg VITE_API_BASE_URL=...` 注入 |
| 站点配置 | `frontend/nginx.conf` 作为 **server block** 复制到 `/etc/nginx/conf.d/default.conf`（不是替换整份 `nginx.conf`） |

站点配置要点：hashed 资源长缓存（`/assets/` immutable）、`index.html` 不缓存、SPA fallback `try_files $uri $uri/ /index.html`、`/api/` 反代到 `http://backend:8000`（上游名与 compose 服务名一致，K8s 下换成 Service 名）、**SSE 关闭 `proxy_buffering`**（否则进度流会卡住）、`/healthz` 与 `/readyz` 在边缘返回 404（探针只供编排层在内部网络访问，不对外暴露）。

## 3. 运行拓扑（compose 单机）

四个服务：`postgres`（`postgres:18`，命名卷 `pgdata`）→ `migrate`（一次性，`alembic upgrade head`）→ `backend` → `frontend`（唯一的对外端口）。启动顺序由 `depends_on` 的条件表达：`postgres` 健康 → `migrate` 成功退出 → `backend` 健康 → `frontend`。

**为什么迁移是独立服务**：迁移需要 Postgres 先行可达，且多副本滚动时必须只跑一次；放在应用启动钩子里会导致并发迁移与启动耦合。

> ✅ **已落地**：顶层白名单已于 2026-09-12 经用户批准修订（登记见 `docs/13_changes/change_log.md`），本片段与仓库根 `docker-compose.yml` 内容一致。校验：`POSTGRES_PASSWORD=… docker compose config -q` 退出码 0（相对 context 正确解析到 `backend/`、`frontend/`），缺 `POSTGRES_PASSWORD` 时报错退出。

```yaml
name: huntai-test

services:
  postgres:
    image: postgres:18
    environment:
      POSTGRES_DB: huntai
      POSTGRES_USER: huntai
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U huntai -d huntai"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  migrate:
    build:
      context: ./backend
    command: ["alembic", "upgrade", "head"]
    env_file: [.env]
    environment:
      DATABASE_URL: postgresql+asyncpg://huntai:${POSTGRES_PASSWORD:?}@postgres:5432/huntai
    depends_on:
      postgres:
        condition: service_healthy
    restart: "no"

  backend:
    build:
      context: ./backend
    env_file: [.env]
    environment:
      DATABASE_URL: postgresql+asyncpg://huntai:${POSTGRES_PASSWORD:?}@postgres:5432/huntai
      ARTIFACT_ROOT: /data/artifacts
    volumes:
      - artifacts:/data/artifacts
    depends_on:
      postgres:
        condition: service_healthy
      migrate:
        condition: service_completed_successfully
    healthcheck:
      test: ["CMD", "python", "-c", "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
      args:
        VITE_API_BASE_URL: ""
    ports:
      - "${HTTP_PORT:-8080}:80"
    depends_on:
      backend:
        condition: service_healthy
    restart: unless-stopped

volumes:
  pgdata:
  artifacts:
```

`environment` 优先于 `env_file`，因此 `DATABASE_URL` 在容器内被改写为 `postgres` 主机（仓库根 `.env` 里通常指向 `127.0.0.1`，那是本地裸跑用的）。

**迁移到 Kubernetes 的约束**：同一批镜像、同一套环境变量、同一个 `/data/artifacts` 语义（换成 PVC）、同样的 stdout 日志与探针路径。K8s 清单形态、Ingress/网关选型与迁移时点是 `tech_stack_decision-v1.0.md` 登记的 **G4 开放项**，本文不发明。

## 4. 环境配置说明

后端 `Settings` 有 **18 个必填键**（缺任何一个进程起不来）与 7 个可选键。全部经环境变量注入，**代码不硬编码配置值**。

| 类别 | 键 |
|---|---|
| 必填 · 应用 | `APP_ENV`、`APP_PORT`、`LOG_LEVEL`、`DATABASE_URL` |
| 必填 · 会话 | `SESSION_COOKIE_NAME`、`SESSION_COOKIE_SAMESITE`、`SESSION_COOKIE_SECURE`、`SESSION_TTL_SECONDS`、`OIDC_LOGIN_DRAFT_TTL_SECONDS`、`REAUTH_WINDOW_SECONDS`、`APPROVAL_TTL_SECONDS` |
| 必填 · OIDC | `OIDC_ISSUER`、`OIDC_CLIENT_ID`、`OIDC_CLIENT_SECRET`、`OIDC_REDIRECT_URI`、`OIDC_CLAIM_SUBJECT` |
| 必填 · 集成与制品 | `GITHUB_WEBHOOK_SECRET`、`ARTIFACT_ROOT` |
| 可选 | `JENKINS_WEBHOOK_SECRET`、`JENKINS_API_TOKEN`、`TEST_RUN_HEARTBEAT_TIMEOUT_SECONDS`、`CI_LOG_CHUNK_BYTES`、`CI_LOG_MAX_TOTAL_BYTES`、`REPORT_PARSE_TIMEOUT_SECONDS`、`REPORT_PARSE_BATCH_ROWS` |
| 仅供 compose 插值 | `POSTGRES_PASSWORD`（见 §11.2）、`HTTP_PORT` |

生产环境要求：

- `APP_ENV=production` 时 **`OIDC_ISSUER` 指向 loopback（`localhost` / `127.0.0.1` / `::1` / `0.0.0.0`）会直接拒绝启动**——防止把本地 mock IdP 带上生产（`config.py` 的 `reject_local_mock_idp_in_production`）。
- 生产必须 `SESSION_COOKIE_SECURE=true`（本地 HTTP 联调才设 `false`）。
- `.env` **不入库**（`.gitignore`）；`.env.example` 只放键名与说明，**不填真实值**。M0/M1 秘密经 `.env` + Docker secret。
- 密钥类值禁止进入镜像、日志、Trace、错误体（构建期已用 `.dockerignore` 排除 `.env`）。

## 5. 数据、迁移与制品卷

- **迁移**：`alembic upgrade head`，由 compose 的 `migrate` 服务或 K8s 的一次性 Job 执行，**不在应用启动时自动跑**。`alembic/env.py` 的 URL 来自 `get_settings().database_url`（同一套环境变量），`alembic.ini` 里的 URL 只是占位符。
- **制品卷**：`ARTIFACT_ROOT` 必须指向可写且**持久**的卷。本地卷布局为 `<organization_id>/<artifact_id>/<sanitized_filename>`，另有 worker 用的 `tmp/`。**M0/M1 不启用 MinIO**（`architecture.md` §15.1）；启用 MinIO 前需先迁移本地卷制品并校验 checksum，否则迁移会退化成代码改动。
- **无本地业务状态**：除制品卷外，进程不持有本地业务状态，这是 compose → K8s 只换编排层的前提。
- **PostgreSQL 版本**：技术栈冻结 PostgreSQL 18；`backend/README.md` 记录本地测试曾用 14。

## 6. 探针与健康检查

| 路径 | 语义 | 行为 |
|---|---|---|
| `GET /healthz` | 存活（liveness） | 200 `{"status":"ok"}`；**不触库**，只证明进程在服务 |
| `GET /readyz` | 就绪（readiness） | 执行 `SELECT 1`；可达 200 `{"status":"ready"}`，不可达 503 `{"status":"not_ready"}` |

两条硬性质：

1. **匿名可达且不泄露内部信息**。探针不经认证，因此失败响应是固定文案，不含 DSN、驱动原文、堆栈或异常类型。已由 `backend/tests/test_ops_probes.py` 钉住（用带假密码的 DSN 构造失败，断言响应体不含 `sup3r-s3cret` / `postgresql` / `db.internal` / `RuntimeError`）。
2. **它们不是产品 API**。探针位于 `/api/v1` **之外**、不占 API 编号、不写入 `api_spec.md`——产品 API 一律在 `/api/v1` 的约定不受影响。为免将来「新增未登记路由」，它们已登记进 `backend/tests/test_route_auth_conformance.py` 的 `PUBLIC_ROUTES`（带理由），受认证一致性测试约束。

边缘行为：nginx 对 `/healthz`、`/readyz` 返回 404，探针只在内部网络（compose 网络 / K8s Pod 网络）可达。

## 7. CI/CD 配置说明

`project_rules.md` §5.3 规定 **CI 由 Stage 12 引入，且「CI 为绿」是判定标准**。门控命令与本地完全一致，不另立一套：

| Job | 命令 |
|---|---|
| backend | `uv sync --frozen` → `uv run ruff check .` → `uv run ruff format --check .` → `uv run mypy app` → `uv run pytest` |
| frontend | `npm ci` → `npm run lint` → `npx tsc --noEmit` → `npm run build` → `npm run test` |
| images | `docker build backend` + `docker build frontend` |

`pytest` 需要 PostgreSQL：CI 用 service 容器提供，并通过 `DATABASE_URL` 指向它（`conftest.py` 优先读取已存在的 `DATABASE_URL`，取不到才回落到本地默认值）。

> ✅ **已落地**：`.github/` 已于 2026-09-12 经用户批准加入顶层白名单，本片段与 `.github/workflows/ci.yml` 内容一致（校验：YAML 可解析，3 个 job：`backend` / `frontend` / `images`）。**但「CI 为绿」尚未取得**——`gh` 在本环境未登录、无 PR 运行记录，首次真实运行结果仍属未验证项（见 §10.2 #6）。

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:18
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: huntai_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    env:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/huntai_test
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          version: "0.12.7"
      - run: uv python install 3.14
      - working-directory: backend
        run: uv sync --frozen
      - working-directory: backend
        run: |
          uv run ruff check .
          uv run ruff format --check .
          uv run mypy app
          uv run pytest

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "24"
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - working-directory: frontend
        run: npm ci
      - working-directory: frontend
        run: |
          npm run lint
          npx tsc --noEmit
          npm run build
          npm run test

  images:
    runs-on: ubuntu-latest
    needs: [backend, frontend]
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t huntai-backend:${{ github.sha }} backend
      - run: docker build -t huntai-frontend:${{ github.sha }} frontend
```

说明：`images` job 是**镜像可用性的唯一自动化验证**（本地无 Docker daemon）。action 版本此处用主版本标签；若组织要求供应链加固，应改为按 commit SHA 锁定（本仓库 `.pre-commit-config.yaml` 已有 gitleaks 秘密扫描门禁）。

## 8. 发布清单

1. 确认冻结门控全绿：backend 四条 + frontend 四条命令零失败。
2. 确认 `uv.lock` / `package-lock.json` 与 `pyproject.toml` / `package.json` **同 commit 一致**（`uv lock --check`、`npm ci` 不报 lockfile 失配）。
3. 确认镜像构建通过并打上**不可变 tag**（建议 commit SHA），不要只用 `latest`。
4. 确认目标环境的环境变量齐备：§4 的 18 个必填键与所需可选键；生产必须 `SESSION_COOKIE_SECURE=true` 且 `APP_ENV=production`（后者会拒绝 loopback issuer）。
5. 执行 `alembic upgrade head`（独立步骤），确认无待应用迁移。
6. 确认 `ARTIFACT_ROOT` 指向持久卷且运行用户可写。
7. 滚动更新应用，等待 `/readyz` 返回 200 后再放量。
8. 发布后核查：`/healthz` 200、`/readyz` 200、登录链路可完成、日志出现在 stdout。
9. 记录本次发布：镜像 tag、迁移 revision、发布人、时间。

## 9. 回滚预案

| 层 | 手段 |
|---|---|
| 应用 | 回滚到上一镜像 tag（compose：`docker compose up -d` 指定旧 tag；K8s：`kubectl rollout undo`）。镜像不变、只换编排层的前提使该操作不需要改配置 |
| 数据 | 迁移必须**向前兼容**：回滚应用镜像时数据库保持新 schema，不执行 `alembic downgrade`（除非该迁移明确提供安全降级路径） |
| 配置 | 环境变量随编排层回滚；`.env` 变更需与镜像 tag 一并记录 |
| 外部副作用 | 不在本文范围——外部写入的补偿见 PRD 附录 C.4（回滚策略以 compensation 为主，不自动删外部对象） |

**不在本文定义**：RPO/RTO 与备份恢复拓扑全部 TBD（`architecture.md` §14.2 / Q11、`tech_stack_decision` G5）。「备份成功不等于可恢复」，正式放量前必须在隔离环境演练——本文不发明恢复目标值。

## 10. 验证方式与验证人（`project_rules.md` §5.3）

### 10.1 已本地验证（2026-09-12）

| 验证项 | 命令 | 结果 |
|---|---|---|
| 后端静态检查与测试 | `uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest` | ruff 通过、`202 files already formatted`、mypy `117 source files` 无问题、**`445 passed, 8 skipped, 4 warnings in 107.25s`** |
| 前端门控 | `npm run lint && npx tsc --noEmit && npm run build && npm run test` | lint/tsc 零错误、build 成功、**`Test Files 33 passed` / `Tests 112 passed`** |
| 后端镜像依赖层（Dockerfile 第 1 步本体） | `UV_PROJECT_ENVIRONMENT=/tmp/... uv sync --frozen --no-dev` | 成功；`fastapi/uvicorn/sqlalchemy/alembic/asyncpg/authlib/playwright/locust` 均可导入；`ruff`/`mypy`/`pytest-asyncio` 确认不在运行时依赖中 |
| 锁文件冻结一致性 | `uv lock --check` | 通过 |
| 前端镜像构建步骤本体 | `npm ci && npm run build`（`VITE_API_BASE_URL` 留空） | `npm ci` 329 包、0 漏洞、lockfile 无失配；build 成功（同源默认基址生效） |
| compose 结构（仓内 `docker-compose.yml`） | `POSTGRES_PASSWORD=… docker compose config -q` | 退出码 0，无错误/告警；相对 `build.context` 正确解析到 `backend/`、`frontend/`；缺 `POSTGRES_PASSWORD` 时**报错退出**（符合预期）。**说明**：这是无 daemon 的客户端解析——验证 YAML 结构、变量插值、`depends_on` 条件与 context 解析，**未验证**镜像构建与容器启动 |
| CI workflow 结构 | `yaml.safe_load` 解析 + job/step 计数 | 可解析；3 个 job（`backend` / `frontend` / `images`）、触发器 `push`(main) + `pull_request`，与文档片段一致 |
| 探针行为 | `uv run pytest tests/test_ops_probes.py` | 3 条通过：匿名 200、就绪 200、失败 503 且不泄露内部信息 |
| 路由认证一致性（含新探针） | `uv run pytest tests/test_route_auth_conformance.py` | 4 条通过 |

### 10.2 未本地验证（必须据此记录，不得声称已验证）

本地 **Docker daemon 未运行**（`docker info` 连接 `unix:///Users/.../docker.sock` 失败）、**`gh` 未登录**，因此以下均未验证：

| # | 未验证项 | 验证方式 | 验证人 |
|---|---|---|---|
| 1 | 后端镜像能否真正构建 | 有可用 daemon 的环境执行 `docker build backend`；或 CI `images` job | 待指定 |
| 2 | 前端镜像能否真正构建、nginx 站点配置是否生效 | `docker build frontend` 后 `docker run -p 8080:80` 访问页面与 `/api` | 待指定 |
| 3 | compose 能否真正起来（含 `migrate` 顺序、健康门控、卷挂载） | `docker compose up -d` 后核查四个服务状态与 `/readyz` | 待指定 |
| 4 | Playwright 浏览器与系统库在镜像内是否可执行 | 镜像内跑一次 Web 用例（`playwright_worker`） | 待指定 |
| 5 | 基础镜像 tag 是否可用（`python:3.14-slim`、`node:24-slim`、`postgres:18`、`nginx:alpine`、`ghcr.io/astral-sh/uv:0.12.7`） | 首次构建即验证；`uv` 0.12.7 已确认存在于 PyPI（发布物存在） | 待指定 |
| 6 | CI 是否真能跑绿 | 落到 `.github/workflows/` 后在 PR 上运行（依赖 §11.1 裁定） | 待指定 |
| 7 | 生产 IdP 真实对接 | 见 [test_report.md](../11_test/test_report.md) §7.4；真实凭证与端到端仍不可验证 | 待指定 |

## 11. 已裁定事项与开放项

两处原先待裁定的冻结资产改动（§11.1、§11.2）已于 2026-09-12 经用户批准落地；其余开放项见 §11.3，均为「登记不发明」。

### 11.1 已裁定：compose 与 CI 工作流的仓内落位（2026-09-12）

原先受阻于 `AGENTS.md` §1 / `project_rules.md` §2 的顶层白名单为封闭列表（不含 `docker-compose.yml` 与 `.github/`）。**已按 R2 流程闭环**：

1. 登记 `docs/13_changes/change_log.md`（2026-09-12 行）。
2. 获用户显式批准。
3. 同步修订 `AGENTS.md` §1 与 `project_rules.md` §2（两处同改，均限定这两个条目只用于 Stage 12 的编排与 CI 门控，且 CI 门控命令必须与 §5 一致）。
4. 落地仓库根 `docker-compose.yml` 与 `.github/workflows/ci.yml`。

**剩余缺口（据实登记）**：`project_rules.md` §5.3 的「CI 为绿」需要一次真实 CI 运行才能判定，本环境 `gh` 未登录、无法触发或观测，因此该判定标准**尚未取得**，不得视为已闭环。

### 11.2 已裁定：`.env.example` 新增键（2026-09-12）

compose 用 `POSTGRES_PASSWORD` 注入数据库口令（`POSTGRES_DB`/`POSTGRES_USER` 已固定在 compose 内，非秘密）。已在 `.env.example` 的「部署（docker compose，Stage 12）」段增补 `POSTGRES_PASSWORD=`（仅键名与说明，不填值），并随本次白名单修订一并登记 change_log。`HTTP_PORT` 不入 `.env.example`——compose 已给默认值 `8080`。

### 11.3 其他开放项（登记，不发明）

| # | 开放项 | 归属 |
|---|---|---|
| 1 | K8s 迁移时点、清单形态、Ingress/网关选型 | `tech_stack_decision-v1.0.md` G4 → 本文（未裁定，需用户裁决） |
| 2 | PostgreSQL HA / 备份 / RPO / RTO | `tech_stack_decision` G5、`architecture.md` Q11（TBD） |
| 3 | 执行器是否拆分为独立镜像（减小 API 镜像体积） | 本文 §2.1 取舍，待评估 |
| 4 | 基础镜像与 action 版本是否按 SHA 锁定 | 组织供应链策略 |
| 5 | SLO 目标值（P95 等） | `architecture.md` §14.1 明确仍为假设/TBD，不得当部署默认 |
