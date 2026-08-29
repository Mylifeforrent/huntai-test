# 技术栈冻结决策（tech_stack_decision · v1.0）

> - **Status: 已冻结**
> - **日期**：2026-08-29 · **版本**：v1.0
> - **流程定位**：Stage 6（系统架构设计）**技术栈分册**——把前端框架 / UI 组件方案 / 状态管理 / 后端框架 / ORM / API 风格 / 测试框架 / 构建部署八类选型冻结到锁定版本；与 [architecture.md](architecture.md)（后端集成架构）、[frontend_design_spec-v1.0.md](frontend_design_spec-v1.0.md)（前端分册）、[frontend_backend_boundary_spec-v1.0.md](frontend_backend_boundary_spec-v1.0.md)（前后端边界分册）共同构成 Stage 6 产出
> - **上游输入**：[architecture.md](architecture.md)（运行单元、数据面边界、SSE/Webhook 原则、Temporal 集成协议）· [frontend_design_spec-v1.0.md](frontend_design_spec-v1.0.md) §1.3 技术基线 · [frontend_backend_boundary_spec-v1.0.md](frontend_backend_boundary_spec-v1.0.md) §3/§5/§7（数据归属、必调 API 类别、错误处理职责）· [project_rules.md](../00_setup/project_rules.md) §1.1/§1.2/§5（Stage 0 已冻结的语言、lint、测试基线）· [决策总纲](../README.md) §4.2/§6/§7（Playwright 执行引擎、ApiToken 哈希、限流归属、pgvector 起步）· [ADR 0002](adr/0002_durable_workflow_runtime.md)
> - **下游消费者**：[07_backend_design](../07_backend_design/README.md)（API 契约的实现约束）· Stage 11 前端初始化 · Stage 12 后端实施与部署
> - **收口纪律**：只冻结**实现所必需**的技术；Stage 0 已定项按继承处理不重开；新增依赖一律走红线 R4（批准 → 审计 → 落锁）；本文不含任何代码、DDL、迁移或部署清单
> - **不做什么**：不定义 API 路由与错误码 schema（归 07_backend_design）；不定义表结构与索引；不预建 `backend/` / `frontend/` 子目录（`project_rules.md` §2.5 要求子结构定稿后才建）；不锁定 M2+ 才启用组件的小版本

---

## 1. 冻结范围与判定原则

| # | 原则 | 执行标准 |
| --- | --- | --- |
| 1 | **只锁实现必需** | 每项选型必须能指向一条上游已定义的需求或约束；找不到出处的组件一律进 §6 不采纳清单 |
| 2 | **继承优先于重选** | Stage 0 `project_rules.md` 与 Stage 6 前端分册已定的选型只补版本号，不重开讨论；重开须走 `change_log` |
| 3 | **分期启用** | 目标架构组件与 M0/M1 实际运行组件分离登记（§5）；未到启用期的组件不锁小版本、不进依赖清单 |
| 4 | **单人可独立运维** | 每项选型须通过 §7 自评：无需专职团队即可完成安装、升级、排障、回滚 |
| 5 | **依赖四要素齐全** | 每个核心依赖必须同时给出锁定版本、License、维护活跃度证据、CVE 结论（§4）；缺一视为未完成审计 |

**冻结的八类**：前端框架、UI 组件方案、状态管理、后端框架、ORM、API 风格、测试框架、构建部署方式。

---

## 2. 冻结结论总表

| # | 类别 | 冻结结论 | 一句话理由 |
| --- | --- | --- | --- |
| 1 | 前端框架 | React 19.2.8 + TypeScript 7.0.2 + Vite 8.2.2 | Stage 0 已定；纯 SPA，无 SSR 需求（企业内部登录后使用，无 SEO 与首屏营销诉求） |
| 2 | UI 组件方案 | Tailwind CSS 4.3.3 + `@tailwindcss/vite` 4.3.3；shadcn/ui 以**源码内置**方式使用；运行时依赖 radix-ui 1.6.7 + cva 0.7.1 + clsx 2.1.1 + tailwind-merge 3.6.0 + lucide-react 1.37.0 | 三个关键页面（审批卡片 / TestRun 详情 / 执行发起页）分区顺序被 05 §4.3 冻结，需要可改源码的组件而非黑盒组件库 |
| 3 | 状态管理 | TanStack Query 5.102.8（服务端状态）+ Zustand 5.0.15（本地 UI 与 SSE 订阅）+ React Router 7.18.3（URL 状态与路由） | 对应 boundary spec §3.2 的三类前端本地数据，职责不重叠 |
| 4 | 后端框架 | FastAPI 0.141.1 + **Starlette 1.6.0（显式直接依赖）** + Uvicorn 0.52.4 + Pydantic 2.13.5 + pydantic-settings 2.15.0 | Stage 0 已定 Python；FastAPI 原生产出 OpenAPI 3.1 与 Pydantic 校验，直接承接 boundary spec 的语义契约 |
| 5 | ORM | SQLAlchemy 2.0.52（async）+ asyncpg 0.31.0 + Alembic 1.19.1 | 需要行锁、CAS、Outbox 与显式事务边界，ORM 必须能下沉到 SQL；不引入 SQLModel 叠第二层抽象 |
| 6 | API 风格 | REST + OpenAPI 3.1（FastAPI 原生）+ SSE 单向流（sse-starlette 3.4.8）；认证 Authlib 1.7.2（OIDC Auth Code + PKCE） | boundary spec §5.1 的八类必调 API 只需要「读写 REST + SSE」，无双向通道需求 |
| 7 | 测试框架 | 后端 pytest 9.1.1 + pytest-asyncio 1.4.0 + httpx 0.28.1；前端 Vitest 4.1.11 + @testing-library/react 16.3.3 + jsdom 30.0.1；E2E Playwright 1.62.1 | 前两组 Stage 0 §5.1/§5.2 已定；Playwright 本就是 M2 Web 自动化执行引擎，E2E 复用同一运行时 |
| 8 | 构建部署 | uv 0.12.7 管依赖；Docker 多阶段构建；**前期 docker compose 单机 → 后期同镜像上 Kubernetes**；运行时 Python 3.14 / Node 24 LTS / PostgreSQL 18 | 镜像即交付物，compose → K8s 只换编排层不换构建产物，避免二次改造 |

---

## 3. 逐项选型理由

### 3.1 前端框架：React 19 + TypeScript 7 + Vite 8

**继承来源**：`frontend_design_spec` §1.3 已定「React + TypeScript + Vite（纯 SPA）」，`project_rules.md` §1.2 已要求 `strict: true` 且禁止 `any`。本文只补锁定版本。

**为什么是纯 SPA 而不是 Next.js 之类的 SSR 框架**：25 个页面全部在登录态之后，没有 SEO 需求；boundary spec §2.1 要求「无租户上下文一律拒绝」，首屏也必须先建立会话。引入 SSR 会多一个 Node 运行时进程需要运维，与 §7 的单人运维目标相悖，且不解决任何已登记问题。

**为什么 Vite 而不是其他构建工具**：`npm run build` 已被 `project_rules.md` §5.2 列为合入前必过命令；Vite 的 dev server 与生产构建是同一份配置，减少「本地能跑、构建挂掉」的排障面。

### 3.2 UI 组件方案：Tailwind + shadcn/ui 源码内置

**关键判断是「可改源码」而非「组件多」**。05 §4.3 冻结了三个关键页面的分区顺序：审批卡片自上而下六区 + 操作区顺序不得调换、TestRun 详情页头 10 态进度条、执行发起页三层顺序不可调换。这类结构约束在成品组件库（如 Ant Design、MUI）里意味着持续与库的默认布局对抗；shadcn/ui 的组件是复制进仓库的源码，改结构就是改自己的文件。

**因此 shadcn/ui 不是 npm 依赖**，不出现在 `package.json` 里。真正进依赖清单的是它底层用到的五个包：radix-ui（无障碍行为原语）、cva（变体 API）、clsx + tailwind-merge（类名合并）、lucide-react（图标）。

**Tailwind 4 的取舍**：v4 用 `@tailwindcss/vite` 插件替代了 PostCSS 配置链，少一层配置文件。样式约定已由 `project_rules.md` §1.2 定为「优先使用 Tailwind 原子类，自定义 CSS 类用 kebab-case」。

### 3.3 状态管理：三者职责正交

boundary spec §3.2 把前端本地数据分成三类，正好对应三个库，没有重叠：

| boundary spec §3.2 条目 | 承接方案 | 不用另一个的原因 |
| --- | --- | --- |
| 5. 服务端状态缓存（「缓存可有时效，冲突一律以后端为准」） | TanStack Query | Zustand 是 store，把领域数据放进去会在心智上变成本地事实源，与 §3.3 红线 4「禁止将领域数据持久化为本地事实源」冲突 |
| 1./3./4. UI 状态、未提交表单、查看器状态；以及 §3.2-5 的 SSE 订阅状态 | Zustand | 这些数据没有服务端副本，用 Query 缓存模型表达是错配 |
| 2. 列表 URL 状态（筛选/排序/分页一律进 URL） | React Router | URL 是唯一事实源，任何库内状态都是它的镜像 |

**TanStack Query 承接的四项硬要求**（都是上游明文，不是「顺手好用」）：

1. boundary spec §7.2 网络错误行原文即写「自动重试（TanStack Query）」；
2. `architecture.md` §9.3 要求「重连、版本跳跃或网络恢复后 GET 对账」——对应 `refetchOnReconnect` / `refetchOnWindowFocus`；
3. boundary spec §9-G3 的 SSE 降级轮询——对应可动态调整的 `refetchInterval`；
4. `frontend_design_spec` §6.14 的缓存失效策略——对应 `invalidateQueries`。

另有一项工程收益：P01 工作台四个卡片与全局审批徽标读同一批待审批数据，Query 的 in-flight 去重避免同一端点被并发打多次。

**React Router 的定位**：只承担路由与 URL 状态，**不启用其 loader/action 数据层**。理由是避免与 TanStack Query 形成两套并行的数据获取与失效机制——同一份 TestRun 数据由两个库各自缓存会直接制造「前端自行推演状态」的风险，而 boundary spec §1 原则 1 与 §3.3 红线 1 明确禁止这件事。

> **本项为新增依赖**：React Router 7.18.3 在 `frontend_design_spec` §1.3 原为「Stage 11 按红线 R4 依赖审批流程确定」，已于本次经用户批准并前移至 Stage 6 冻结，§1.3 同步修订。

### 3.4 后端框架：FastAPI + 显式锁定的 Starlette

**继承来源**：`project_rules.md` §1.1 已把后端定为 Python（ruff / mypy / 完整类型注解），§5.1 已把测试定为 pytest + httpx。语言层无重选空间。

**为什么 FastAPI**：boundary spec §7 把错误分成网络 / 权限 / 业务三类并要求业务错误「结构化返回」，§2 全表的输入输出都是语义契约——Pydantic 模型直接就是这份契约的可执行表达，且 FastAPI 原生产出 OpenAPI 3.1 供 07_backend_design 承接。异步是硬需求：连接器要并发调用 Jira / GitHub / CI，SSE 要长连接，同步框架（Django / Flask）在这两处都要额外引入 worker 模型。

**Starlette 必须显式锁定为直接依赖**——这是本次审计发现的唯一实质风险，处置记录见 §4.4。

**Pydantic Settings 承接 `.env` 唯一注入口**：`AGENTS.md` §2 要求「后端全部配置统一经 `.env` 注入，代码中禁止硬编码任何配置值」，pydantic-settings 提供带类型校验的集中读取点，缺失必填项时启动即失败，而不是运行到一半才发现。

### 3.5 ORM：SQLAlchemy 2.0 async + asyncpg + Alembic

**为什么 ORM 必须能下沉到 SQL**。`architecture.md` §11.3 要求的机制里有三项不是普通 ORM 用法：

- ApprovalRequest 消费必须使用**数据库行锁**（`SELECT ... FOR UPDATE`）；
- TestRun / TestCase.current_version / ExecutionEnvironment / OrgQuota 使用 **expected_version CAS**；
- 聚合事实与 **Outbox 同事务提交**。

SQLAlchemy 2.0 的 Core + ORM 双层结构允许在需要时直接写 SQL 表达式，同时保留 ORM 的会话与工作单元；这三项都能表达。同时 `architecture.md` §4.1 要求「模块之间不共享仓储或 ORM 实体」，SQLAlchemy 的 registry 允许按模块拆分声明基类来做这道边界。

**为什么 asyncpg 而不是 psycopg3**：asyncpg 是 Apache-2.0，psycopg3 核心是 **LGPL-3.0-only**。`architecture.md` §18 风险表明确登记了「GPL 源码污染」风险项（源自 TestHub 的 GPL-3.0 教训）。LGPL 动态链接在法律上通常可用，但对一个内部项目而言，选 Apache-2.0 直接消除了这个需要律师判断的问题。代价见 §4.5 观察项。

**不引入 SQLModel**：它在 SQLAlchemy 之上再叠一层 Pydantic 融合模型。本项目的 API 模型与持久化模型本就不应等同——boundary spec §2 的输出是「语义契约」而非表结构，`architecture.md` §6 还要求聚合内部字段不外泄。强行统一两者会削弱这道边界。

**Alembic** 是 SQLAlchemy 官方迁移工具，同作者同版本节奏，不引入第三方迁移方案。

### 3.6 API 风格：REST + OpenAPI 3.1 + SSE

boundary spec §5.1 穷举了八类必须调用 API 的操作：领域对象读、写与状态迁移、L2+ 动作、AI 能力、导入导出、**SSE 订阅**、通知数据、制品访问。除 SSE 外全部是请求–响应语义，REST 直接匹配；`project_rules.md` §1.3 已定 API 路径规范（全小写、连字符、名词复数）。

**SSE 而不是 WebSocket**：`architecture.md` §9.3 明确「SSE 只负责展示进度和变化提示，不是命令通道」——数据流是严格单向的服务端→客户端。WebSocket 提供的双向能力在这里不但用不上，还会引入一个与「命令必经 REST 并重校验权限」原则冲突的旁路。sse-starlette 处理断连清理与心跳，避免自行实现长连接生命周期。

**不引入 GraphQL**：P01 工作台的聚合视图是 GraphQL 的典型场景，但 boundary spec §3.1-6 已把它定义为**后端聚合接口**（后端算好再下发），前端禁止本地计算聚合指标（§3.3 红线 3）。既然聚合在后端完成，GraphQL 的按需取数价值就不存在，反而增加权限与租户过滤的实现面。

**不引入 gRPC**：M0–M3 没有跨服务内部调用——`architecture.md` §4.1 是模块化单体，模块间用进程内调用与事件。Worker 回写走「已登记控制面命令」，即 HTTP。

**Authlib 承接 OIDC**：`architecture.md` §13.1 定 OIDC Authorization Code + PKCE 为主认证候选。Authlib 提供完整的 OIDC 客户端流程（含 PKCE、state、nonce、JWKS 轮换与 ID Token 校验）。**不引入 python-jose**：Authlib 已含 JWT 校验能力，再加一个 JWT 库会出现两套签名算法配置，是安全配置分叉的常见来源。

### 3.7 测试框架

**后端**（`project_rules.md` §5.1 已定，本文补版本）：pytest + pytest-asyncio + httpx。§5.1 要求「每个 API 端点至少 1 条 happy-path 集成测试（httpx AsyncClient）」，httpx 同时是连接器的出站 HTTP 客户端，一个库两用。

**前端**（`project_rules.md` §5.2 已定）：Vitest + React Testing Library。Vitest 复用 Vite 的配置与转换链，不需要第二套构建配置（这是相对 Jest 的主要优势）。jsdom 提供 DOM 环境。

**E2E：Playwright 1.62.1**。这一项看似「新增」，实际不是：决策总纲 §4.2 已定 Web 自动化引擎为 Playwright，`frontend_design_spec` §6.6 要求证据查看器支持 Trace 回放——Trace 是 Playwright 的产物格式。平台自身的 E2E 与被测产品的执行引擎共用同一运行时，等于把运维面合并成一个。

**验证入口不新增**：合入前命令沿用 `project_rules.md` §5，本文不另立命令。

### 3.8 构建与部署：Docker 多阶段 → compose → Kubernetes

**依赖管理 uv 0.12.7**：`AGENTS.md` §3 已强制（`uv sync` / `uv add`，`uv.lock` 入库，禁止 pip / requirements.txt / poetry）。前端对应 npm + `package-lock.json`（`project_rules.md` §4 已按此表述）。

**构建产物是容器镜像**。后端多阶段构建（uv 装依赖 → 复制应用层）；前端构建出静态产物后由后端或反向代理托管，不单独跑 Node 运行时——少一个需要运维的进程。

**部署演进路径**：前期 docker compose 单机；后期同一批镜像上 Kubernetes。这条路径的关键约束是**镜像不变、只换编排层**，所以现在就必须守住三条：配置全部经环境变量注入（`AGENTS.md` §2 已要求）、进程无本地状态（M0/M1 制品卷是唯一例外，见 §5 迁移前置）、日志写 stdout 不写文件。守住这三条，从 compose 迁到 K8s 不需要改应用代码。

---

## 4. 核心依赖审计表

> **数据来源与采集时间**：2026-08-29 实测。版本与 License 取自 PyPI JSON API 与 npm registry；维护活跃度以「最近一次发布日期 + 近 12 个月发布次数」为证据；CVE 结论取自 PyPI 逐版本 `vulnerabilities` 字段（OSV 数据源）与 npm registry bulk advisory 接口，**按锁定的具体版本查询，不是按包名查询**。

### 4.1 后端运行时依赖

| 依赖 | 锁定版本 | License | 最近发布 | 近 12 月发布 | CVE 结论 | 用途出处 |
| --- | --- | --- | --- | --- | --- | --- |
| fastapi | 0.141.1 | MIT | 2026-07-29 | 92 | CLEAN | §3.4 |
| starlette | 1.6.0 | BSD-3-Clause | 2026-08-08 | 22 | CLEAN（**见 §4.4 处置**） | §3.4 |
| uvicorn | 0.52.4 | BSD-3-Clause | 2026-08-19 | 24 | CLEAN | ASGI 服务器 |
| pydantic | 2.13.5 | MIT | 2026-08-28 | 25 | CLEAN | 语义契约与校验 |
| pydantic-settings | 2.15.0 | MIT | 2026-08-07 | 8 | CLEAN | `.env` 唯一注入口（`AGENTS.md` §2） |
| sqlalchemy | 2.0.52 | MIT | 2026-08-11 | 12 | CLEAN | §3.5 |
| asyncpg | 0.31.0 | Apache-2.0 | 2025-11-24 | 1 | CLEAN | §3.5（**见 §4.5 观察项**） |
| alembic | 1.19.1 | MIT | 2026-08-08 | 11 | CLEAN | 迁移 |
| sse-starlette | 3.4.8 | BSD-3-Clause | 2026-08-05 | 20 | CLEAN | §3.6 SSE |
| authlib | 1.7.2 | BSD-3-Clause | 2026-05-06 | 12 | CLEAN | §3.6 OIDC |
| argon2-cffi | 25.1.0 | MIT | 2025-06-03 | 0 | CLEAN | ApiToken 哈希（决策总纲 §6 裁定「bcrypt/argon2」）（**见 §4.5**） |
| python-multipart | 0.0.32 | Apache-2.0 | 2026-06-04 | 12 | CLEAN | 文件上传（P07 导入、Excel 导入，boundary spec §5.1-5） |
| httpx | 0.28.1 | BSD-3-Clause | 2026-08-21 | 3 | CLEAN | 连接器出站客户端 + 测试客户端 |

### 4.2 后端开发依赖

| 依赖 | 锁定版本 | License | 最近发布 | 近 12 月发布 | CVE 结论 | 用途出处 |
| --- | --- | --- | --- | --- | --- | --- |
| pytest | 9.1.1 | MIT | 2026-06-19 | 7 | CLEAN | `project_rules.md` §5.1 |
| pytest-asyncio | 1.4.0 | Apache-2.0 | 2026-05-26 | 7 | CLEAN | 同上 |
| ruff | 0.16.5 | MIT | 2026-08-27 | 49 | CLEAN | `project_rules.md` §1.1 |
| mypy | 2.3.1 | MIT | 2026-08-15 | 12 | CLEAN | 同上 |

### 4.3 前端依赖

| 依赖 | 锁定版本 | License | 最近发布 | 近 12 月发布 | CVE 结论 | 用途出处 |
| --- | --- | --- | --- | --- | --- | --- |
| react / react-dom | 19.2.8 | MIT | 2026-08-28 | 457 | CLEAN | §3.1 |
| typescript | 7.0.2 | Apache-2.0 | 2026-08-29 | 264 | CLEAN | `project_rules.md` §1.2 |
| vite | 8.2.2 | MIT | 2026-08-20 | 81 | CLEAN | §3.1 |
| @vitejs/plugin-react | 6.1.1 | MIT | — | — | CLEAN | 同上 |
| tailwindcss / @tailwindcss/vite | 4.3.3 | MIT | 2026-08-14 | 410 | CLEAN | §3.2 |
| radix-ui | 1.6.7 | MIT | 2026-07-31 | 83 | CLEAN | §3.2 |
| class-variance-authority | 0.7.1 | Apache-2.0 | 2024-11-26 | 0 | CLEAN | §3.2（**见 §4.5 观察项**） |
| clsx | 2.1.1 | MIT | 2025-06-27 | 0 | CLEAN | §3.2（**见 §4.5**） |
| tailwind-merge | 3.6.0 | MIT | 2026-08-22 | 96 | CLEAN | §3.2 |
| lucide-react | 1.37.0 | ISC | 2026-08-29 | 77 | CLEAN | §3.2 图标 |
| react-router-dom | 7.18.3 | MIT | 2026-08-28 | 208 | CLEAN | §3.3（本次新增，经 R4 批准） |
| @tanstack/react-query | 5.102.8 | MIT | 2026-08-27 | 82 | CLEAN | §3.3 |
| zustand | 5.0.15 | MIT | 2026-08-13 | 7 | CLEAN | §3.3 |
| vitest | 4.1.11 | MIT | 2026-08-28 | 60 | CLEAN | `project_rules.md` §5.2 |
| @testing-library/react | 16.3.3 | MIT | 2026-08-27 | 3 | CLEAN | 同上 |
| @testing-library/jest-dom | 7.0.1 | MIT | — | — | CLEAN | 断言扩展 |
| jsdom | 30.0.1 | MIT | — | — | CLEAN | DOM 环境 |
| @playwright/test | 1.62.1 | Apache-2.0 | 2026-08-29 | 565 | CLEAN | §3.7 |
| eslint | 10.9.1 | MIT | 2026-08-24 | 33 | CLEAN | `project_rules.md` §1.2 |
| typescript-eslint | 8.68.0 | MIT | — | — | CLEAN | 同上 |
| eslint-plugin-react-hooks | 7.1.1 | MIT | — | — | CLEAN | 同上 |
| eslint-plugin-react-refresh | 0.5.5 | MIT | — | — | CLEAN | 同上 |
| globals | 17.11.0 | MIT | — | — | CLEAN | ESLint flat config |
| prettier | 3.9.6 | MIT | — | — | CLEAN | 格式化 |
| @types/react | 19.2.18 | MIT | — | — | CLEAN | 类型 |
| @types/react-dom | 19.2.5 | MIT | — | — | CLEAN | 类型 |

### 4.4 漏洞扫描结论与唯一处置记录

**扫描结论**：后端 17 个锁定版本 + 前端 29 个锁定版本，**高危/严重 CVE 未处置数 = 0**。

**唯一发现与处置（Starlette）**：

| 环节 | 内容 |
| --- | --- |
| 发现 | 初次审计按 Starlette 0.51.0 查询，命中 6 条通告：CVE-2026-48710 / GHSA-86qp-5c8j-p5mr（修复 1.0.1）、CVE-2026-48817 / GHSA-x746-7m8f-x49c（修复 1.1.0）、CVE-2026-48818 / GHSA-wqp7-x3pw-xc5r（修复 1.1.0）、CVE-2026-54282 / GHSA-jp82-jpqv-5vv3（修复 1.3.0）、CVE-2026-54283 / GHSA-82w8-qh3p-5jfq（修复 1.3.1） |
| 根因 | FastAPI 0.141.1 只声明 `starlette>=0.46.0`，**无上界**。若把 Starlette 当作纯传递依赖交给解析器，锁文件可能落在 1.3.1 以下的有洞版本 |
| 处置 | 把 Starlette 提升为**直接依赖并锁定 1.6.0**，不依赖 FastAPI 的传递解析 |
| 复验 | 按 1.6.0 重新查询 PyPI 逐版本通告：**CLEAN**。且 1.6.0 满足 `starlette>=0.46.0`，与 FastAPI 0.141.1 无版本冲突 |
| 长期约束 | Starlette 与 FastAPI 必须**同批次升级并同批次复验**；升级 FastAPI 时不得放开 Starlette 的显式锁（见 §9 规则 4） |

### 4.5 观察项（非漏洞，但需登记的维护活跃度风险）

以下四项 CVE 结论为 CLEAN，但发布节奏偏慢，登记为观察项而非默认合格：

| 依赖 | 现象 | 风险评估 | 退出方案 |
| --- | --- | --- | --- |
| class-variance-authority 0.7.1 | 最近发布 2024-11-26，近 12 月 0 次 | **最需关注**。已近两年无发布 | 它只提供变体类名拼装，且只被**已复制进仓库的** shadcn 组件源码使用，可用 tailwind-merge + 普通对象映射就地替换，无迁移成本 |
| clsx 2.1.1 | 最近发布 2025-06-27，近 12 月 0 次 | 低。功能完备的微型工具（条件类名拼接），无网络与文件系统接触面 | 同上，可就地替换 |
| argon2-cffi 25.1.0 | 最近发布 2025-06-03，近 12 月 0 次 | 低。密码哈希算法本身稳定，无需频繁迭代 | 若出现停维信号，切 bcrypt（决策总纲 §6 裁定表原文即「bcrypt/argon2」二选一） |
| asyncpg 0.31.0 | 最近发布 2025-11-24，近 12 月仅 1 次 | 中。它在数据路径上，停维影响面大于前三者 | 切 psycopg3（需接受 LGPL-3.0-only，届时须在 `change_log` 登记 License 变更并复核 §18 GPL 风险项）。SQLAlchemy 的 dialect 抽象使切换局限在连接串与驱动配置 |

**复扫要求**：以上四项在每次 Stage 12 发布前必须重新查询发布日期；连续 18 个月无发布且出现未修复通告时，立即启动退出方案。

---

## 5. 分期启用矩阵

> 依据用户 2026-08-29 裁定：M0/M1 只运行 PostgreSQL 单数据面。本节**不推翻** ADR 0002（Temporal 仍是目标持久工作流运行时），只定义启用节奏。`architecture.md` §15.1 已同步登记。

| 组件 | 目标架构地位 | M0 / M1 | M2+ | M0/M1 的替代实现 |
| --- | --- | --- | --- | --- |
| PostgreSQL 18 | 业务事实唯一权威 | **启用** | 启用 | — |
| Temporal | 持久工作流运行时（ADR 0002 Accepted） | 不启用 | 启用 | Outbox 表落 PostgreSQL；轮询由后端定时任务驱动；长等待态靠 TestRun / ApprovalRequest 自身状态机 + 滞留时长可见性表达 |
| Redis | 可重建缓存、限流辅助、短租约 | 不启用 | 按需启用 | 入口限流归网关（决策总纲 §6 已裁定）；缓存暂不引入 |
| S3 / MinIO | 制品正文存储 | 不启用 | 启用 | 本地卷 + 服务端生成的私有对象 key；访问仍走后端授权，不发预签名 URL |
| Vault | 秘密管理 | 不启用 | 启用 | `.env`（`AGENTS.md` §2）+ Docker secret；`.env` 不入库，`.env.example` 只含键名 |
| pgvector | 检索能力起步 | 不启用 | M4 评估 | M0–M3 无 RAG 需求（决策总纲 §1 分期注记已把 RAG 定为 M4） |

**M0/M1 实际运行单元**：PostgreSQL 1 个有状态组件 + 后端 API 进程 + 前端静态产物。这是 §7 单人运维结论成立的前提。

**启用前置条件（不得跳过）**：

1. **Temporal**：启用前必须先满足 `architecture.md` §15.1 的八项生产 Gate；启用时 Outbox relay 的调度 Owner 从后端定时任务切到 Temporal，切换期间**同一业务步骤不得同时存在两个调度 Owner**（`architecture.md` §11.2 原文约束）。
2. **MinIO**：启用前必须先完成本地卷制品的迁移与摘要复核；此前应用不得假设对象存储的任何 S3 专有语义（如预签名 URL），否则迁移会退化为改代码。
3. **Vault**：启用前 `.env` 中的凭证必须已按 `architecture.md` §12「业务库只保存引用」的形态组织，即数据库里存的已经是引用而不是明文。
4. 上述任一组件启用都属于「变更配置与依赖」，须按 `AGENTS.md` §5 先出 Plan，并在 `change_log` 登记。

**这里承担的债务要说清楚**：M0/M1 用定时任务驱动轮询，无法提供 Temporal 的持久 Timer 与 workflow history。因此 M0/M1 的恢复保证弱于目标架构——进程重启后靠数据库状态重建，而不是靠 workflow 重放。`architecture.md` §11.3 要求的幂等键、CAS 与行锁在 M0/M1 **必须照常实现**，它们是这个阶段唯一的「重启不重复副作用」保障，不能因为「反正 M2 要上 Temporal」而推迟。

---

## 6. 不采纳清单

> 对应约束「不允许为『看起来完整』添加无实际需求的组件」。每项给出不采纳的具体理由，而不是「暂时不需要」。

| 组件 | 不采纳理由 |
| --- | --- |
| Redis（M0/M1） | 入口限流已由网关承担（决策总纲 §6 裁定）；`architecture.md` §12 明确 Redis 只能存「可重建」数据，因此它在 M0/M1 不解决任何正确性问题，只增加一个有状态组件 |
| Celery / Arq / RQ | 与 ADR 0002 已接受的 Temporal 职责重复。M0/M1 的轻量定时任务用后端进程内调度即可，引入第二套任务队列会在 M2 上 Temporal 时产生两个调度 Owner——正是 `architecture.md` §11.2 明令禁止的情况 |
| GraphQL | 聚合已由后端完成（boundary spec §3.1-6 聚合接口 + §3.3 红线 3 禁止前端本地计算），按需取数的价值不存在；反而扩大租户过滤与权限校验的实现面 |
| gRPC | M0–M3 无跨服务内部调用（模块化单体，模块间进程内调用）；Worker 回写走已登记的 HTTP 控制面命令 |
| WebSocket | 数据流严格单向（`architecture.md` §9.3「SSE 不是命令通道」）；双向能力用不上，还会开出一条绕过 REST 权限校验的旁路 |
| Redux / MobX / Jotai | TanStack Query + Zustand 已覆盖 boundary spec §3.2 的全部三类数据，无剩余场景 |
| SQLModel | 在 SQLAlchemy 上叠第二层抽象，并把 API 模型与持久化模型强行统一，削弱 boundary spec §2「输出是语义契约而非表结构」的边界 |
| python-jose / PyJWT | Authlib 已含 JWT 与 JWKS 校验；再加一个 JWT 库会出现两套签名算法配置，是安全配置分叉的常见来源 |
| Zod | 后端 OpenAPI 3.1 可生成前端类型，运行时校验的收益有限；P08 动态表单按 `params_schema_ref` 渲染，那是 **JSON Schema**，真需要运行时校验时应评估 ajv 而非 zod。列为 §10-G2 待裁定，不预先锁 |
| Next.js / Remix（SSR） | 无 SEO 需求，全部页面在登录态后；多一个 Node 运行时进程需要运维 |
| Ant Design / MUI | 05 §4.3 冻结了三个关键页面的分区顺序，成品组件库意味着持续与默认布局对抗（详见 §3.2） |
| structlog / OpenTelemetry SDK | `architecture.md` §14.3 的三类记录分离是**目标**要求。M0/M1 用标准库 logging + JSON formatter 输出到 stdout 即可满足「结构化日志」，Trace 因果链在只有单进程时价值有限。M2 拆出 Worker 后再评估，届时走 R4 |
| pip / requirements.txt / poetry | `AGENTS.md` §3 明令禁止 |
| pnpm / yarn | `project_rules.md` §4 已按 `package-lock.json` 表述，即 npm |
| MCP SDK | ADR 0008 与 `architecture.md` §15.3 已定 M0–M3 不引入 MCP client/server/SDK/传输 |
| LangGraph | ADR 0008 限定其仅用于 Agent/Copilot（M3+），且「是否最终采用」仍未决定。M0–M2 无需求，不预锁版本 |

---

## 7. 独立运维可行性自评

> 对应自检项「每个选型是我能独立运维的」。判定标准：单人能否独立完成安装、升级、排障、回滚。

| 类别 | M0/M1 运维面 | 结论 |
| --- | --- | --- |
| 有状态组件 | PostgreSQL 1 个 | **通过**。单实例 + 定期备份，恢复路径是标准 `pg_dump` / PITR |
| 无状态进程 | 后端 API 1 个；前端为静态产物 | **通过**。崩溃即重启，无状态可丢 |
| 前端依赖 | 全部为构建期/运行期库，无服务端组件 | **通过**。出问题即回滚 `package-lock.json`，影响面限于浏览器 |
| 后端依赖 | 全部为进程内库，无独立守护进程 | **通过**。出问题即回滚 `uv.lock` |
| 部署 | docker compose 单机 | **通过**。`docker compose up/down` + 镜像 tag 回滚 |
| 升级 | uv / npm 锁文件驱动，锁文件变更独立成 commit（`AGENTS.md` §3） | **通过**。可逐依赖回退 |

**未通过独立运维评估、因此推迟的组件**：Temporal（需要自身的数据库、history 保留策略、Worker Versioning 与在途 workflow 兼容性管理）、Vault（需要 unseal 流程、租约与轮换策略、自身的灾备）。这两项在 M2+ 启用前必须先补运维方案——**这是硬前置条件，不是建议**。这也是 §5 分期启用的直接动因。

**诚实的结论**：本次冻结在 M0/M1 范围内完全满足「能独立运维」；在目标架构（M2+）范围内**不满足**，需要额外的运维能力建设或托管服务。这一点没有被本次冻结解决，只是被推迟并显式登记。

---

## 8. 一致性检查

| 检查项 | 结果 |
| --- | --- |
| 选型 ⊆ 上游已冻结结论，或已走变更登记 | PASS：Stage 0 项按继承；React Router 与分期启用两项已在 `change_log` 登记并经用户批准 |
| 每个核心依赖四要素齐全（版本 / License / 活跃度 / CVE） | PASS：§4.1–§4.3 逐行给出，数据为 2026-08-29 实测 |
| 高危/严重 CVE 未处置数 = 0 | PASS：唯一发现（Starlette）已处置并复验，记录见 §4.4 |
| 无新增领域对象 / 页面 / 状态 / 字段 | PASS：本文不触碰领域模型 |
| 无代码 / DDL / 迁移 / 部署清单 | PASS：仅决策与版本表 |
| 未预建 `backend/` / `frontend/` 子目录 | PASS：符合 `project_rules.md` §2.5 |
| License 相容性 | PASS：全部为 MIT / BSD-3-Clause / Apache-2.0 / ISC；无 GPL 与 LGPL 依赖（asyncpg 选型即为规避 psycopg3 的 LGPL） |
| 与 `architecture.md` 非目标不冲突 | PASS：§2.3 声明架构正文不定义依赖与部署，本文正是其缺口的承接分册 |

---

## 9. 依赖治理规则

1. **新增运行时依赖**固定顺序：获用户批准 → 审计（活跃度 / License / 无未修复通告）→ `uv add` / `npm install` 落锁（红线 R4）。
2. **锁文件变更独立成 commit**（`AGENTS.md` §3），便于审计回溯。
3. **每次发布前复扫**：按锁定版本逐个查询 PyPI `vulnerabilities` 与 npm advisory bulk 接口；`uv.lock` / `package-lock.json` 变更后必须复扫，不得沿用旧结论。
4. **Starlette 特例**：与 FastAPI 同批次升级并同批次复验；升级 FastAPI 时**不得移除** Starlette 的显式直接依赖声明（理由见 §4.4）。
5. **§4.5 观察项**每次发布前复查发布日期；连续 18 个月无发布且出现未修复通告即启动退出方案。
6. 本文的版本冻结在下列情况才允许变更：安全通告、上游不兼容、或已登记的架构变更；日常「跟新版本」不构成变更理由。

---

## 10. 缺口上报

| # | 缺口 | 建议归属 |
| --- | --- | --- |
| G1 | M0/M1 用后端定时任务驱动轮询与 Outbox relay，其调度形态（进程内调度器 / 独立进程 / 数据库 advisory lock 选主）未定义 | 07_backend_design 或 Stage 12 实施设计 |
| G2 | P08 动态表单按 `params_schema_ref` 渲染，前端是否需要运行时 JSON Schema 校验器（ajv）取决于 07_backend_design 最终的 schema 契约复杂度 | 07_backend_design 定契约后裁定，届时走 R4 |
| G3 | 前端与后端类型同步方式（由 OpenAPI 生成 TS 类型 / 手写）未定；若引入生成器属新增开发依赖 | Stage 11 前端初始化，走 R4 |
| G4 | Kubernetes 迁移的具体时点、清单形态与 Ingress/网关选型未定；本文只冻结「同镜像换编排层」的约束 | Stage 12 部署设计 |
| G5 | PostgreSQL 高可用与备份拓扑仍为 TBD（`architecture.md` §14.2 已登记），本文未替其定值 | 沿用 `architecture.md` 开放问题 Q11 |

---

## 11. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1.0 | 2026-08-29 | 首版：冻结八类技术栈至锁定版本；核心依赖审计 46 项（后端 17 / 前端 29）含 License、维护活跃度与逐版本 CVE 结论；发现并处置 Starlette 传递依赖 CVE 风险；登记 4 项维护活跃度观察项；定义 M0/M1 单 PostgreSQL 数据面的分期启用矩阵与启用前置条件；不采纳清单 16 项；独立运维自评（M0/M1 通过、M2+ 不通过并显式推迟）；缺口 5 项上报 |
