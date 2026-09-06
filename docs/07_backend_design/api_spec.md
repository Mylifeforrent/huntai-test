# HuntAI Test API 契约（Stage 7）

> - **Status: Draft**
> - **日期**：2026-08-29（2026-09-06 修订） · **版本**：v1.1
> - **阶段**：Stage 7 · 数据模型与 API 规范 · 本文件只覆盖 **OpenAPI 3.1 风格接口契约**
> - **文档定位**：把 [前后端边界](../06_architecture_design/frontend_backend_boundary_spec-v1.0.md) 的语义操作与已定稿架构的命令/查询/SSE/Webhook 原则落到路径、方法、请求/响应语义、错误码与鉴权。实现映射（FastAPI / Pydantic / ORM）留给 Stage 11/12。
> - **实现边界**：本文不含可执行代码、DDL、Alembic、ORM 实体、部署配置、Redis/Temporal/MinIO/Vault 产品管理面。
> - **变更纪律**：修订本文走 Stage 7 评审；禁止静默修改 Stage 6 已定稿 / 已冻结文档。禁止把 Proposed 写成已批准实现。

---

## 0. 阅读导航

| 章 | 内容 |
| --- | --- |
| [1](#1-来源优先级范围与非目标) | 来源优先级、范围、非目标 |
| [2](#2-契约总则) | `/api/v1`、命令/查询、受理与完成、幂等、CAS、404 |
| [3](#3-鉴权与授权模型) | OIDC 会话、角色、ApiToken、HMAC、REQUIRE_REAUTH |
| [4](#4-统一错误外壳与错误码) | 三大类 + 子类；全局唯一错误码 |
| [5](#5-公共-openapi-31-schema) | Envelope、CommandReceipt、Page、Error |
| [6](#6-api-清单总表) | 稳定 ID `API-001`…；Method + Path |
| [7](#7-端点契约) | 每个端点：鉴权、schema、成功判定、错误（查询 / 写 / L2+ / AI·SSE·制品） |
| [8](#8-sse-契约g3) | 只读通道、事件 ID、重连、降级轮询 |
| [9](#9-制品与导出访问g5) | 引用≠授权；Restricted；M0/M1 代理 |
| [10](#10-ai-草稿暂存g1) | 不落库 TestCase；TTL/多端 TBD |
| [11](#11-限流语义) | 网关入口限流；无 Redis 限流表 |
| [12](#12-系统内部命令无浏览器端点) | consume / Worker / Outbox |
| [13](#13-覆盖矩阵) | §2 / §5.1 / §5.2 |
| [14](#14-tbd-与-proposed) | 未批项清单 |

---

## 1. 来源优先级、范围与非目标

### 1.1 来源优先级（冲突时服从更高优先级）

| 优先级 | 来源 | 本文使用规则 |
| --- | --- | --- |
| 1 | [problem_model.md](../03_problem_modeling/problem_model.md) | 23 对象、状态集合、不变量；**不得发明**状态、结果枚举或领域对象 |
| 2 | [architecture.md](../06_architecture_design/architecture.md) | 命令/查询分离、受理与完成分离、SSE 非命令通道、Webhook 先观察再命令、幂等/CAS/行锁、`execution_result=unknown` |
| 3 | [02_api_workflow_and_review.md](../06_architecture_design/02_api_workflow_and_review.md) | Stage 7 OpenAPI 语义约束（认证/404、幂等三层、错误子类、同步异步、SSE、文件访问）。本文消费其约束，**不替代**也**不推翻**三大错误类 |
| 4 | [frontend_backend_boundary_spec-v1.0.md](../06_architecture_design/frontend_backend_boundary_spec-v1.0.md) | 必调 API 八类（§5.1）、纯本地无 API（§5.2）、成功判定（§6）、三类错误（§7）、缺口 G1/G3/G5 |
| 5 | [data_model.md](data_model.md) | 逻辑表与 Public/Internal/Confidential/Restricted；**响应字段 ⊆ 可对外语义，不等于表结构** |
| 6 | [tech_stack_decision-v1.0.md](../06_architecture_design/tech_stack_decision-v1.0.md) 与 [ADR 0009](../06_architecture_design/adr/0009_technology_stack_freeze.md) | REST + OpenAPI 3.1 + SSE；OIDC Auth Code + PKCE；M0/M1 无 Redis/Temporal/MinIO/Vault 专用面 |
| 7 | [project_rules.md](../00_setup/project_rules.md) §1.3 | 路径全小写、连字符、名词复数 |

不使用仓库中不存在的 `architecture_spec.md`、`data_model_spec.md`、`api_interface_spec.md`、`business_model.md`。不把过时的「LangChain 编排层」写成 API。不启用 MCP / LangGraph checkpoint / WebSocket / gRPC / GraphQL 端点。

### 1.2 范围

- 业务 API ⊆ 边界文档 §2 操作 ∪ §5.1 八类 ∪ 架构已登记的命令 / Webhook / SSE。
- 认证会话、操作回执、通知列表/角标为**传输协调面**，不升格为第 24 个领域对象。
- 入站 Webhook 与 ApiToken 调用作为**系统入口**单列（不是页面字段）。

### 1.3 非目标

- 不写 FastAPI 路由函数、Pydantic 类、DDL、Alembic、ORM。
- 不把模块私有列、Outbox / Inbox / execution intent 暴露为对外资源树。
- 不把 Worker 内部命令或 Outbox relay 暴露为浏览器 API。
- 不把 Temporal HTTP、Vault/MinIO 管理面写成产品 API。
- 不把边界文档 §5.2 纯前端本地操作设为 API。
- 不把 Proposed（含 ADR 0007 混合预签名的 M2+ 形态、L2 持续授权独立对象、`not_evaluated`）写成当前已批准默认。

### 1.4 状态与结果枚举纪律

对外状态 / 结果枚举 **严格 ⊆** `problem_model.md`：

| 对象 | 允许值 |
| --- | --- |
| TestCase.lifecycle_status | `DRAFT / PENDING_REVIEW / ACTIVE / DEPRECATED` |
| TestCase.validity | `valid / invalid` |
| TestRun.status | `PENDING / VALIDATING / RUNNING / WAITING_EXTERNAL / WAITING_APPROVAL / STOPPING / SUCCEEDED / FAILED / CANCELLED / TIMEOUT` |
| TestRun 终态 | `SUCCEEDED / FAILED / CANCELLED / TIMEOUT` |
| ApprovalRequest.status | `CREATED / PENDING / APPROVED / EXECUTED / REJECTED / EXPIRED` |
| ApprovalRequest.execution_result | 仅 EXECUTED 有值：`ok / failed / unknown` |
| ExecutionEnvironment.status | `PENDING_APPROVAL / ACTIVE / DEGRADED / DISABLED` |
| ReleaseTask.status | `DRAFT / PENDING_CONFIRM / SUBMITTED / READY / FAILED_RETRYABLE / CANCELLED` |
| GateEvaluation.result | `pass / fail / waived`（**不含** Proposed `not_evaluated`） |
| AIInvocationLog.result | `ok / degraded / refused` |
| FailureCluster.category | `env_down / auth_expired / locator_stale / assertion_real_bug / flaky / data_issue / unknown` |

本文**不手写**状态机边数；迁移合法性以 `problem_model.md` 为准。不可评估的门禁：无 `GateEvaluation` 行 + 查询投影 `unevaluated_reason`（不是第四种 `result`）。

---

## 2. 契约总则

### 2.1 前缀与路径

- 所有产品 API 位于 **`/api/v1`**。
- 路径：全小写、连字符分隔、名词复数（例：`/api/v1/test-runs`）。
- 动作用资源子路径表达（例：`/api/v1/test-runs/{test_run_id}/cancel`），不使用动词型顶层 RPC（`/execute` 万能入口除外：L2+ Preview 使用 `POST /api/v1/action-previews`，因其对应 Policy Gate，不是第 24 对象）。
- 内容类型：`application/json; charset=utf-8`。SSE：`text/event-stream`。文件上传：`multipart/form-data` 或先登记后代理字节流。文件下载：按 `mime_type`。

### 2.2 命令 vs 查询

| | 查询（Query） | 命令（Command） |
| --- | --- | --- |
| HTTP | 默认 `GET` | `POST` / `PATCH` / `DELETE`（删除语义仅成员移除等；领域对象禁止物理删除的走停用/吊销命令） |
| 副作用 | **禁止**隐式外部写或状态迁移 | 改变状态或产生副作用 |
| 校验 | 每次认证 + tenant + RBAC | 入口重校验身份、tenant、权限、当前态、版本、幂等 |
| 返回 | 当前有权快照 + `version`（CAS 用） | 受理回执和/或持久化后的资源；完成态另判 |
| 失败 | 网络失败 ≠ 空集 | 失败与拒绝同样写 AuditEvent |

查询失败不得被前端解释为「空数据」。列表空集使用 `200` + `data.items: []` + `page`；权限/网络走错误外壳。

### 2.3 受理回执 vs 完成态

- **受理**：认证、tenant、RBAC、基本参数、幂等与当前态校验通过后，命令被接受。HTTP 常为 `200`（短事务已落库）或 `202`（异步完成）。
- **完成**：领域资源进入权威状态或异步任务 `succeeded/failed/partial`。前端按钮反馈、跳转、SSE 进度 **不是**完成。
- 对照边界 §6：例如发起执行的权威成功是 TestRun 已创建并返回 `test_run_id`（状态至少 `PENDING`）；执行成功仍须等终态。审批 `APPROVED` ≠ `EXECUTED + execution_result=ok`。

### 2.4 幂等 scope

受理幂等 scope = **`tenant`（organization_id）+ `command_type` + `idempotency_key`**。

- 服务端保存请求哈希与结果引用：同 key 同 hash → 返回已有回执；同 key 异 hash → `HT-IDEM-001`。
- 客户端可发送不透明 `Idempotency-Key`（UUID）。**禁止**用业务字段（标题、Jira key、参数 JSON）派生「业务幂等键」。
- 浏览器可重放服务端回执中的同一 key。
- ApiToken 调用方必须提供可稳定重放的 key，或使用回执中服务端签发的 key 重放。
- 入站 Webhook **不**使用该头：去重依据 = 外部稳定事件 ID + tenant + connector。
- 幂等时效：**TBD**（未批不得发明默认小时数）。
- 幂等三层（`02_api` §4.1）在 API 层只暴露**受理幂等**；执行幂等与外部写幂等由 Worker/连接器消费，不另开浏览器端点。

请求头：

```http
Idempotency-Key: <opaque-uuid>
```

适用：所有可重试命令（创建 TestRun、取消、导入、导出、A1 生成、L2+ Preview、审批决策、Token 签发等）。只读 GET 不要求该头。

### 2.5 `expected_version` CAS

下列可变聚合的写命令（除 append-only）必须携带 `expected_version`（对应数据模型 `aggregate_version`，**对外字段名 `version` / `expected_version`**）：

- Organization（治理开关等）
- TestCase（生命周期与指针；Version 行本身禁止覆盖）
- TestRun（状态迁移命令）
- ExecutionEnvironment
- ReleaseTask
- OrgQuota（账本命令由系统使用；对外以查询为主）
- QualityGatePolicy、Connector、ModelRoute、Skill 发布指针、PerfBaseline 活跃切换、TestPlan

不匹配 → `HT-VER-001`。append-only 资源（AuditEvent、EvidenceObject、GateEvaluation、AIInvocationLog、TestCaseVersion、Artifact）**无** CAS 覆盖。

### 2.6 跨租户统一「资源不存在」

| 情况 | HTTP | 错误码 | 说明 |
| --- | --- | --- | --- |
| 未认证 | `401` | `HT-AUTH-001` | **不得**伪装 404 |
| 需再认证 | `401` | `HT-AUTH-002` | `REQUIRE_REAUTH` |
| 已认证，资源不存在或跨租户/不可感知 | `404` | `HT-RES-001` | 不泄露存在性 |
| 同租户可见但无动作权限 | `403` | `HT-IAM-001` 等 | 支持 UX；前端置灰不是安全边界 |

消费 `02_api` Draft A-02：跨租户统一不存在；同租户动作权不足可表达 403。该 HTTP 映射由本文冻结为契约；上游推荐仍标记 Draft，与边界 §7「跨租户引用统一 404」一致。

---

## 3. 鉴权与授权模型

默认：**需要服务端会话**（OIDC Authorization Code + PKCE）。不是「匿名 / 登录」二元。LDAP 仅为无 OIDC 时的兼容候选（架构 §13.1），本契约不另列 LDAP 端点。

### 3.1 通道

| 通道 | 凭证 | 用于 |
| --- | --- | --- |
| **OIDC 会话** | HttpOnly、Secure、SameSite 会话 Cookie（具体 Cookie 名 **TBD**）；浏览器不持 IdP refresh token 明文 | 几乎全部浏览器 API、SSE、上传下载 |
| **ApiToken** | `Authorization: Bearer <token>`；argon2 哈希存库；明文只在签发响应出现一次 | CI/集成调用；scopes + project 白名单 + 有效期 + 吊销 |
| **HMAC** | 连接器约定头（如 `X-Hub-Signature-256`；具体头名按连接器类型 **TBD** 但必须验签无例外） | 仅入站 Webhook `API-090` |
| **无凭证** | — | 仅 OIDC start/callback 的浏览器跳转步；callback 校验 `state`/`nonce` |

SSE、上传、下载、webhook **管理查询**均须认证，不因流式或文件通道绕过。

### 3.2 ProjectMember 角色

角色 ∈ `owner / admin / tester / viewer`。Jira 同步不得覆盖本表（ADR 0005 为 Proposed；当前兼容 = 平台角色权威）。

| 角色 | 读 | 发起执行 | 审批 | L2+ Preview | 环境注册 / 连接器 / Token | 成员管理 | 门禁策略 blocking | kill switch 关停 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| viewer | 项目内只读 | 否 | 否 | 否 | 否 | 否 | 否 | 否 |
| tester | 是 | 是（受环境/配额/白名单） | 否（非候选审批人） | 可发起需审批的 Preview | 否 | 否 | 否 | 否 |
| admin | 是 | 是 | 是（四眼：≠ initiator） | 是 | 是（组织级配置另见 owner） | 是（不可移除最后 owner） | 是（显式确认） | 是（L1） |
| owner | 是 | 是 | 是 | 是 | 是 | 是 | 是 | 是 |

细化以各端点 `roles` 为准。**四眼**：批准人 ≠ 发起人，服务端强制。前端「本人批准置灰」只是呈现。

未列出的精确矩阵（如「tester 可否改 TestPlan」）在端点级声明；冲突时 fail-close（拒绝）。

### 3.3 ApiToken scopes

`scopes` ⊆ `read / write / execute / delete`。

| scope | 允许（语义） |
| --- | --- |
| `read` | 查询 TestRun/结果/门禁等只读（仍受 `project_ids`） |
| `write` | 非执行类写（配置类）；默认 **不**含发起 TestRun |
| `execute` | `POST /api/v1/test-runs`（`trigger_type=api_token`） |
| `delete` | 吊销类/移除类；**不能**物理删领域对象或擦审计 |

`project_ids[]` 白名单；空数组语义 **TBD**（禁止默认「全部项目」）。过期或 `revoked_at` 非空 → `HT-AUTH-001` 或 `HT-IAM-004`。Token **不能**替代审批、不能绕过 Policy Gate、不能下载 Restricted 正文（除非另批，当前 = 否）。

### 3.4 L3+ `REQUIRE_REAUTH`

Policy Gate 对 L3+ 且会话超过再认证窗口（窗口数值 **TBD**）返回 `REQUIRE_REAUTH`。客户端走 `API-004` 完成 step-up 后再重放命令（同一 `Idempotency-Key` 仅当请求哈希不变）。模型声称「已获批准」不构成授权。

### 3.5 入站 HMAC

Webhook 必须验签、归属（tenant / connector / job）、去重、审计。验签失败：`401`/`403` + `HT-AUTH-004`（不泄露内部密钥）；仍写审计（无 secret）。**不能**直接改 TestRun/ReleaseTask 状态机：只落观察，再经已登记命令。

---

### 3.6 Cookie 与会话安全

默认通道仍是 **OIDC Authorization Code + PKCE** 签发的**服务端会话**（非「匿名 / 登录」二元）。会话是传输协调面，**不是**第 24 个领域对象。

| 属性 | 契约 | 未批项 |
| --- | --- | --- |
| 载体 | HttpOnly、Secure 会话 Cookie；浏览器脚本不得读取 | Cookie **名** TBD |
| SameSite | 必须启用（`Lax` 或 `Strict` 的取值 **TBD**，未批不得写成默认） | 具体枚举 TBD |
| 明文禁区 | 浏览器**不持** IdP refresh token / access token 明文；API 响应体不回传会话秘密 | 会话时长、IdP claim、MFA、JIT、禁用传播 TBD |
| 吊销 | `API-003` 吊销服务端会话记录后，同一 Cookie 不得再通过认证 | — |
| 再认证 | L3+ 窗口由 Policy Gate 判定；窗口**数值 TBD**，本文不写秒数 | 见 §3.9 |
| CSRF | 变更类命令依赖 Cookie 的 SameSite + 同源；不另开 CSRF RPC。OIDC callback 仍校验 `state` / `nonce` / PKCE | — |

禁止：

- 把会话 Cookie 当长期 Bearer 写进 `localStorage` / 前端状态库。
- 用前端「已登录」缓存替代每请求校验（架构 §13.1 / 边界 §1 原则 2）。
- 无组织上下文时回退默认租户（`02_api` §3.2；无上下文 = 拒绝）。
- 为 LDAP 另列产品端点（架构 §13.1 仅为无 OIDC 时的兼容候选，本契约不展开）。

SSE、上传、下载、webhook **管理查询**均须已认证会话（或明确允许的 Token 通道）；不得因 `text/event-stream` 或文件代理绕过。

### 3.7 ApiToken 传输与头示例

CI / 集成调用使用 `Authorization: Bearer`；库内只存 argon2 `token_hash`（Restricted）；明文**仅** `API-171` 签发响应出现一次。列表与再 GET 只返回 `token_prefix`、scopes、`project_ids`、`expires_at`、`revoked_at` 投影。

**请求头示例**（假前缀，禁止真实密钥）：

```http
Authorization: Bearer ht_live_xxxREDACTED
Idempotency-Key: 00000000-0000-4000-8000-000000000001
```

| 规则 | 说明 |
| --- | --- |
| 前缀 | 文档与示例一律使用 `ht_live_xxxREDACTED`；实现签发的真实前缀策略 **TBD**，但对外契约禁止把真实 token 写入设计文档、日志、Trace、Prompt、错误 `details` |
| scope | ⊆ `read / write / execute / delete`；`execute` 仅 `API-080`（同路径 `POST /api/v1/test-runs`，`trigger_type=api_token`） |
| 白名单 | `project_ids[]` 必须命中；空数组语义 **TBD**（禁止默认「全部项目」） |
| 失效 | 过期或 `revoked_at` 非空 → `HT-AUTH-001` 或 `HT-IAM-004` |
| 不能替代 | 审批、Policy Gate、四眼、Restricted 正文下载（当前 = 否，除非另批） |
| 幂等 | Token 调用方可重试命令**必须**带稳定 `Idempotency-Key`（`API-080` 强制） |

Token **不能**调用审批决策（`API-112`）、L3 配置或 `API-120` 的人机 Preview 以绕过会话再认证。SSE 默认 **仅 Sess**；Token 调用方用资源 GET 轮询。

### 3.8 HMAC 验签原则（仅 `API-090`）

入站 Webhook **无例外先验签**，再归属（tenant / connector / job）、去重、落 `external_observations` / Inbox，再经已登记**内部命令**推进领域状态。观察行**禁止**直接 UPDATE `test_runs` / `release_tasks` / `gate_evaluations`。

| 原则 | 契约 |
| --- | --- |
| 头名 | 按连接器类型约定（如 `X-Hub-Signature-256`）；具体头名 **TBD**，但「必须验签」不是 TBD |
| 密钥 | 只存 `webhook_secret_ref`（Restricted 引用）；响应、错误、审计 `payload` **不得**含 secret 值 |
| 失败 | 验签失败 → `401`/`403` + `HT-AUTH-004`；**不**泄露算法细节、期望签名或密钥材料 |
| 审计 | 验签失败**仍写** AuditEvent（`signature_ok=false` 语义）；无 secret 正文 |
| 去重 | 外部稳定事件 ID + tenant + connector；**不**使用 `Idempotency-Key` 头 |
| 乱序 | 只对账与审计，不回退状态机（`02_api` §9.2） |
| 成功 | `202` 受理观察，或重复事件返回已有结果；**不是** TestRun/ReleaseTask 已完成 |

HMAC 通道不得签发会话 Cookie，也不得用 ApiToken 冒充入站签名。

### 3.9 `REQUIRE_REAUTH` 重放纪律

Policy Gate 对 L3+ 且会话超过再认证窗口（**窗口数值 TBD**，禁止在契约中写秒数）返回 `REQUIRE_REAUTH`，对外映射 `401` + `HT-AUTH-002`。

客户端纪律：

1. **停止**把原命令当已授权；不得本地把 CTA 当作已通过 Gate。
2. 走 `API-004` 完成 step-up；成功判定 = 再评估不再仅因窗口返回 `REQUIRE_REAUTH`（窗口仍 TBD）。
3. **重放原命令**时：同一 `Idempotency-Key` **仅当**请求哈希不变（body / 关键 query 的服务端 `request_hash` 一致）。同 key 异 hash → `HT-IDEM-001`。
4. 参数、目标资源、权限上下文变化后：旧幂等键与旧审批**均不能**授权新动作；须新 Preview（`API-120`）及（若仍为 REQUIRE_APPROVAL）新 ApprovalRequest。
5. 模型或 Copilot 声称「已获批准」**不构成**授权（架构 §13.4）。
6. `API-004` 循环失败 → `HT-IAM-001`，不得降级为匿名重试。

自动重试必须复用同一幂等语义，禁止生成「看起来新」的命令（`02_api` §4.2）。

### 3.10 viewer 置灰不是安全边界

| 层 | 允许 | 禁止把其当作 |
| --- | --- | --- |
| 前端 | 按 `API-005` 角色渲染：viewer 只读、无发起 / 审批 / L2+ 入口；按钮置灰、无权限态页面 | 安全边界、授权证明 |
| 后端 | **每个**查询与命令重校验 RBAC + tenant；viewer 写命令 / Preview / 审批 / Token 管理 / 环境注册 → `HT-IAM-001` | 依赖 CTA 隐藏 |
| 四眼 | 发起人「批准」置灰仅为呈现；服务端 `approver_id != initiator_id` 强制，违例 `HT-IAM-002` 并审计 | 前端置灰即可放行 |

同租户可见但无动作权：可 `403`（支持 UX）。跨租户或不可感知：统一 `404` + `HT-RES-001`，前端不得用 403/404 差异探测存在性（`02_api` Draft A-02；边界 §7.3）。未认证不得伪装 404（`HT-AUTH-001`）。

长流程在入口、恢复、审批消费、连接器 / Tool 调用、制品授权时读取**当前**权限，不沿用旧角色快照（架构 §13.2）。

---


## 4. 统一错误外壳与错误码

### 4.1 三大类（边界 §7，不可推翻）

| 大类 | `error.class` | 判定 |
| --- | --- | --- |
| 网络 | `network` | 未送达 / 超时 / 断连 / 网关 5xx / SSE 断连；业务语义**未知** |
| 权限 | `permission` | 401、REQUIRE_REAUTH、403、跨租户 404 遮蔽 |
| 业务 | `business` | 校验、前置态、配额、DENY、审批失效、外部失败、partial 等 |

`02_api` §5.1 子类是 Draft A-04，本文采用为 `error.subclass`，**从属于**三大类。

### 4.2 错误对象（OpenAPI 3.1）

```yaml
ErrorEnvelope:
  type: object
  required: [error]
  properties:
    error:
      type: object
      required: [code, class, subclass, message, retryable, trace_id]
      properties:
        code:
          type: string
          description: 全局唯一错误码，如 HT-VAL-001
        class:
          type: string
          enum: [network, permission, business]
        subclass:
          type: string
          description: |
            unauthenticated | require_reauth | forbidden | not_found |
            validation | precondition | version_conflict | idempotency_conflict |
            policy_deny | quota | rate_limited | approval_invalid | external |
            async_partial | internal
        message:
          type: string
          description: 用户可理解说明；禁止内部栈、SQL、密钥、Prompt 原文
        retryable:
          type: boolean
        details:
          type: object
          additionalProperties: true
          description: 字段级错误等；不得含 Restricted 明文
        trace_id:
          type: string
          description: 关联审计/追踪；失败也必须有
        resource_type:
          type: string
        resource_id:
          type: string
          format: uuid
```

HTTP 5xx 响应体仍用本外壳（`HT-INT-*` / `HT-NET-*`），不返回框架默认 HTML。

### 4.3 错误码表（全局唯一、分段）

| code | HTTP | class | subclass | 语义 | 典型可重试 |
| --- | --- | --- | --- | --- | --- |
| `HT-NET-001` | 504 / 断连无体 | network | — | 网关/上游超时，结果未决 | 条件；先 GET 对账 |
| `HT-NET-002` | 502/503 | network | — | 服务暂不可用 | 条件 |
| `HT-NET-003` | — | network | — | SSE 断连（传输层，未必有 JSON 体） | 重连/降级轮询 |
| `HT-AUTH-001` | 401 | permission | unauthenticated | 无会话或会话失效 | 完成登录后 |
| `HT-AUTH-002` | 401 | permission | require_reauth | L3+ 需再认证 | 完成 API-004 后 |
| `HT-AUTH-003` | 401 / 浏览器 302 | permission | unauthenticated | OIDC `state`/`nonce`/PKCE 失败或 IdP `error` | SPA 恢复面后重新 start |
| `HT-AUTH-004` | 401/403 | permission | unauthenticated | 入站 HMAC 验签失败；不泄露签名材料 | 否 |
| `HT-IAM-001` | 403 | permission | forbidden | 角色不足 | 否 |
| `HT-IAM-002` | 403 | permission | forbidden | 四眼违例 | 否 |
| `HT-IAM-003` | 403 | permission | forbidden | ApiToken scope 不足 | 否 |
| `HT-IAM-004` | 401/403 | permission | forbidden | Token 过期或已吊销 | 否 |
| `HT-IAM-005` | 403 | permission | forbidden | Token 项目白名单外 | 否 |
| `HT-RES-001` | 404 | permission | not_found | 不存在或不可感知（含跨租户） | 否 |
| `HT-VAL-001` | 400 | business | validation | 字段/格式校验失败 | 修正后 |
| `HT-VAL-002` | 400 | business | validation | Job Schema / 变量解析 / Job 不存在 | 修正后 |
| `HT-VAL-003` | 400 | business | validation | 文件类型/大小/checksum/扫描失败 | 修正后 |
| `HT-VAL-004` | 400 | business | validation | AI 输出 schema / evidence_refs 校验失败 | 按任务语义 |
| `HT-VAL-005` | 400 | business | validation | 开放重定向：`return_path` 不在相对路径白名单 | 否 |
| `HT-STATE-001` | 409 | business | precondition | 当前态不允许该命令 | 对账后 |
| `HT-STATE-002` | 409 | business | precondition | 审批已消费/不可再决 | 对账后 |
| `HT-VER-001` | 409 | business | version_conflict | `expected_version` 不匹配 | 拉新版本后人工 |
| `HT-IDEM-001` | 409 | business | idempotency_conflict | 同 key 异 hash | 否（换 key 或对齐参数） |
| `HT-POL-001` | 403 | business | policy_deny | Policy Gate `DENY` | 否 |
| `HT-POL-002` | 403 | business | policy_deny | 未声明 sideEffectLevel / 白名单外压测目标 | 否 |
| `HT-QUOTA-001` | 429 | business | quota | OrgQuota Token/执行 slot/压测预算不足 | 条件 |
| `HT-QUOTA-002` | 429 | business | rate_limited | 入口或能力限流（网关或应用语义） | 条件 |
| `HT-APPR-001` | 409 | business | approval_invalid | `param_hash` 不一致 / 审批失效 | 新审批 |
| `HT-APPR-002` | 409 | business | approval_invalid | TTL 过期（EXPIRED）后对已失效请求操作 | 新审批或取消 run |
| `HT-EXT-001` | 502 | business | external | 连接器调用失败（已落账或回执标明外部） | 按连接器 |
| `HT-EXT-002` | 409 | business | external | `execution_result=unknown` 需对账，禁止盲重试 | 否 |
| `HT-ASYNC-001` | 200/202 | business | async_partial | 部分成功；`failed_items` 必现 | 按任务 |
| `HT-ASYNC-002` | 422 | business | async_partial | 异步任务失败（生成/导入/解析） | 按任务 |
| `HT-INT-001` | 500 | business | internal | 未分类内部错误；只暴露 trace_id | 条件 |

业务错误 **失败也审计**。`details` 可含 `failed_items[]`（A1）、字段路径，不得含 Prompt、凭证、Webhook secret、`token_hash`、`credential_ref` **值**。

### 4.4 网络未决：先 GET 对账

边界 §7.2 / `02_api` §4.2 / 架构 §9.1：传输超时、断连、网关 5xx、客户端放弃等待时，**业务语义未知**。

| 步骤 | 契约 |
| --- | --- |
| 1 | 不得把 UI「提交中结束」或超时当作成功或失败 |
| 2 | **先 GET** 领域资源或 `API-071` 回执：已有 `resource_id` / 同一幂等回执 → 视为已受理，禁止换新 key 再 POST |
| 3 | GET 仍看不到资源且无回执：才允许用**同一** `Idempotency-Key` 重放命令 |
| 4 | SSE 断连（`HT-NET-003`）只触发重连或降级轮询，**禁止**据此把 TestRun 标 FAILED/TIMEOUT 或把 ApprovalRequest 标 EXPIRED |
| 5 | `execution_result=unknown`（`HT-EXT-002`）只对账 / 人工接管，禁止盲重试 |

查询失败不得解释为空集：空列表是 `200` + `data.items: []`；网络 / 权限走错误外壳。

### 4.5 `trace_id` 与 AuditEvent 关联

`ErrorEnvelope.error.trace_id` **失败也必须有**（含 5xx）。它是请求级追踪标识，与可观测因果链（架构 §14.3：trace、tenant/project、actor、run、approval、connector、`external_request_id`）对齐。

| 机制 | 用途 | 禁止 |
| --- | --- | --- |
| `trace_id` | 支撑排障、SIEM、与应用日志 / Trace 对齐 | 当作幂等键、业务 `version`、SSE 事件 ID |
| AuditEvent | append-only 业务/安全归因；失败、DENY、四眼违例、验签失败也插行 | 用 `updated_at` 冒充审计；写入 Prompt / secret / `token_hash` / `credential_ref` **值** |
| 关联方式 | 时间窗 + `organization_id` + `actor_user_id` + `resource_type`/`resource_id` + `request_hash` + `approval_id`；运维用同一 `trace_id` 查日志 / Trace | **不**要求把 `trace_id` 升格为领域字段或第 24 对象；`data_model.md` 未冻结 AuditEvent.`trace_id` 列，本契约不发明该列 |
| 错误 `details` | 字段路径、`failed_items` | Restricted 明文、Webhook secret、Token 明文 |

业务错误失败也审计。`message` 用户可理解；禁止内部栈、SQL、密钥、Prompt 原文。

### 4.6 细分码使用说明

`HT-VAL-005` 与 `HT-AUTH-004` 已列入 §4.3 主表。HMAC 验签失败统一 `HT-AUTH-004`（不再用笼统的 `HT-AUTH-001` 表达签名失败）。`API-001` 非法 `return_path` 使用 `HT-VAL-005`；一般字段校验仍用 `HT-VAL-001`。

### 4.7 全量 `HT-*` 的 `retryable` 建议

`retryable` 是**客户端是否允许自动/半自动再试**的契约提示，不是配额恢复时间表。`true` 仍须服从幂等与「先 GET」。`false` 表示换参数或换流程前不要自动重放同一请求。

| code | `retryable` 建议 | 重试前提 | 说明 |
| --- | --- | --- | --- |
| `HT-NET-001` | `true`（条件） | **先 GET 对账**；命令复用同一 `Idempotency-Key` | 网关/上游超时，结果未决 |
| `HT-NET-002` | `true`（条件） | 退避后重试；命令同 key | 502/503 暂不可用 |
| `HT-NET-003` | `true`（通道） | SSE 重连或降级 GET 轮询 | 无 JSON 体亦可；禁止改业务态 |
| `HT-AUTH-001` | `false` → 认证后可再发 | 完成 SSO / 换有效 Token 后视为新请求周期 | 无会话或失效；不得伪装 404 |
| `HT-AUTH-002` | `false` → step-up 后可重放 | `API-004` 成功且 **hash 不变** 的同一 key | `REQUIRE_REAUTH` |
| `HT-AUTH-003` | `false` | SPA 停恢复面后重新 `API-001`（`prompt=login`） | `state`/`nonce`/PKCE 失败或 IdP `error`；浏览器走 API-002 失败 302 |
| `HT-AUTH-004` | `false` | 修正签名/密钥配置；禁止用猜签名重试刷接口 | HMAC 失败仍审计 |
| `HT-IAM-001` | `false` | 权限变更后由人再操作 | 角色不足 / 无组织上下文 |
| `HT-IAM-002` | `false` | 换审批人 | 四眼违例 |
| `HT-IAM-003` | `false` | 换 scope 或通道 | Token scope 不足 |
| `HT-IAM-004` | `false` | 重新签发 Token | 过期或已吊销 |
| `HT-IAM-005` | `false` | 调整 `project_ids` 或换 Token | 项目白名单外 |
| `HT-RES-001` | `false` | — | 不存在或不可感知（含跨租户） |
| `HT-VAL-001` | `false` | 修正字段后**新提交**（可新 key） | 一般校验 |
| `HT-VAL-002` | `false` | 修正 Job/变量后重提 | Schema / 解析 / Job 不存在 |
| `HT-VAL-003` | `false` | 换文件后重提 | 类型/大小/checksum/扫描 |
| `HT-VAL-004` | 按任务 | schema 修正或明确 degraded 路径 | AI 输出 / evidence_refs |
| `HT-VAL-005` | `false` | 换白名单内相对路径 | 开放重定向 |
| `HT-STATE-001` | `false`（对账后人工） | GET 当前态后再决定 | 当前态不允许 |
| `HT-STATE-002` | `false` | GET 审批；需则新请求 | 审批已消费/不可再决 |
| `HT-VER-001` | `false` | 拉新 `version` 后人工改 `expected_version` | CAS；禁止自动覆盖 |
| `HT-IDEM-001` | `false` | 换 key **或**对齐参数后用原 key | 同 key 异 hash |
| `HT-POL-001` | `false` | 政策变更后由人再 Preview | `DENY` |
| `HT-POL-002` | `false` | 改目标进白名单或声明 sideEffectLevel | 未声明 / 白名单外压测；**不进审批** |
| `HT-QUOTA-001` | `true`（条件） | 额度恢复后；仍走受理幂等 | OrgQuota Token/slot/压测预算 |
| `HT-QUOTA-002` | `true`（条件） | 限流窗口过后；**数值 TBD** | 入口或能力限流 |
| `HT-APPR-001` | `false` | 新 Preview + 新审批 | `param_hash` / 审批失效 |
| `HT-APPR-002` | `false` | 新审批或取消 run | TTL 后对 EXPIRED 再操作 |
| `HT-EXT-001` | 按连接器 | 连接器策略；须幂等 / 先查询 | 已落账的外部失败 |
| `HT-EXT-002` | `false` | 只对账 / 人工接管 | `execution_result=unknown` |
| `HT-ASYNC-001` | 按任务 | 仅失败项；禁止把 partial 当全成功 | `failed_items` 必现 |
| `HT-ASYNC-002` | 按任务 | 按生成/导入语义 | 异步任务失败 |
| `HT-INT-001` | `true`（条件） | 携带 `trace_id` 报障；命令同 key | 只暴露 trace，不暴露栈 |

压测与 Agent 任务**禁止自动重试**（`02_api` §4.2）；与上表不冲突：即使 `HT-NET-*` 为条件可重试，这两类命令的客户端默认 `retryable` 视为人工确认后的同 key 重放，不得静默循环。

---


---

## 5. 公共 OpenAPI 3.1 schema

```yaml
UUID:
  type: string
  format: uuid

Version:
  type: integer
  minimum: 1
  description: 对外 CAS 版本；映射聚合 aggregate_version，不是 SSE 事件 ID

CommandReceipt:
  type: object
  required: [id, command_type, status, accepted_at]
  properties:
    id:
      $ref: '#/UUID'
    command_type:
      type: string
    status:
      type: string
      enum: [accepted, running, succeeded, failed, partial]
    accepted_at:
      type: string
      format: date-time
    resource_type:
      type: string
    resource_id:
      $ref: '#/UUID'
    idempotency_key:
      type: string
    poll:
      type: object
      properties:
        path:
          type: string
        sse_path:
          type: string
    error:
      description: 仅 failed/partial 时出现；形状同 ErrorEnvelope.error

Page:
  type: object
  required: [next_cursor, has_more]
  properties:
    next_cursor:
      type: string
      nullable: true
    has_more:
      type: boolean
    limit:
      type: integer
      description: 本次返回上限；默认与最大值 TBD

ListEnvelope:
  type: object
  required: [data, page]
  properties:
    data:
      type: object
      required: [items]
      properties:
        items:
          type: array
    page:
      $ref: '#/Page'

ResourceEnvelope:
  type: object
  required: [data]
  properties:
    data:
      type: object
```

分页：cursor。`limit` 默认值与上限 **TBD**。排序/筛选：各列表端点声明；只暴露可对外语义字段。禁止把 Internal 运维列（`jira_sync_cursor`、`token_hash`）当作筛选器。

通用请求头：`Idempotency-Key`（命令）、`Authorization`（ApiToken）。会话走 Cookie。

---

### 5.1 公共 headers 与 query

```yaml
# components.parameters
IdempotencyKeyHeader:
  name: Idempotency-Key
  in: header
  required: false
  description: |
    不透明 UUID。受理幂等 scope = organization_id + command_type + 本值。
    禁止用标题、Jira key、参数 JSON 派生。GET 不使用。
    入站 Webhook（API-090）禁止本头。
    API-080 必须提供。其它可重试命令强烈建议。
    时效 TBD，本文不写默认小时数。
  schema:
    type: string
    format: uuid

AuthorizationBearerHeader:
  name: Authorization
  in: header
  required: false
  description: |
    仅 ApiToken 通道。会话走 Cookie，不使用本头携带 IdP token。
    示例（假值）：Bearer ht_live_xxxREDACTED
  schema:
    type: string
    pattern: "^Bearer .+$"

CookieSession:
  name: Cookie
  in: header
  required: false
  description: HttpOnly 会话 Cookie；具体 Cookie 名 TBD。浏览器不可读。
  schema:
    type: string

LastEventIDHeader:
  name: Last-Event-ID
  in: header
  required: false
  description: SSE 续传；服务端不透明 ID。不是 version，不是幂等键。
  schema:
    type: string

CursorQuery:
  name: cursor
  in: query
  required: false
  description: |
    不透明游标；由上一页 page.next_cursor 原样回传。客户端不得伪造或解码为内部列。
    禁止把 Internal 列（如 jira_sync_cursor、token_hash）当作筛选器。
  schema:
    type: string
    nullable: true

LimitQuery:
  name: limit
  in: query
  required: false
  description: 本次返回上限。默认值与最大值 TBD，未批不得写死数字。
  schema:
    type: integer
    minimum: 1
```

### 5.2 资源引用、门禁未评估、失败项

```yaml
ResourceRef:
  type: object
  additionalProperties: false
  required: [resource_type, resource_id]
  description: 跨对象稳定引用。引用不是授权（制品 object_key / Evidence content_ref 同此纪律）。
  properties:
    resource_type:
      type: string
      description: 对外资源类型名（如 test_run、approval_request）；不是第 24 对象
    resource_id:
      type: string
      format: uuid

UnevaluatedGate:
  type: object
  additionalProperties: false
  required: [evaluation, unevaluated_reason]
  description: |
    API-146：无 GateEvaluation 行时的查询投影。
    result 枚举仍仅为 pass/fail/waived；禁止 result=not_evaluated（Proposed ADR 0003，保持 Proposed）。
    绝不默认 pass。
  properties:
    evaluation:
      type: "null"
      description: 恒为 JSON null，表示无评估行
    unevaluated_reason:
      type: string
      description: |
        示例语义（具体码 TBD，不得发明第四种 result）：
        agent_source | cancelled_or_timeout | partial_report | policy_unmet
    test_run_id:
      type: string
      format: uuid

FailedItem:
  type: object
  additionalProperties: false
  required: [reason]
  description: |
    A1 / 导入 / 异步 partial 的显式失败项。禁止静默丢空。
    不得含 Prompt 原文、凭证、Webhook secret、token 明文。
  properties:
    item_ref:
      type: string
      description: 行/endpoint/源片段的稳定定位（非秘密）
    locator:
      type: string
      description: 可选；导入行号或 OpenAPI path 等
    reason:
      type: string
    details:
      type: object
      additionalProperties: true
      description: 可含字段路径；分级 ≤Confidential 且脱敏

CommandReceipt:
  type: object
  required: [id, command_type, status, accepted_at]
  properties:
    id:
      type: string
      format: uuid
    command_type:
      type: string
    status:
      type: string
      enum: [accepted, running, succeeded, failed, partial]
    accepted_at:
      type: string
      format: date-time
    resource_type:
      type: string
    resource_id:
      type: string
      format: uuid
    idempotency_key:
      type: string
      format: uuid
    poll:
      type: object
      additionalProperties: false
      properties:
        path:
          type: string
        sse_path:
          type: string
    error:
      description: 仅 failed/partial 时出现；形状同 ErrorEnvelope.error
    failed_items:
      type: array
      items:
        $ref: "#/FailedItem"
      description: status=partial 或 HT-ASYNC-001 时建议出现

Page:
  type: object
  required: [next_cursor, has_more]
  properties:
    next_cursor:
      type: string
      nullable: true
    has_more:
      type: boolean
    limit:
      type: integer
      description: 本次实际上限；默认与最大值 TBD

ErrorEnvelope:
  type: object
  required: [error]
  properties:
    error:
      type: object
      required: [code, class, subclass, message, retryable, trace_id]
      properties:
        code:
          type: string
          pattern: "^HT-[A-Z]+-[0-9]{3}$"
        class:
          type: string
          enum: [network, permission, business]
        subclass:
          type: string
          enum:
            - unauthenticated
            - require_reauth
            - forbidden
            - not_found
            - validation
            - precondition
            - version_conflict
            - idempotency_conflict
            - policy_deny
            - quota
            - rate_limited
            - approval_invalid
            - external
            - async_partial
            - internal
        message:
          type: string
        retryable:
          type: boolean
        details:
          type: object
          additionalProperties: true
        trace_id:
          type: string
        resource_type:
          type: string
        resource_id:
          type: string
          format: uuid
        failed_items:
          type: array
          items:
            $ref: "#/FailedItem"
```

`HT-NET-001` / `HT-NET-003` 在断连无体时允许无 JSON；一旦有体，仍用本外壳。HTTP 5xx 禁止框架默认 HTML。

`subclass` 对 `HT-NET-*` 可省略或不上表中的业务子类；有体时应给出可解析的 `class=network`。

### 5.3 敏感字段剔除清单（响应 / 错误 / SSE / 审计对外投影）

对照 `data_model.md` §8 Restricted：表内禁止明文，API **同样禁止回传值**。分类缺失按 Confidential fail-close。

| 字段 / 内容 | 存法（数据模型） | API 对外 |
| --- | --- | --- |
| `credential_ref` **值** | 引用 | **永不返回**；环境用 `has_credential` / `credential_present: boolean` |
| `token_hash` | argon2 | **永不返回** |
| ApiToken 明文 | 仅签发瞬间 | **仅 API-171 一次**；示例文档用 `ht_live_xxxREDACTED` |
| Prompt 原文 | 无列；`input_ref` 最多脱敏 object_key | `API-184`/`API-185` 无 Prompt；错误/SSE/审计禁止 |
| Webhook secret / `webhook_secret_ref` **值** | 引用 | 连接器详情无 secret；验签失败响应无期望签名 |
| IdP refresh / access token | 不进浏览器 | callback 不把 token 写入 body |
| Outbox `payload` 秘密、制品 Restricted 正文 | 只传 ID / object_key / classification | SSE 帧禁止 Restricted 正文、未脱敏字节 |
| `jira_sync_cursor` | Internal 运维列 | 禁止作筛选器或列表字段 |

Confidential（如 email、标题、轨迹摘要）最小化、禁缓存；不在错误 `message` 中回显完整转储。

---


## 6. API 清单总表

**鉴权缩写**：`Sess` = OIDC 会话；`Tok` = ApiToken；`HMAC` = 入站签名；`Pub` = 仅 OIDC 跳转（callback 仍校验 state）。  
**§5.1 类**：1 领域读 · 2 写与状态迁移 · 3 L2+ Preview/Execute · 4 AI · 5 导入导出 · 6 SSE · 7 通知 · 8 制品。  
**M**：里程碑提示（M0–M4）；未到里程碑的端点仍写入契约，实现可延后，不得当作不存在。

### 6.1 认证会话（API-001–006）

| ID | Method | Path | 类 | 鉴权 | 说明 |
| --- | --- | --- | --- | --- | --- |
| API-001 | GET | `/api/v1/auth/oidc/start` | — | Pub | 开始 Authorization Code + PKCE；设置 state/nonce；可选 `prompt=login` |
| API-002 | GET | `/api/v1/auth/oidc/callback` | — | Pub | IdP 回调；签发服务端会话；失败 302 回 SPA（`oidc=failed`） |
| API-003 | POST | `/api/v1/auth/session/logout` | 2 | Sess | 吊销会话 |
| API-004 | POST | `/api/v1/auth/reauth` | 2 | Sess | L3+ step-up |
| API-005 | GET | `/api/v1/me` | 1 | Sess | 用户、租户、项目角色 |
| API-006 | GET | `/api/v1/auth/session` | 1 | Sess | 会话元数据（过期提示）；不含 token 明文 |

### 6.2 身份、项目、成员、配额（API-010–019）

| ID | Method | Path | 类 | 鉴权 | 说明 |
| --- | --- | --- | --- | --- | --- |
| API-010 | GET | `/api/v1/organizations/current` | 1 | Sess | 当前租户；含降级/kill 开关**投影**（非第 24 对象） |
| API-011 | GET | `/api/v1/projects` | 1 | Sess | 项目列表（Jira 只读镜像，无手工建项目） |
| API-012 | GET | `/api/v1/projects/{project_id}` | 1 | Sess | 总览：连接健康、Jira 映射、最近活动 |
| API-013 | GET | `/api/v1/projects/{project_id}/members` | 1 | Sess | 成员列表 |
| API-014 | POST | `/api/v1/projects/{project_id}/members` | 2 | Sess | 添加成员 |
| API-015 | PATCH | `/api/v1/projects/{project_id}/members/{user_id}` | 2 | Sess | 改角色 |
| API-016 | DELETE | `/api/v1/projects/{project_id}/members/{user_id}` | 2 | Sess | 移除成员 |
| API-017 | GET | `/api/v1/org-quotas/current` | 1 | Sess | OrgQuota 余量 |
| API-018 | GET | `/api/v1/projects/{project_id}/quota-view` | 1 | Sess | 项目级配额视图 |
| API-019 | GET | `/api/v1/projects/{project_id}/notification-subscriptions` | 1 | Sess | 订阅配置 |

### 6.3 工作台、通知、审计、证据（API-020–029）

| ID | Method | Path | 类 | 鉴权 | 说明 |
| --- | --- | --- | --- | --- | --- |
| API-020 | GET | `/api/v1/workbench` | 1 | Sess | 待审批 / 进行中 run / 门禁异常 / 预算 |
| API-021 | GET | `/api/v1/notifications` | 7 | Sess | 通知列表（查询投影，非第 24 对象） |
| API-022 | GET | `/api/v1/notifications/badge` | 7 | Sess | 未读角标 |
| API-023 | POST | `/api/v1/notifications/{notification_id}/read` | 7 | Sess | 标已读；产品形态 G4 仍 TBD |
| API-024 | GET | `/api/v1/audit-events` | 1 | Sess | 审计检索 |
| API-025 | GET | `/api/v1/audit-events/{audit_event_id}` | 1 | Sess | 审计详情 |
| API-026 | GET | `/api/v1/evidence-objects` | 1 | Sess | 证据检索 |
| API-027 | GET | `/api/v1/evidence-objects/{evidence_object_id}` | 1 | Sess | 证据详情 |
| API-028 | POST | `/api/v1/evidence-objects/export-packages` | 5 | Sess | 证据包导出受理 |
| API-029 | PATCH | `/api/v1/projects/{project_id}/notification-subscriptions` | 2 | Sess | 更新订阅 |
| API-040 | PUT | `/api/v1/organizations/current/siem-export` | 2 | Sess | SIEM 外发配置（非第 24 对象；body 无密钥明文） |

### 6.4 TestCase（API-030–039）

| ID | Method | Path | 类 | 鉴权 | 说明 |
| --- | --- | --- | --- | --- | --- |
| API-030 | GET | `/api/v1/test-cases` | 1 | Sess | 列表；筛选含 `ai-generated` |
| API-031 | GET | `/api/v1/test-cases/{test_case_id}` | 1 | Sess | 详情（步骤、定位器健康；凭证不返回） |
| API-032 | POST | `/api/v1/test-cases` | 2 | Sess | 保存草稿 → DRAFT + Version |
| API-033 | PATCH | `/api/v1/test-cases/{test_case_id}` | 2 | Sess | 步骤等编辑（新 Version） |
| API-034 | POST | `/api/v1/test-cases/{test_case_id}/submit-review` | 2 | Sess | DRAFT→PENDING_REVIEW |
| API-035 | POST | `/api/v1/test-cases/{test_case_id}/review` | 2 | Sess | 通过→ACTIVE / 驳回→DRAFT |
| API-036 | POST | `/api/v1/test-cases/{test_case_id}/deprecate` | 2 | Sess | →DEPRECATED |
| API-037 | GET | `/api/v1/test-cases/{test_case_id}/versions` | 1 | Sess | 版本历史 |
| API-038 | GET | `/api/v1/test-cases/{test_case_id}/versions/{version_id}` | 1 | Sess | 版本快照 |
| API-039 | POST | `/api/v1/test-cases/{test_case_id}/rollback` | 2 | Sess | 回滚指针（heal 回滚） |

### 6.5 TestPlan 与 PerfBaseline（API-050–059）

| ID | Method | Path | 类 | 鉴权 | 说明 |
| --- | --- | --- | --- | --- | --- |
| API-050 | GET | `/api/v1/test-plans` | 1 | Sess | 计划列表 |
| API-051 | GET | `/api/v1/test-plans/{test_plan_id}` | 1 | Sess | 计划详情 + 报告聚合 |
| API-052 | POST | `/api/v1/test-plans` | 2 | Sess | 创建 |
| API-053 | PATCH | `/api/v1/test-plans/{test_plan_id}` | 2 | Sess | 更新编排 |
| API-054 | PUT | `/api/v1/test-plans/{test_plan_id}/case-ids` | 2 | Sess | 用例集关联 |
| API-055 | PUT | `/api/v1/test-plans/{test_plan_id}/schedule` | 2 | Sess | 定时回归绑定 |
| API-056 | GET | `/api/v1/perf-baselines` | 1 | Sess | 基线列表 |
| API-057 | POST | `/api/v1/perf-baselines` | 2 | Sess | 创建（停用旧活跃） |
| API-058 | POST | `/api/v1/perf-baselines/{perf_baseline_id}/deactivate` | 2 | Sess | 停用 |
| API-059 | GET | `/api/v1/perf-baselines/{perf_baseline_id}` | 1 | Sess | 基线详情/对比数据 |

### 6.6 TestRun 查询、会话发起、控制（API-060–071）

| ID | Method | Path | 类 | 鉴权 | 说明 |
| --- | --- | --- | --- | --- | --- |
| API-060 | GET | `/api/v1/test-runs` | 1 | Sess 或 Tok `read` | 列表 |
| API-061 | GET | `/api/v1/test-runs/{test_run_id}` | 1 | Sess 或 Tok `read` | 详情 |
| API-062 | POST | `/api/v1/test-runs` | 2 | **Sess** | 手动/调度配置发起；`trigger_type=manual\|schedule` |
| API-063 | POST | `/api/v1/test-runs/{test_run_id}/cancel` | 2 | Sess | 取消/终止受理 |
| API-064 | GET | `/api/v1/test-runs/{test_run_id}/case-results` | 1 | Sess 或 Tok `read` | 用例结果 |
| API-065 | GET | `/api/v1/case-results/{case_result_id}` | 1 | Sess 或 Tok `read` | 单条结果 |
| API-066 | GET | `/api/v1/case-results/{case_result_id}/step-runs` | 1 | Sess | 步骤 |
| API-067 | GET | `/api/v1/test-runs/{test_run_id}/trajectory` | 1 | Sess | Agent A8 轨迹（脱敏） |
| API-068 | POST | `/api/v1/test-runs/{test_run_id}/script-drafts` | 2 | Sess | 轨迹→新 TestCase DRAFT |
| API-069 | GET | `/api/v1/projects/{project_id}/execution-options` | 1 | Sess | ACTIVE 环境、用例可选性、容量 |
| API-070 | GET | `/api/v1/execution-environments/{environment_id}/jobs/{job_id}/params-schema` | 1 | Sess | Job 参数 Schema |
| API-071 | GET | `/api/v1/command-receipts/{receipt_id}` | 1 | Sess 或 Tok | 操作回执查询（协议，非领域 CRUD） |

### 6.7 ApiToken 发起执行（系统入口，单列）

| ID | Method | Path | 类 | 鉴权 | 说明 |
| --- | --- | --- | --- | --- | --- |
| API-080 | POST | `/api/v1/test-runs` | 2 | **Tok `execute`** | 与 API-062 同路径；`trigger_type=api_token`；必须 `Idempotency-Key` |

### 6.8 入站 Webhook（系统入口，单列）

| ID | Method | Path | 类 | 鉴权 | 说明 |
| --- | --- | --- | --- | --- | --- |
| API-090 | POST | `/api/v1/inbound-webhooks/{connector_id}` | — | **HMAC** | CI / GitHub / Release 观察入口；先验签再 Inbox |

### 6.9 ExecutionEnvironment（API-100–106）

| ID | Method | Path | 类 | 鉴权 | 说明 |
| --- | --- | --- | --- | --- | --- |
| API-100 | GET | `/api/v1/execution-environments` | 1 | Sess | 列表（凭证字段永不返回） |
| API-101 | GET | `/api/v1/execution-environments/{environment_id}` | 1 | Sess | 详情；`credential_present: boolean` |
| API-102 | POST | `/api/v1/execution-environments` | 2+3 | Sess | 创建 PENDING_APPROVAL；须经 Preview 或内联 Gate |
| API-103 | POST | `/api/v1/execution-environments/{environment_id}/disable` | 2 | Sess | →DISABLED |
| API-104 | GET | `/api/v1/execution-environments/{environment_id}/jobs` | 1 | Sess | Job Registry |
| API-105 | GET | `/api/v1/execution-environments/{environment_id}/health` | 1 | Sess | 健康投影（写入仍系统内部） |
| API-106 | POST | `/api/v1/connectors/{connector_id}/credential-refs` | 2 | Sess | 登记凭证引用（body 无明文；上传走独立机密通道 **TBD**） |

> API-106：浏览器**禁止**提交密钥明文。实现可用一次性上传会话；契约只允许 `credential_ref` 已存在的引用绑定。明文通道不在本文展开。

### 6.10 审批与 L2+ Preview（API-110–121）

| ID | Method | Path | 类 | 鉴权 | 说明 |
| --- | --- | --- | --- | --- | --- |
| API-110 | GET | `/api/v1/approval-requests` | 1 | Sess | 队列 + 九要素 |
| API-111 | GET | `/api/v1/approval-requests/{approval_request_id}` | 1 | Sess | 详情 |
| API-112 | POST | `/api/v1/approval-requests/{approval_request_id}/decisions` | 2+3 | Sess | 批准/拒绝 |
| API-113 | POST | `/api/v1/approval-requests/{approval_request_id}/resubmissions` | 2+3 | Sess | 新请求（新 param_hash） |
| API-120 | POST | `/api/v1/action-previews` | 3 | Sess | Policy Gate Preview；生成 param_hash |
| API-121 | GET | `/api/v1/action-previews/{preview_id}` | 3 | Sess | 回取 Preview（TTL TBD） |

副作用 **Execute**（行锁 consume、execution intent）= 系统内部，见 §12。

### 6.11 失败分诊（API-130–133）

| ID | Method | Path | 类 | 鉴权 | 说明 |
| --- | --- | --- | --- | --- | --- |
| API-130 | GET | `/api/v1/test-runs/{test_run_id}/failure-clusters` | 1 | Sess | 聚类报告 |
| API-131 | GET | `/api/v1/failure-clusters/{failure_cluster_id}` | 1 | Sess | 簇详情 |
| API-132 | PATCH | `/api/v1/failure-clusters/{failure_cluster_id}` | 2 | Sess | 人工修正（提交才调） |
| API-133 | GET | `/api/v1/failure-clusters/{failure_cluster_id}/similar` | 1 | Sess | 历史相似失败 |

### 6.12 质量门禁（API-140–146）

| ID | Method | Path | 类 | 鉴权 | 说明 |
| --- | --- | --- | --- | --- | --- |
| API-140 | GET | `/api/v1/quality-gate-policies` | 1 | Sess | 策略列表 |
| API-141 | GET | `/api/v1/quality-gate-policies/{policy_id}` | 1 | Sess | 策略详情 |
| API-142 | POST | `/api/v1/quality-gate-policies` | 2 | Sess | 创建 |
| API-143 | PATCH | `/api/v1/quality-gate-policies/{policy_id}` | 2 | Sess | 更新（升版本；blocking 显式） |
| API-144 | GET | `/api/v1/gate-evaluations` | 1 | Sess | 评估历史 |
| API-145 | GET | `/api/v1/gate-evaluations/{gate_evaluation_id}` | 1 | Sess | 评估明细 |
| API-146 | GET | `/api/v1/test-runs/{test_run_id}/gate-evaluation` | 1 | Sess | 挂接或 `unevaluated_reason` |

### 6.13 ReleaseTask（API-150–155）

| ID | Method | Path | 类 | 鉴权 | 说明 |
| --- | --- | --- | --- | --- | --- |
| API-150 | GET | `/api/v1/release-tasks` | 1 | Sess | 列表（M3） |
| API-151 | GET | `/api/v1/release-tasks/{release_task_id}` | 1 | Sess | 含 Readiness 与 A5 草稿只读 |
| API-152 | POST | `/api/v1/release-tasks` | 2 | Sess | 圈定版本 → DRAFT |
| API-153 | POST | `/api/v1/release-tasks/{release_task_id}/retries` | 2 | Sess | FAILED_RETRYABLE 幂等重试 |
| API-154 | POST | `/api/v1/release-tasks/{release_task_id}/cancel` | 2 | Sess | 取消 |
| API-155 | GET | `/api/v1/release-tasks/{release_task_id}/readiness` | 1 | Sess | Readiness 投影 |

`release_push` 确认走 API-120 Preview + 审批，不提供「执行生产发布」API。

### 6.14 集成中心（API-160–167）

| ID | Method | Path | 类 | 鉴权 | 说明 |
| --- | --- | --- | --- | --- | --- |
| API-160 | GET | `/api/v1/connectors` | 1 | Sess | 连接器列表 |
| API-161 | GET | `/api/v1/connectors/{connector_id}` | 1 | Sess | 详情；无 secret |
| API-162 | POST | `/api/v1/connectors` | 2 | Sess | 注册 |
| API-163 | PATCH | `/api/v1/connectors/{connector_id}` | 2 | Sess | 更新契约/配置版本 |
| API-164 | GET | `/api/v1/connectors/{connector_id}/webhook-deliveries` | 1 | Sess | 入站投递历史 |
| API-165 | GET | `/api/v1/connectors/{connector_id}/outbound-channels` | 1 | Sess | 出站通知渠道 |
| API-166 | PUT | `/api/v1/connectors/{connector_id}/outbound-channels` | 2 | Sess | 配置渠道 |
| API-167 | PUT | `/api/v1/projects/{project_id}/ci-trigger-bindings` | 2 | Sess | 仓库/分支 ↔ 计划 |

### 6.15 ApiToken 管理（API-170–172）

| ID | Method | Path | 类 | 鉴权 | 说明 |
| --- | --- | --- | --- | --- | --- |
| API-170 | GET | `/api/v1/api-tokens` | 1 | Sess | 列表（前缀、scopes、过期；无哈希无明文） |
| API-171 | POST | `/api/v1/api-tokens` | 2 | Sess | 签发；**响应仅一次** `token` |
| API-172 | POST | `/api/v1/api-tokens/{api_token_id}/revocations` | 2 | Sess | 吊销即时生效 |

### 6.16 AI 能力（API-180–197）

| ID | Method | Path | 类 | 鉴权 | 说明 |
| --- | --- | --- | --- | --- | --- |
| API-180 | POST | `/api/v1/ai/generations` | 4+5 | Sess | A1 受理；不落 TestCase |
| API-181 | GET | `/api/v1/ai/generations/{generation_id}` | 4 | Sess | 生成任务/暂存状态 |
| API-182 | GET | `/api/v1/ai/generations/{generation_id}/drafts` | 4 | Sess | 结构化草稿 + failed_items |
| API-183 | GET | `/api/v1/ai/cost-dashboard` | 1 | Sess | 成本聚合 |
| API-184 | GET | `/api/v1/ai-invocation-logs` | 1 | Sess | 日志列表；无 Prompt |
| API-185 | GET | `/api/v1/ai-invocation-logs/{log_id}` | 1 | Sess | 日志详情；无 Prompt |
| API-190 | GET | `/api/v1/copilot-sessions` | 4 | Sess | 会话列表（M3+） |
| API-191 | POST | `/api/v1/copilot-sessions` | 4 | Sess | 创建会话 |
| API-192 | POST | `/api/v1/copilot-sessions/{session_id}/messages` | 4 | Sess | A6 提问 |
| API-193 | GET | `/api/v1/copilot-sessions/{session_id}` | 4 | Sess | 会话（消息 Confidential 最小化） |
| API-194 | GET | `/api/v1/skills` | 1 | Sess | 技能（M4） |
| API-195 | POST | `/api/v1/skill-versions/{skill_version_id}/publications` | 2 | Sess | 三级发布 |
| API-196 | GET | `/api/v1/model-routes` | 1 | Sess | 路由表 |
| API-197 | PUT | `/api/v1/model-routes/{model_route_id}` | 2 | Sess | 更新路由 |
| API-198 | POST | `/api/v1/model-routes/{model_route_id}/connection-tests` | 2 | Sess | 测试连接 |
| API-199 | POST | `/api/v1/organizations/current/capability-controls/tighten` | 2 | Sess | kill switch **关停** L1 即时 |

`kill_switch_restore` 走 API-120，禁止用 tighten 接口放开。

### 6.17 导入导出（API-200–205）

| ID | Method | Path | 类 | 鉴权 | 说明 |
| --- | --- | --- | --- | --- | --- |
| API-200 | POST | `/api/v1/test-cases/imports` | 5 | Sess | Excel 导入受理；初始生命周期 TBD |
| API-201 | GET | `/api/v1/test-cases/imports/{receipt_id}` | 5 | Sess | 导入结果/失败明细 |
| API-202 | POST | `/api/v1/test-cases/exports` | 5 | Sess | Excel 导出受理 |
| API-203 | GET | `/api/v1/test-cases/exports/{receipt_id}` | 5 | Sess | 导出状态 |
| API-204 | GET | `/api/v1/import-sources/{source_id}` | 5 | Sess | A1 源文件元数据（无原文 dump） |
| API-205 | POST | `/api/v1/import-sources` | 5 | Sess | 登记 OpenAPI/Postman/curl 源 |

### 6.18 SSE（API-210–213）

| ID | Method | Path | 类 | 鉴权 | 说明 |
| --- | --- | --- | --- | --- | --- |
| API-210 | GET | `/api/v1/test-runs/{test_run_id}/events` | 6 | Sess | 执行/解析/聚类进度 |
| API-211 | GET | `/api/v1/ai/generations/{generation_id}/events` | 6 | Sess | A1 进度 |
| API-212 | GET | `/api/v1/command-receipts/{receipt_id}/events` | 6 | Sess | 导入导出打包进度 |
| API-213 | GET | `/api/v1/events` | 6 | Sess | 审批/降级/通知轻量 hint；冲突以 GET 资源为准 |

### 6.19 制品访问（API-220–223）

| ID | Method | Path | 类 | 鉴权 | 说明 |
| --- | --- | --- | --- | --- | --- |
| API-220 | GET | `/api/v1/artifacts/{artifact_id}` | 8 | Sess | 元数据；`object_key` 非授权 |
| API-221 | GET | `/api/v1/artifacts/{artifact_id}/content` | 8 | Sess | **M0/M1 代理下载** |
| API-222 | POST | `/api/v1/artifacts/{artifact_id}/access-grants` | 8 | Sess | **Proposed M2+** 短期授权；Restricted 拒绝走预签名 |
| API-223 | GET | `/api/v1/export-packages/{receipt_id}/content` | 8 | Sess | 导出包代理下载 |

---

## 7. 端点契约

每个端点使用固定结构（与 §7.1 约定一致）：鉴权与角色/scope、同步性、请求/响应 OpenAPI 3.1 片段、成功判定（对照边界 §6）、错误码、幂等/分页/筛选。

下列分节由专题合并：**7.R** 查询、**7.W** 写与状态迁移、**7.L** L2+ Preview/审批/Token 发起/Webhook、**7.A** AI/导入导出/SSE/制品。同一 ID 以分节正文为准；§6 清单锁定 Method/Path。

响应字段为对外语义，不是表列全集。禁止 Restricted 明文、Prompt 原文、`token_hash`、`credential_ref` 值、Webhook secret。

### 7.0 认证跳转端点（OIDC start / callback / 会话探测）

> API-003 / API-004 见 §7.W；API-005 见 §7.R。本节补齐清单中的跳转与会话探测，避免只在 §6 出现而无契约正文。

#### API-001 `GET /api/v1/auth/oidc/start`

1. **鉴权**：无会话。限流见 §11（OIDC start 必覆盖）。
2. **同步性**：同步。实现可为 `302` 至 IdP，或 `200` 返回 `authorization_url`（SPA）。
3. **请求**：query `return_path`（可选，必须是**相对路径白名单**内，防开放重定向）；query `prompt`（可选，**仅**允许省略或 `login`）。`prompt=login` 映射 OIDC `prompt=login`，用于 SSO 失败后强制 IdP 出示企业账号密码表单。首次登录**省略** `prompt`，由 IdP 自行尝试 SSO。非法 `prompt` → `HT-VAL-001`。
4. **响应**：不返回 `code_verifier`（只存服务端会话草稿）；不返回 IdP token。
5. **成功判定**：到达 IdP 授权页 **≠** 登录成功。权威成功以 API-002 签发会话且 API-005 可查询为准（边界 §6-14）。
6. **错误码**：`HT-VAL-001`、`HT-VAL-005`、`HT-QUOTA-002`、`HT-INT-001`。
7. **幂等**：不适用。IdP、claim、MFA、会话时长 **TBD**。HuntAI **不**收集或校验用户密码；密码表单只存在于 IdP。

#### API-002 `GET /api/v1/auth/oidc/callback`

1. **鉴权**：校验 `state` / `nonce` / PKCE `code`；尚无业务会话。
2. **同步性**：同步；成功 `302` 回前端并 Set-Cookie。
3. **请求**：IdP query `code`、`state`；失败时可为 OIDC `error`（无 `code`）。
4. **响应**：Body **不**返回 access_token / refresh_token 明文。
5. **成功判定**：后续 `API-005` 返回租户与角色。无组织上下文 → 拒绝（`HT-IAM-001`），不创建默认租户。
6. **错误码 / 浏览器失败路径**：`state`/`nonce`/PKCE 失败、缺 `code`、或 IdP `error` 视为 `HT-AUTH-003`。对浏览器 **不**返回 ErrorEnvelope body，改为 `302` 至已校验的 `return_path`（缺省 `/`）并附加 query `oidc=failed`。失败跳转 URL **禁止**携带 `code` / `state` / IdP token / `code_verifier` / `error_description`。SPA 见到该标记必须停在全局壳恢复面，禁止自动再次 `API-001`。用户确认后重新 `API-001`（`prompt=login`）。失败仍写 `trace_id` 审计/日志，不记录密钥。
7. **限流**：§11 必覆盖。

#### API-006 `GET /api/v1/auth/session`

1. **鉴权**：Sess。
2. **同步性**：同步查询。
3. **响应**：`expires_at`（若有）、`reauth_required: boolean`。无 token 明文。会话时长数值 **TBD**。
4. **成功判定**：返回当前会话投影；不构成领域命令成功。
5. **错误码**：`HT-AUTH-001`（无会话时不得伪装 404）。

### 7.R 查询端点

#### 7.R0 读端点共用 schema

```yaml
# 角色（ProjectMember）
Role:
  type: string
  enum: [owner, admin, tester, viewer]

# 数据分级（响应中只作标注，不改变禁止明文规则）
DataClassification:
  type: string
  enum: [Public, Internal, Confidential, Restricted]

# 可变资源公共头
MutableResourceMeta:
  type: object
  required: [id, version, created_at, updated_at]
  properties:
    id: { $ref: '#/UUID' }
    version: { $ref: '#/Version' }
    created_at: { type: string, format: date-time }
    updated_at: { type: string, format: date-time }
    created_by: { $ref: '#/UUID' }

# append-only / 不可变资源公共头（无 version / updated_at）
AppendOnlyMeta:
  type: object
  required: [id, created_at]
  properties:
    id: { $ref: '#/UUID' }
    created_at: { type: string, format: date-time }
    created_by: { $ref: '#/UUID' }

# TestRun 10 态（⊆ problem_model）
TestRunStatus:
  type: string
  enum:
    - PENDING
    - VALIDATING
    - RUNNING
    - WAITING_EXTERNAL
    - WAITING_APPROVAL
    - STOPPING
    - SUCCEEDED
    - FAILED
    - CANCELLED
    - TIMEOUT

TestRunTerminalStatus:
  type: string
  enum: [SUCCEEDED, FAILED, CANCELLED, TIMEOUT]

# CaseResult.outcome：与归一化完成事实对齐，不发明第四套状态机
CaseResultOutcome:
  type: string
  description: |
    与执行完成事实对齐：至少表达通过 / 失败 / 未完成。
    精确取值与报告归一化契约对齐，**TBD**（未批不得写成已冻结枚举）。
    禁止发明第四套业务状态机——不是 TestRun 10 态、不是 ApprovalRequest 6 态、
    不是 GateEvaluation.result（pass / fail / waived）、不是 AIInvocationLog.result。

# 门禁评估结果（禁止 not_evaluated）
GateEvaluationResult:
  type: string
  enum: [pass, fail, waived]

# 不可评估投影原因（不是 result 枚举）
UnevaluatedReason:
  type: string
  description: |
    无 GateEvaluation 行时的查询投影。示例码（精确集合 TBD）：
    agent_source | cancelled_or_timeout | partial_report | policy_unmet
    禁止写成 GateEvaluation.result=not_evaluated。

# 凭证存在性投影（永不返回引用值）
CredentialPresence:
  type: boolean
  description: 是否已绑定凭证引用；永不返回 credential_ref / webhook_secret_ref / token_hash 值

# 通用列表 query（各端点可收窄）
CursorPageQuery:
  type: object
  properties:
    cursor:
      type: string
      description: 不透明游标；首页省略
    limit:
      type: integer
      minimum: 1
      description: 本次上限；默认与最大值 TBD
```

通用 GET 错误子集（各端点再收窄）：`HT-AUTH-001`、`HT-RES-001`（跨租户 / 不可感知统一不存在）、`HT-IAM-001`（同租户角色不足）、`HT-IAM-003` / `HT-IAM-005`（仅 Tok 通道）、`HT-VAL-001`（非法 query）、`HT-QUOTA-002`、`HT-INT-001`、`HT-NET-001` / `HT-NET-002`。查询 **不适用** `HT-VER-001` / `HT-IDEM-001` / `HT-STATE-001`（写命令码）。

---

### 7.2 认证与当前主体（读）

#### API-005 `GET /api/v1/me`

相对 `api_spec.md` 骨架 **增补**字段：`user.is_disabled`、`organization.slug` / `version` / `is_active`、`capability_controls` 结构化投影、`memberships[].project_name`、`reauth_required`。骨架已有字段语义不变。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess（OIDC 会话）。**不允许** ApiToken。
   - 角色：任一已认证主体（不要求特定 ProjectMember 角色）。无组织上下文 → 拒绝（见错误）。
   - Token：不适用。
2. **同步性**：同步查询。
3. **Query params**：无。无筛选 / 排序 / 分页。
4. **Response YAML**

```yaml
MeResponse:
  allOf:
    - $ref: '#/ResourceEnvelope'
    - type: object
      properties:
        data:
          $ref: '#/Me'
Me:
  type: object
  required: [user, organization, memberships, reauth_required]
  properties:
    user:
      type: object
      required: [id, display_name, is_disabled]
      properties:
        id: { $ref: '#/UUID' }
        display_name: { type: string }
        email:
          type: string
          description: Confidential；按最小需要返回（登录主体自身）
        is_disabled: { type: boolean }
    organization:
      type: object
      required: [id, name, slug, version, is_active, capability_controls]
      properties:
        id: { $ref: '#/UUID' }
        name: { type: string, description: Confidential 最小化（当前租户名） }
        slug: { type: string }
        version: { $ref: '#/Version' }
        is_active: { type: boolean }
        capability_controls:
          type: object
          description: |
            降级 / kill 开关投影，供全局横幅。非第 24 对象。
            关停位与生效范围；不含内部实现、不含恢复审批细节。
          required: [ai_global_tightened, tightened_capabilities, tightened_modules]
          properties:
            ai_global_tightened: { type: boolean }
            tightened_capabilities:
              type: array
              items: { type: string, description: A1–A8 能力码；精确集合 TBD }
            tightened_modules:
              type: array
              items:
                type: string
                description: 模块级（Copilot / Release / 压测 / 连接器写入等）；精确集合 TBD
            banner_scope:
              type: string
              description: 横幅生效范围文案键；枚举 TBD
    memberships:
      type: array
      items:
        type: object
        required: [project_id, role]
        properties:
          project_id: { $ref: '#/UUID' }
          project_name:
            type: string
            description: 展示用；Confidential 最小化
          role: { $ref: '#/Role' }
    reauth_required:
      type: boolean
      description: 会话是否已越过 L3+ 再认证窗口（窗口秒数 TBD）；权威仍以每请求 Policy Gate 为准
```

5. **成功判定**：边界 **§6-14**：权限以后端每请求为准；本接口只提供渲染输入。返回租户 + 项目角色快照 ≠ 后续命令已授权。
6. **错误码**：`HT-AUTH-001`（禁止伪装 404）、`HT-IAM-001`（无组织上下文）、`HT-QUOTA-002`、`HT-INT-001`。
7. **version**：`organization.version` 用于租户治理开关对账。成员角色以本响应 + 后续成员 GET 为准，无独立 membership version（成员 CAS **TBD**）。

---

### 7.3 身份、项目、配额、订阅（读）

#### API-010 `GET /api/v1/organizations/current`

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess。不允许 Tok。
   - 角色：当前租户任一成员（`owner` / `admin` / `tester` / `viewer` 任一项目角色即可）。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**

```yaml
OrganizationCurrent:
  type: object
  required: [id, name, slug, version, is_active, capability_controls]
  properties:
    id: { $ref: '#/UUID' }
    name: { type: string, description: Confidential 最小化 }
    slug: { type: string }
    version: { $ref: '#/Version' }
    is_active: { type: boolean }
    capability_controls:
      type: object
      description: 与 API-005 同形的关停 / 降级投影；非第 24 对象
    created_at: { type: string, format: date-time }
    updated_at: { type: string, format: date-time }
```

禁止：密钥、Prompt、内部 kill 实现细节。

5. **成功判定**：当前租户权威快照。横幅数据以后端投影为准（边界 §3.1-8）。关停 / 恢复是否已生效以本快照 + 审计为准，不以开关 UI 乐观态为准。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-001`（无组织上下文）、`HT-QUOTA-002`、`HT-INT-001`。
7. **version**：必返；后续治理写命令（kill 关停 / 恢复审批消费）用 `expected_version`。

---

#### API-011 `GET /api/v1/projects`

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess。不允许 Tok。
   - 角色：返回**当前用户为成员**的项目。四角色均可读本列表。
2. **同步性**：同步查询。
3. **Query params**

```yaml
parameters:
  - name: cursor
    in: query
    schema: { type: string }
  - name: limit
    in: query
    schema: { type: integer, minimum: 1 }
  - name: q
    in: query
    schema: { type: string }
    description: 名称 / Jira key 模糊匹配；匹配规则 TBD
  - name: sort
    in: query
    schema:
      type: string
      description: 白名单 TBD（如 name / created_at）；默认 TBD
```

禁止筛选 `jira_sync_cursor`。无手工建项目 API（本查询不隐含创建）。

4. **Response YAML**

```yaml
ProjectListItem:
  type: object
  required: [id, name, version, my_role]
  properties:
    id: { $ref: '#/UUID' }
    name: { type: string, description: Confidential 最小化 }
    jira_project_key:
      type: string
      nullable: true
    version: { $ref: '#/Version' }
    my_role: { $ref: '#/Role' }
    created_at: { type: string, format: date-time }
    updated_at: { type: string, format: date-time }
```

外壳：`ListEnvelope`（`data.items[]` = `ProjectListItem`）。**永不**返回 `jira_sync_cursor`。

5. **成功判定**：有权项目快照列表。空集 = 用户无项目成员身份，不是错误。项目存在性以本列表 + 详情 GET 为准（Jira 镜像，非前端推演）。
6. **错误码**：`HT-AUTH-001`、`HT-VAL-001`、`HT-QUOTA-002`、`HT-INT-001`。
7. **version**：每项 `version`；项目聚合可变（展示名等）。

---

#### API-012 `GET /api/v1/projects/{project_id}`

对照边界 **§2.14** 项目总览。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess。不允许 Tok。
   - 角色：该项目 `owner` / `admin` / `tester` / `viewer`。非成员 → `HT-RES-001`（不可感知）。
2. **同步性**：同步查询。
3. **Query params**：无（路径参数 `project_id`）。
4. **Response YAML**

```yaml
ProjectOverview:
  type: object
  required: [id, name, version, my_role, jira, connector_health, recent_activity]
  properties:
    id: { $ref: '#/UUID' }
    name: { type: string, description: Confidential 最小化 }
    version: { $ref: '#/Version' }
    my_role: { $ref: '#/Role' }
    jira:
      type: object
      properties:
        project_key: { type: string, nullable: true }
      description: Jira 只读映射；无 sync cursor
    bind_env_ids:
      type: array
      items: { $ref: '#/UUID' }
      description: 绑定环境 ID 列表；权威状态仍以环境 GET 为准
    connector_health:
      type: array
      description: 连接健康摘要（探测结果投影，非第五套状态机）
      items:
        type: object
        required: [connector_id, type, healthy]
        properties:
          connector_id: { $ref: '#/UUID' }
          type:
            type: string
            enum: [jira, github, ci, release]
          name: { type: string, description: Confidential 最小化 }
          healthy: { type: boolean }
          last_checked_at: { type: string, format: date-time, nullable: true }
          latency_ms: { type: integer, nullable: true }
    recent_activity:
      type: array
      description: 最近活动投影（来自审计 / 通知查询投影，非第 24 对象）
      items:
        type: object
        required: [occurred_at, summary]
        properties:
          occurred_at: { type: string, format: date-time }
          summary: { type: string }
          resource_type: { type: string }
          resource_id: { $ref: '#/UUID' }
          audit_event_id: { $ref: '#/UUID' }
    created_at: { type: string, format: date-time }
    updated_at: { type: string, format: date-time }
```

禁止：`jira_sync_cursor`、连接器 secret、`credential_ref` 值。

5. **成功判定**：总览以后端聚合为准（边界 §3.1-6 / §2.14）。前端不得本地拼连接健康或活动时间线当事实源。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-IAM-001`（同租户可见但无项目成员——当前兼容按不可感知 `HT-RES-001`）、`HT-INT-001`。
7. **version**：项目 `version`。连接器健康无独立 CAS（探测结果）。

---

#### API-013 `GET /api/v1/projects/{project_id}/members`

对照边界 **§2.14** 成员列表。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess。不允许 Tok。
   - 角色：该项目四角色均可读成员列表（写命令 API-014–016 另限 `owner` / `admin`）。
2. **同步性**：同步查询。
3. **Query params**

```yaml
parameters:
  - { name: cursor, in: query, schema: { type: string } }
  - { name: limit, in: query, schema: { type: integer, minimum: 1 } }
  - name: role
    in: query
    schema: { $ref: '#/Role' }
    description: 可选单角色筛选
```

4. **Response YAML**

```yaml
ProjectMemberItem:
  type: object
  required: [user_id, role]
  properties:
    user_id: { $ref: '#/UUID' }
    display_name: { type: string, description: Confidential 最小化 }
    email:
      type: string
      description: Confidential；仅当调用方为 owner/admin 时返回——否则省略（最小化）
    role: { $ref: '#/Role' }
    created_at: { type: string, format: date-time }
    updated_at: { type: string, format: date-time }
```

外壳：`ListEnvelope`。成员行无独立 `version`（成员 CAS 精确资源 **TBD**；写命令对账以项目 `version` 或成员 etag TBD）。

5. **成功判定**：成员与角色以后端表为准（平台角色权威，Jira 同步不得覆盖）。空列表仅当项目尚无成员（不应出现：至少有同步/引导 owner——若出现按数据异常 `HT-INT-001` 或仍 200，**TBD**）。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：本列表不返回成员 CAS。对账请带 API-012 的项目 `version`（写侧 TBD）。

---

#### API-017 `GET /api/v1/org-quotas/current`

对照边界 **§6-15**。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess。不允许 Tok。
   - 角色：任一租户成员可读余量（超限拒绝发生在 AI / 执行**命令**上）。`owner` / `admin` 可见完整账本；`tester` / `viewer` 可见余量投影（字段同形，不额外暴露内部记账流水——流水本就无对外表）。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**

```yaml
OrgQuotaCurrent:
  type: object
  required:
    - version
    - token_budget
    - token_reserved
    - token_consumed
    - executor_slot_quota
    - perf_concurrency_quota
  properties:
    version: { $ref: '#/Version' }
    token_budget: { type: number }
    token_reserved: { type: number }
    token_consumed: { type: number }
    token_remaining:
      type: number
      description: 投影 = budget - reserved - consumed；权威仍以后端三列计算为准
    executor_slot_quota: { type: integer }
    executor_slots_in_use:
      type: integer
      description: 当前占用投影；精确口径 TBD
    perf_concurrency_quota: { type: integer }
    perf_concurrency_in_use:
      type: integer
      description: 当前压测并发占用投影；精确口径 TBD
    updated_at: { type: string, format: date-time }
```

禁止：把本接口当扣减命令。无 Token 明文、无 Prompt。

5. **成功判定**：边界 **§6-15**：配额 / 预算权威在后端计算与扣减。本 GET 的余量展示 ≠ 后续 A1 / 发起执行已预留成功。超限发生在命令上 `HT-QUOTA-001`。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-001`、`HT-INT-001`。
7. **version**：账本 CAS；系统内部预留/确认/释放带 `expected_version`。对外以本查询为主。

---

#### API-018 `GET /api/v1/projects/{project_id}/quota-view`

对照边界 **§2.14** 项目级配额视图。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess。不允许 Tok。
   - 角色：该项目四角色可读。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**

```yaml
ProjectQuotaView:
  type: object
  required: [project_id, org_quota_version, view]
  properties:
    project_id: { $ref: '#/UUID' }
    org_quota_version: { $ref: '#/Version' }
    view:
      type: object
      description: |
        项目级视图，数据源仍是 OrgQuota（组织一行账本）。
        是否按项目拆分占用：口径 TBD，未批不得发明项目级独立账本对象。
      properties:
        token_consumed_in_project:
          type: number
          description: 本项目 AIInvocationLog 确认消耗投影；口径 TBD
        executor_slots_in_use_in_project:
          type: integer
          nullable: true
          description: TBD
        perf_concurrency_in_use_in_project:
          type: integer
          nullable: true
          description: TBD
        org_remaining:
          $ref: '#/OrgQuotaCurrent'
          description: 组织余量摘要，避免前端本地相减
```

5. **成功判定**：同 **§6-15**。项目视图不得被前端加总成「组织已超限」的独立结论；超限判定只在命令路径。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：返回 `org_quota_version`（组织账本）。项目无独立配额聚合版本。

---

#### API-019 `GET /api/v1/projects/{project_id}/notification-subscriptions`

对照边界 **§2.14** / G4（站内形态 TBD）。订阅是**配置投影**，不是第 24 领域对象。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess。不允许 Tok。
   - 角色：该项目四角色可读；写（API-029）限 `owner` / `admin`（本 GET 不写）。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**

```yaml
NotificationSubscriptionView:
  type: object
  required: [project_id, version, channels, categories]
  properties:
    project_id: { $ref: '#/UUID' }
    version:
      type: integer
      description: 订阅配置 CAS；若落在项目聚合则与项目 version 合一——精确资源 TBD
    channels:
      type: array
      description: 渠道偏好；主备与投递在连接器。渠道类型枚举 TBD（G4）
      items:
        type: object
        required: [channel_id, enabled]
        properties:
          channel_id: { type: string }
          enabled: { type: boolean }
          connector_id: { $ref: '#/UUID' }
          is_primary: { type: boolean }
    categories:
      type: array
      description: |
        订阅的通知类别偏好。类别对齐 02_api §16.1 覆盖面，穷举 TBD，不得发明领域对象。
      items:
        type: object
        required: [category, enabled]
        properties:
          category: { type: string }
          enabled: { type: boolean }
```

5. **成功判定**：返回当前订阅偏好快照。通知**是否已投递**不以本接口为准（投递在集成中心）。G4 产品形态未冻结，本契约只保证可查询偏好。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：配置可变，返回 `version`（精确挂载 TBD）。

---

### 7.4 工作台、通知、审计、证据（读）

#### API-020 `GET /api/v1/workbench`

对照边界 **§2.13** 工作台四组件；裁定 5：等待态持续可见。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess。不允许 Tok。
   - 角色：任一租户成员。卡片内容按调用方角色与项目成员过滤（只看自己可感知的审批 / run / 项目）。
2. **同步性**：同步查询。
3. **Query params**

```yaml
parameters:
  - name: project_id
    in: query
    schema: { type: string, format: uuid }
    description: 可选；收窄到单项目。省略 = 用户全部有权项目聚合
```

无分页（聚合卡片；单卡内部条数上限 TBD）。URL 筛选由前端持有，本 API 只认 `project_id`。

4. **Response YAML**

```yaml
Workbench:
  type: object
  required: [pending_approvals, active_runs, gate_anomalies, quota]
  properties:
    pending_approvals:
      type: array
      items:
        type: object
        required: [id, action_type, status, expires_at, initiator_id]
        properties:
          id: { $ref: '#/UUID' }
          action_type:
            type: string
            enum:
              - jira_write
              - heal_apply
              - perf_high_risk
              - release_push
              - env_register
              - agent_tool_action
              - gate_waiver
              - kill_switch_restore
          status:
            type: string
            enum: [CREATED, PENDING]
            description: 工作台待办仅未决态；EXPIRED 走通知/高亮但不算「待我处理」——精确过滤 TBD
          expires_at: { type: string, format: date-time }
          escalate_to: { $ref: '#/UUID' }
          is_expiring:
            type: boolean
            description: 临期投影；阈值 TBD
          initiator_id: { $ref: '#/UUID' }
          target_object_type: { type: string }
          target_object_id: { $ref: '#/UUID' }
          version: { $ref: '#/Version' }
    active_runs:
      type: array
      description: |
        非终态 TestRun，必须包含 WAITING_APPROVAL / WAITING_EXTERNAL。
        等待态必须带 dwell_seconds；禁止因长时间等待隐藏。
      items:
        type: object
        required: [id, status, project_id, version]
        properties:
          id: { $ref: '#/UUID' }
          project_id: { $ref: '#/UUID' }
          status: { $ref: '#/TestRunStatus' }
          execution_source:
            type: string
            enum: [script, agent, external_ci]
          version: { $ref: '#/Version' }
          dwell_seconds:
            type: integer
            minimum: 0
            description: |
              status ∈ {WAITING_APPROVAL, WAITING_EXTERNAL} 时必填。
              其他非终态可省略或同口径（进入当前态起算）TBD。
          last_heartbeat_at:
            type: string
            format: date-time
            nullable: true
            description: 仅活跃态有意义；等待态不适用心跳治理
    gate_anomalies:
      type: array
      items:
        type: object
        required: [kind]
        properties:
          kind:
            type: string
            description: fail_evaluation | unevaluated | check_run_failed 等；精确集合 TBD
          test_run_id: { $ref: '#/UUID' }
          gate_evaluation_id:
            type: string
            format: uuid
            nullable: true
          result:
            allOf: [{ $ref: '#/GateEvaluationResult' }]
            nullable: true
            description: 有评估行时；无行则为 null（配合 unevaluated_reason）
          unevaluated_reason:
            allOf: [{ $ref: '#/UnevaluatedReason' }]
            nullable: true
    quota:
      description: 组织预算余量摘要，形状同 OrgQuotaCurrent 子集
      $ref: '#/OrgQuotaCurrent'
```

5. **成功判定**：四类数据源以后端聚合为准（边界 §3.1-6）。等待态可见性是成功条件的一部分：缺少 `dwell_seconds` 的 `WAITING_*` 视为契约不合格。本接口不是审批 / 执行完成判定。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`（非法 project_id 不可感知）、`HT-VAL-001`、`HT-INT-001`。
7. **version**：审批与 TestRun 项带 `version`；配额带账本 `version`。工作台本身无聚合版本。

---

#### API-021 `GET /api/v1/notifications`

对照边界 **§5.1 类 7**、`02_api` §16.1。通知是**查询投影**，**不是**第 24 个领域对象。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess。不允许 Tok。
   - 角色：仅返回**当前用户**收件箱投影。四角色均可读自己的通知。
2. **同步性**：同步查询。
3. **Query params**

```yaml
parameters:
  - { name: cursor, in: query, schema: { type: string } }
  - { name: limit, in: query, schema: { type: integer, minimum: 1 } }
  - name: read
    in: query
    schema: { type: boolean }
    description: 按已读/未读筛选；省略 = 全部
  - name: category
    in: query
    schema: { type: string }
    description: 单类别；穷举 TBD
  - name: project_id
    in: query
    schema: { type: string, format: uuid }
```

4. **Response YAML**

```yaml
NotificationProjection:
  type: object
  required: [id, category, created_at, read, title]
  properties:
    id:
      type: string
      format: uuid
      description: 投影行 ID（传输协调面）；不是第 24 对象主键语义以外的领域 ID
    category:
      type: string
      description: |
        对齐 02_api §16.1 覆盖：审批创建/临期/升级/批准/拒绝/过期/执行失败、
        WAITING_* 滞留、用例失效、Check Run 回写失败、Release/连接器失败、
        AI/平台降级、预算超限、导入导出/解析完成或 partial/failed。
        精确枚举 TBD（G4），不得发明新领域对象或新状态机。
    created_at: { type: string, format: date-time }
    read: { type: boolean }
    title: { type: string }
    resource_type: { type: string, nullable: true }
    resource_id:
      type: string
      format: uuid
      nullable: true
    project_id:
      type: string
      format: uuid
      nullable: true
```

外壳：`ListEnvelope`。无 Prompt、无 secret。

5. **成功判定**：列表是展示用投影。已读状态以本查询（及标已读命令之后的再 GET）为准。通知产生与投递均在后端（边界 §4.1-15）；空列表 ≠ 投递失败。
6. **错误码**：`HT-AUTH-001`、`HT-VAL-001`、`HT-RES-001`（project 不可感知）、`HT-INT-001`。
7. **version**：投影可变（已读），**不**使用领域 CAS `version`。对账用 `id` + `read` + `created_at`。

---

#### API-022 `GET /api/v1/notifications/badge`

1. **鉴权 / 角色 / Token scope**：同 API-021（Sess；当前用户）。
2. **同步性**：同步查询。
3. **Query params**：可选 `project_id`（语义同 API-021）。无分页。
4. **Response YAML**

```yaml
NotificationBadge:
  type: object
  required: [unread_count]
  properties:
    unread_count:
      type: integer
      minimum: 0
      description: 当前用户未读投影计数；口径（是否含已过期审批类）TBD
```

5. **成功判定**：角标数字以后端计数为准，前端不得用列表长度本地推算后当作权威（可作乐观，冲突以本 GET 为准）。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：无。计数对账以本响应为准。

---

#### API-024 `GET /api/v1/audit-events`

对照边界 **§2.13** 审计检索。**append-only，仅 GET**（无 PATCH）。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess。不允许 Tok。
   - 角色：fail-close —— `owner` / `admin` 可检索组织审计；`tester` / `viewer` → `HT-IAM-001`（精确矩阵未另批）。跨租户不得泄露。
2. **同步性**：同步查询。
3. **Query params**

```yaml
parameters:
  - { name: cursor, in: query, schema: { type: string } }
  - { name: limit, in: query, schema: { type: integer, minimum: 1 } }
  - name: actor_user_id
    in: query
    schema: { type: string, format: uuid }
  - name: request_hash
    in: query
    schema: { type: string }
  - name: approval_id
    in: query
    schema: { type: string, format: uuid }
  - name: approval_bound_hash
    in: query
    schema: { type: string }
  - name: resource_type
    in: query
    schema: { type: string }
  - name: resource_id
    in: query
    schema: { type: string, format: uuid }
  - name: project_id
    in: query
    schema: { type: string, format: uuid }
  - name: external_request_id
    in: query
    schema: { type: string }
  - name: created_from
    in: query
    schema: { type: string, format: date-time }
  - name: created_to
    in: query
    schema: { type: string, format: date-time }
  - name: sort
    in: query
    schema: { type: string, description: 仅 created_at；默认 desc。白名单 TBD }
```

禁止把 Prompt、payload 秘密当筛选器。

4. **Response YAML**

```yaml
AuditEventListItem:
  allOf:
    - $ref: '#/AppendOnlyMeta'
    - type: object
      required: [data_classification]
      properties:
        project_id: { $ref: '#/UUID' }
        actor_user_id: { $ref: '#/UUID' }
        delegated_agent: { type: string, nullable: true }
        workflow: { type: string, nullable: true }
        step: { type: string, nullable: true }
        skill_id: { $ref: '#/UUID' }
        skill_version_id: { $ref: '#/UUID' }
        model: { type: string, nullable: true }
        provider: { type: string, nullable: true }
        prompt_version:
          type: string
          nullable: true
          description: 版本标识；禁止 Prompt 正文
        tool: { type: string, nullable: true }
        action: { type: string, nullable: true }
        resource_type: { type: string, nullable: true }
        resource_id: { $ref: '#/UUID' }
        request_hash: { type: string, nullable: true }
        response_hash: { type: string, nullable: true }
        approval_id: { $ref: '#/UUID' }
        approval_decision: { type: string, nullable: true }
        approval_bound_hash: { type: string, nullable: true }
        data_classification: { $ref: '#/DataClassification' }
        external_request_id: { type: string, nullable: true }
        result:
          type: string
          nullable: true
          description: 审计结果摘要码，非秘密正文
        evidence_refs:
          type: array
          items: { $ref: '#/UUID' }
        cost: { type: number, nullable: true }
        latency_ms: { type: integer, nullable: true }
        payload_ref:
          type: string
          nullable: true
          description: 稳定 object_key；禁止 secret / Restricted 明文
```

外壳：`ListEnvelope`。无 `updated_at`、无 CAS `version`。

5. **成功判定**：检索结果以后端为准（边界 §3.1-10）。空集 = 无匹配，不是权限失败（权限失败走错误外壳）。失败操作也必须能被检索到（若调用方有权）。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-001`、`HT-RES-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：无（append-only）。对账用 `id` + `created_at` + `request_hash`。

---

#### API-025 `GET /api/v1/audit-events/{audit_event_id}`

1. **鉴权 / 角色 / Token scope**：同 API-024。跨租户 → `HT-RES-001`。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**：`ResourceEnvelope.data` = `AuditEventListItem` 全量可对外字段。仍禁止：Prompt 正文、密钥、Restricted 明文、把 `payload_ref` 解包为秘密。
5. **成功判定**：单条不可变事件快照。不存在覆盖语义。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：无。

---

#### API-026 `GET /api/v1/evidence-objects`

对照边界 **§2.13** 证据中心。**append-only，仅 GET**。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess。不允许 Tok。
   - 角色：该证据 `subject` 所属项目的四角色可读；组织级无项目主体的证据限 `owner` / `admin`（精确矩阵 TBD，冲突 fail-close）。Restricted 分类：元数据可返回 `data_classification`，**正文不在本接口**。
2. **同步性**：同步查询。
3. **Query params**

```yaml
parameters:
  - { name: cursor, in: query, schema: { type: string } }
  - { name: limit, in: query, schema: { type: integer, minimum: 1 } }
  - name: subject_type
    in: query
    required: false
    schema:
      type: string
      description: test_run / case_result / failure_cluster / gate_evaluation / release_task / ai_invocation 等 [建模补全]
  - name: subject_id
    in: query
    schema: { type: string, format: uuid }
  - name: created_from
    in: query
    schema: { type: string, format: date-time }
  - name: created_to
    in: query
    schema: { type: string, format: date-time }
```

`subject_id` 与 `subject_type` 宜成对出现；不成对 → `HT-VAL-001` 或忽略其一（TBD，建议成对校验）。

4. **Response YAML**

```yaml
EvidenceObjectListItem:
  allOf:
    - $ref: '#/AppendOnlyMeta'
    - type: object
      required: [claim, source_object, subject_type, subject_id, data_classification]
      properties:
        claim:
          type: string
          description: Confidential 最小化（结论陈述）
        source_object:
          type: object
          required: [connector, resource, timestamp]
          description: 稳定来源，禁止预签名 URL
          properties:
            connector: { type: string }
            resource: { type: string }
            version: { type: string }
            timestamp: { type: string, format: date-time }
        content_ref:
          type: string
          nullable: true
          description: 稳定 object_key；引用≠授权；禁止预签名 URL
        subject_type: { type: string }
        subject_id: { $ref: '#/UUID' }
        data_classification: { $ref: '#/DataClassification' }
```

外壳：`ListEnvelope`。

5. **成功判定**：检索以后端为准。`content_ref` / `object_key` **不是**下载令牌（G5）。Restricted 不得在本响应出现明文正文。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-001`、`HT-RES-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：无（不可变）。

---

#### API-027 `GET /api/v1/evidence-objects/{evidence_object_id}`

1. **鉴权 / 角色 / Token scope**：同 API-026。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**：`ResourceEnvelope.data` = `EvidenceObjectListItem`。仍禁止预签名 URL、secret、Prompt、Restricted 明文。
5. **成功判定**：单条不可变证据。访问仍须 tenant / RBAC；有 ID ≠ 已授权看正文。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：无。

---

### 7.5 TestCase（读）

#### API-030 `GET /api/v1/test-cases`

对照边界 **§2.2** 用例库浏览 / 筛选。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess。不允许 Tok。
   - 角色：目标项目四角色可读。
2. **同步性**：同步查询。
3. **Query params**

```yaml
parameters:
  - name: project_id
    in: query
    required: true
    schema: { type: string, format: uuid }
  - { name: cursor, in: query, schema: { type: string } }
  - { name: limit, in: query, schema: { type: integer, minimum: 1 } }
  - name: lifecycle_status
    in: query
    schema:
      type: string
      enum: [DRAFT, PENDING_REVIEW, ACTIVE, DEPRECATED]
    description: 可重复参数 TBD；单值或多值语义 TBD
  - name: validity
    in: query
    schema: { type: string, enum: [valid, invalid] }
  - name: tags
    in: query
    schema: { type: string }
    description: 含保留标签 ai-generated；多标签匹配规则 TBD
  - name: case_type
    in: query
    schema: { type: string, enum: [api, web, performance, referenced] }
  - name: execution_mode
    in: query
    schema: { type: string, enum: [script, agent] }
  - name: priority
    in: query
    schema: { type: string, enum: [P0, P1, P2, P3] }
  - name: q
    in: query
    schema: { type: string }
    description: 标题搜索；规则 TBD
  - name: sort
    in: query
    schema: { type: string, description: 白名单 TBD（updated_at / title / priority） }
```

URL 筛选是前端本地；本 API 接收上述 query。无「标记失效」写接口（validity 只读）。

4. **Response YAML**

```yaml
TestCaseListItem:
  type: object
  required:
    - id
    - project_id
    - case_type
    - execution_mode
    - title
    - priority
    - tags
    - lifecycle_status
    - validity
    - version
  properties:
    id: { $ref: '#/UUID' }
    project_id: { $ref: '#/UUID' }
    case_type:
      type: string
      enum: [api, web, performance, referenced]
    execution_mode:
      type: string
      enum: [script, agent]
    title: { type: string, description: Confidential 最小化 }
    priority:
      type: string
      enum: [P0, P1, P2, P3]
    tags:
      type: array
      items: { type: string }
    lifecycle_status:
      type: string
      enum: [DRAFT, PENDING_REVIEW, ACTIVE, DEPRECATED]
    validity:
      type: string
      enum: [valid, invalid]
    current_version_id:
      type: string
      format: uuid
      nullable: true
    jira_story_key: { type: string, nullable: true }
    version: { $ref: '#/Version' }
    created_at: { type: string, format: date-time }
    updated_at: { type: string, format: date-time }
```

外壳：`ListEnvelope`。列表不返回 `script_ref` 正文、`job_binding` 密钥、步骤全文。

5. **成功判定**：列表快照。`ai-generated` 以 `tags` 为准（后端打标）。空集 = 无匹配。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`（项目不可感知）、`HT-VAL-001`、`HT-INT-001`。
7. **version**：每项必返（生命周期 / 指针 CAS）。

---

#### API-031 `GET /api/v1/test-cases/{test_case_id}`

对照边界 **§2.2** Web 用例详情：步骤、定位器健康、证据三件套引用。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess。不允许 Tok。
   - 角色：所属项目四角色可读。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**

```yaml
TestCaseDetail:
  type: object
  required:
    - id
    - project_id
    - case_type
    - execution_mode
    - title
    - lifecycle_status
    - validity
    - version
  properties:
    id: { $ref: '#/UUID' }
    project_id: { $ref: '#/UUID' }
    case_type:
      type: string
      enum: [api, web, performance, referenced]
    execution_mode:
      type: string
      enum: [script, agent]
    title: { type: string, description: Confidential 最小化 }
    priority:
      type: string
      enum: [P0, P1, P2, P3]
    tags:
      type: array
      items: { type: string }
    lifecycle_status:
      type: string
      enum: [DRAFT, PENDING_REVIEW, ACTIVE, DEPRECATED]
    validity:
      type: string
      enum: [valid, invalid]
    invalid_reason:
      type: string
      nullable: true
      description: Confidential 最小化；validity=invalid 时
    invalidated_at:
      type: string
      format: date-time
      nullable: true
    jira_story_key: { type: string, nullable: true }
    current_version_id:
      type: string
      format: uuid
      nullable: true
    script_ref:
      type: string
      nullable: true
      description: object_key；referenced 必须 null；引用≠下载授权
    job_binding:
      type: object
      nullable: true
      description: |
        referenced：env_id / job_id / params_schema_ref / collect_config / gate_mapping。
        不含环境凭证。params 中的秘密占位符不得解包为明文。
      properties:
        env_id: { $ref: '#/UUID' }
        job_id: { type: string }
        params_schema_ref: { type: string }
        collect_config: { type: object }
        gate_mapping: { type: object }
    steps:
      type: array
      description: 当前版本快照中的步骤；Confidential 最小化，无秘密参数原文
      items: { type: object }
    locator_health:
      type: array
      description: 定位器主备与健康度投影（来自 Version snapshot，非第 24 对象）
      items:
        type: object
        properties:
          locator_id: { type: string }
          strategy: { type: string }
          is_primary: { type: boolean }
          health:
            type: string
            description: 健康度投影码 TBD，不是新状态机
    evidence_preview:
      type: object
      description: 证据三件套引用（截图/视频/Trace artifact id）；非正文
      properties:
        screenshot_artifact_ids:
          type: array
          items: { $ref: '#/UUID' }
        video_artifact_ids:
          type: array
          items: { $ref: '#/UUID' }
        trace_artifact_ids:
          type: array
          items: { $ref: '#/UUID' }
    version: { $ref: '#/Version' }
    created_at: { type: string, format: date-time }
    updated_at: { type: string, format: date-time }
    created_by: { $ref: '#/UUID' }
```

禁止：环境凭证明文、Prompt、Restricted 正文。

5. **成功判定**：详情以后端当前指针版本为准。`validity` 只读（系统标记）。定位器健康不得由前端 DOM 推演。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：必返；编辑 / 评审 / 废弃 / 回滚命令带 `expected_version`。

---

#### API-037 `GET /api/v1/test-cases/{test_case_id}/versions`

1. **鉴权 / 角色 / Token scope**：同 API-031。
2. **同步性**：同步查询。
3. **Query params**：`cursor`、`limit`；`sort` 仅 `version_seq`（默认 desc）。
4. **Response YAML**

```yaml
TestCaseVersionListItem:
  allOf:
    - $ref: '#/AppendOnlyMeta'
    - type: object
      required: [test_case_id, version_seq, data_classification]
      properties:
        test_case_id: { $ref: '#/UUID' }
        version_seq: { type: integer, minimum: 1 }
        data_classification: { $ref: '#/DataClassification' }
        is_current:
          type: boolean
          description: 是否等于用例 current_version_id（投影）
```

外壳：`ListEnvelope`。列表不返回完整 `snapshot`（Confidential 最小化；详情见 API-038）。Version **禁止覆盖**，无 CAS `version`。

5. **成功判定**：历史以不可变行为准。当前指针以用例 GET 的 `current_version_id` 为准。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：无 CAS。对账用 `id` + `version_seq`。用例指针对账用 API-031 的 `version`。

---

#### API-038 `GET /api/v1/test-cases/{test_case_id}/versions/{version_id}`

1. **鉴权 / 角色 / Token scope**：同 API-031。`version_id` 必须属于该 `test_case_id`，否则 `HT-RES-001`。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**

```yaml
TestCaseVersionSnapshot:
  allOf:
    - $ref: '#/TestCaseVersionListItem'
    - type: object
      required: [snapshot]
      properties:
        snapshot:
          type: object
          description: |
            全量用例快照（含定位器主备等）。Confidential 最小化；
            脱敏后返回；禁止秘密参数原文、凭证、Prompt。
```

5. **成功判定**：不可变快照。heal_apply 成功条件是**新** Version + 指针（§6-12），本 GET 只读历史。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：无 CAS。

---

### 7.6 TestPlan 与 PerfBaseline（读）

#### API-050 `GET /api/v1/test-plans`

对照边界 **§2.14**。

1. **鉴权 / 角色 / Token scope**：Sess；项目四角色。不允许 Tok。
2. **同步性**：同步查询。
3. **Query params**：必填 `project_id`；`cursor`、`limit`；可选 `q`（名称）；`sort` TBD。
4. **Response YAML**

```yaml
TestPlanListItem:
  type: object
  required: [id, project_id, name, version]
  properties:
    id: { $ref: '#/UUID' }
    project_id: { $ref: '#/UUID' }
    name: { type: string, description: Confidential 最小化 }
    jira_fix_version: { type: string, nullable: true }
    case_count:
      type: integer
      description: 选用用例数投影
    version: { $ref: '#/Version' }
    created_at: { type: string, format: date-time }
    updated_at: { type: string, format: date-time }
```

外壳：`ListEnvelope`。

5. **成功判定**：计划列表快照。无问题模型状态机。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：必返（编排 CAS）。

---

#### API-051 `GET /api/v1/test-plans/{test_plan_id}`

对照边界 **§2.14** 计划详情 + 报告聚合。

1. **鉴权 / 角色 / Token scope**：同 API-050。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**

```yaml
TestPlanDetail:
  type: object
  required: [id, project_id, name, version, case_ids]
  properties:
    id: { $ref: '#/UUID' }
    project_id: { $ref: '#/UUID' }
    name: { type: string, description: Confidential 最小化 }
    jira_fix_version: { type: string, nullable: true }
    case_ids:
      type: array
      items: { $ref: '#/UUID' }
    schedule:
      type: object
      nullable: true
      description: 定时回归绑定；字段 TBD（cron 表达式等未批）
    report_aggregate:
      type: object
      description: |
        计划级报告聚合（FR-15 证据汇聚输入）。前端不得自行汇总。
        指标口径 TBD。
      properties:
        last_run_id: { $ref: '#/UUID' }
        last_run_status: { $ref: '#/TestRunStatus' }
        pass_rate: { type: number, nullable: true }
        gate_result:
          allOf: [{ $ref: '#/GateEvaluationResult' }]
          nullable: true
    version: { $ref: '#/Version' }
    created_at: { type: string, format: date-time }
    updated_at: { type: string, format: date-time }
    created_by: { $ref: '#/UUID' }
```

5. **成功判定**：编排与聚合以后端为准。计划报告 ≠ TestRun 终态权威（终态仍以 run GET / §6-5）。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：必返。

---

#### API-056 `GET /api/v1/perf-baselines`

对照边界 **§2.10**。

1. **鉴权 / 角色 / Token scope**：Sess；项目四角色。不允许 Tok。
2. **同步性**：同步查询。
3. **Query params**：必填 `project_id`；可选 `scenario_test_case_id`、`is_active`；`cursor`、`limit`。
4. **Response YAML**

```yaml
PerfBaselineListItem:
  type: object
  required: [id, scenario_test_case_id, is_active, version]
  properties:
    id: { $ref: '#/UUID' }
    scenario_test_case_id: { $ref: '#/UUID' }
    is_active: { type: boolean }
    tolerance:
      type: object
      description: RT/TPS 等；Internal
    version: { $ref: '#/Version' }
    created_at: { type: string, format: date-time }
    updated_at: { type: string, format: date-time }
```

外壳：`ListEnvelope`。列表可不返回完整 `metrics_snapshot`（详情 API-059）。

5. **成功判定**：同场景唯一活跃以 `is_active` 为准（后端 CAS）。前端不得把对比图本地拟合当成基线事实。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：必返（活跃切换 CAS）。历史 `metrics_snapshot` 不可改写。

---

#### API-059 `GET /api/v1/perf-baselines/{perf_baseline_id}`

1. **鉴权 / 角色 / Token scope**：同 API-056。
2. **同步性**：同步查询。
3. **Query params**：可选 `compare_with_run_id`（UUID）——对比数据由后端供给，前端不计算。
4. **Response YAML**

```yaml
PerfBaselineDetail:
  allOf:
    - $ref: '#/PerfBaselineListItem'
    - type: object
      required: [metrics_snapshot]
      properties:
        metrics_snapshot:
          type: object
          description: Confidential；创建后不可变；脱敏后返回
        comparison:
          type: object
          nullable: true
          description: 与指定 TestRun 的对比投影；口径 TBD
          properties:
            test_run_id: { $ref: '#/UUID' }
            deltas: { type: object }
```

5. **成功判定**：基线数据与对比结果以后端为准（§2.10）。压测发起成功仍以 TestRun 创建 / 终态另判。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-VAL-001`（compare 指向不可感知 run）、`HT-INT-001`。
7. **version**：必返。

---

### 7.7 TestRun 查询、选项、回执（读）

#### API-060 `GET /api/v1/test-runs`

对照边界 **§2.4** 列表；裁定 5 等待态可见。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess **或** Tok `read`。
   - 角色（Sess）：项目四角色。
   - Tok：`scopes` 含 `read`；`project_id` ∈ `project_ids` 白名单，否则 `HT-IAM-005`。空 `project_ids` 语义 TBD（禁止默认全部项目）。
2. **同步性**：同步查询。
3. **Query params**

```yaml
parameters:
  - name: project_id
    in: query
    required: true
    schema: { type: string, format: uuid }
  - { name: cursor, in: query, schema: { type: string } }
  - { name: limit, in: query, schema: { type: integer, minimum: 1 } }
  - name: status
    in: query
    schema: { $ref: '#/TestRunStatus' }
    description: 可重复 TBD
  - name: execution_source
    in: query
    schema: { type: string, enum: [script, agent, external_ci] }
  - name: trigger_type
    in: query
    schema: { type: string, enum: [manual, schedule, ci_webhook, api_token] }
  - name: plan_id
    in: query
    schema: { type: string, format: uuid }
  - name: env_id
    in: query
    schema: { type: string, format: uuid }
  - name: include_waiting
    in: query
    schema: { type: boolean }
    description: |
      默认 true。若 false，仍不得把 WAITING_* 从「进行中」产品语义中抹掉——
      本参数仅允许显式排除；工作台 API-020 忽略本参数且必须包含等待态。
  - name: sort
    in: query
    schema: { type: string, description: 默认 created_at desc；白名单 TBD }
```

4. **Response YAML**

```yaml
TestRunListItem:
  type: object
  required:
    - id
    - project_id
    - env_id
    - execution_source
    - trigger_type
    - status
    - version
  properties:
    id: { $ref: '#/UUID' }
    project_id: { $ref: '#/UUID' }
    plan_id: { $ref: '#/UUID' }
    env_id: { $ref: '#/UUID' }
    execution_source:
      type: string
      enum: [script, agent, external_ci]
    trigger_type:
      type: string
      enum: [manual, schedule, ci_webhook, api_token]
    status: { $ref: '#/TestRunStatus' }
    gate_evaluation_id:
      type: string
      format: uuid
      nullable: true
      description: agent 恒为 null
    version: { $ref: '#/Version' }
    dwell_seconds:
      type: integer
      minimum: 0
      description: status ∈ {WAITING_APPROVAL, WAITING_EXTERNAL} 时必填
    created_at: { type: string, format: date-time }
    updated_at: { type: string, format: date-time }
```

外壳：`ListEnvelope`。不返回完整 `snapshot`、报告原文、凭证明文。

5. **成功判定**：列表只读。终态判定 **§6-5** 不在本列表完成（须详情 / 后续 GET）。WAITING_* 缺 `dwell_seconds` 视为契约不合格。网络失败 ≠ 空列表。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-003`、`HT-IAM-004`、`HT-IAM-005`、`HT-RES-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：每项必返。

---

#### API-061 `GET /api/v1/test-runs/{test_run_id}`

对照边界 **§2.4** 详情；**§6-5** 终态。

1. **鉴权 / 角色 / Token scope**：同 API-060（Sess 或 Tok `read`）。
2. **同步性**：同步查询。
3. **Query params**：无。SSE 进度不是本接口（API-210）。
4. **Response YAML**

```yaml
TestRunDetail:
  allOf:
    - $ref: '#/TestRunListItem'
    - type: object
      required: [snapshot_summary]
      properties:
        snapshot_summary:
          type: object
          description: |
            受理后不可变快照的对外摘要（用例版本 / 环境 / 非秘密参数）。
            Confidential 最小化；禁止秘密参数原文与凭证。
          properties:
            case_ids:
              type: array
              items: { $ref: '#/UUID' }
            case_version_ids:
              type: array
              items: { $ref: '#/UUID' }
            env_id: { $ref: '#/UUID' }
            env_config_version: { type: integer }
            params_redacted: { type: object }
        last_heartbeat_at:
          type: string
          format: date-time
          nullable: true
        stop_signal_at:
          type: string
          format: date-time
          nullable: true
          description: 终止信号已持久化（§6-8 受理可见）；不等于 CANCELLED
        result_summary:
          type: object
          nullable: true
          description: 完成/失败摘要与结果引用，不含报告原文
        execution_source_badge:
          type: object
          properties:
            skips_quality_gate:
              type: boolean
              description: agent 为 true（不进门禁）
            normalized_from_external_ci:
              type: boolean
        dwell_seconds:
          type: integer
          minimum: 0
          description: WAITING_* 必填
```

5. **成功判定**
   - **§6-3**：存在且可 GET 证明发起已创建（命令侧）；本接口是对账。
   - **§6-4**：`VALIDATING` 本地表单通过 ≠ 校验成功；失败为 `FAILED` + 结构化原因（在 `result_summary`）。
   - **§6-5**：终态只认 `SUCCEEDED / FAILED / CANCELLED / TIMEOUT`；禁止用 SSE / 进度百分比推定。
   - **§6-8**：`stop_signal_at` 非空 = 信号已持久化，权威完成仍是 `CANCELLED`（经 `STOPPING`）或兜底 `TIMEOUT`。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-003`、`HT-IAM-005`、`HT-RES-001`、`HT-INT-001`。
7. **version**：必返；取消等写命令带 `expected_version`。

---

#### API-064 `GET /api/v1/test-runs/{test_run_id}/case-results`

1. **鉴权 / 角色 / Token scope**：Sess 或 Tok `read`；同 API-060。
2. **同步性**：同步查询。
3. **Query params**：`cursor`、`limit`；可选 `outcome`（值须为已批归一化枚举；当前枚举 **TBD**，非法值 `HT-VAL-001`）；可选 `is_late`、`is_partial`。
4. **Response YAML**

```yaml
CaseResultListItem:
  allOf:
    - $ref: '#/AppendOnlyMeta'
    - type: object
      required:
        - test_run_id
        - test_case_id
        - outcome
        - is_late
        - is_partial
        - data_classification
      properties:
        test_run_id: { $ref: '#/UUID' }
        test_case_id: { $ref: '#/UUID' }
        test_case_version_id: { $ref: '#/UUID' }
        attempt_seq: { type: integer, minimum: 1 }
        outcome: { $ref: '#/CaseResultOutcome' }
        is_late: { type: boolean }
        is_partial: { type: boolean }
        chunk_key: { type: string, nullable: true }
        data_classification: { $ref: '#/DataClassification' }
```

外壳：`ListEnvelope`。列表可不含 `normalized_summary` 全文。迟到结果可追加 attempt，**不重开 run**。无 CAS `version`。

5. **成功判定**：用例结果是执行完成事实，**不是** TestRun 状态机。`is_partial` 必须显式，禁止静默截断。终态仍以 run 为准（§6-5）。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-003`、`HT-RES-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：无（append）。对账用 `id` + `attempt_seq` + `chunk_key`。run 对账用 API-061 `version`。

---

#### API-065 `GET /api/v1/case-results/{case_result_id}`

1. **鉴权 / 角色 / Token scope**：Sess 或 Tok `read`。跨租户 / 无项目权 → `HT-RES-001`。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**

```yaml
CaseResultDetail:
  allOf:
    - $ref: '#/CaseResultListItem'
    - type: object
      properties:
        normalized_summary:
          type: object
          nullable: true
          description: 脱敏后摘要；Confidential 禁缓存；无报告原文 / Prompt / 凭证
        artifact_ids:
          type: array
          items: { $ref: '#/UUID' }
          description: 引用≠授权
```

5. **成功判定**：单条结果事实。`outcome` 与归一化对齐；不得映射成第四套状态。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-003`、`HT-RES-001`、`HT-INT-001`。
7. **version**：无。

---

#### API-066 `GET /api/v1/case-results/{case_result_id}/step-runs`

1. **鉴权 / 角色 / Token scope**：Sess。**默认不允许 Tok**（清单未授权 Tok；冲突 fail-close）。角色：项目四角色。
2. **同步性**：同步查询。
3. **Query params**：`cursor`、`limit`；按 `step_index` 升序。
4. **Response YAML**

```yaml
StepRunItem:
  allOf:
    - $ref: '#/AppendOnlyMeta'
    - type: object
      required: [case_result_id, step_index, is_incomplete]
      properties:
        case_result_id: { $ref: '#/UUID' }
        step_index: { type: integer, minimum: 0 }
        action:
          type: object
          nullable: true
          description: Agent：tool + args_hash；不含秘密参数原文
        observation_ref:
          type: string
          nullable: true
          description: object_key；引用≠授权
        assertion_results:
          type: object
          nullable: true
        token_usage:
          type: object
          nullable: true
          description: Agent 步骤用量；非 Prompt
        is_incomplete: { type: boolean }
```

外壳：`ListEnvelope`。禁止覆盖步骤事实。

5. **成功判定**：步骤只读。Agent 终态 **§6-16** 不由步骤 UI 推定（见 API-067）。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：无。

---

#### API-067 `GET /api/v1/test-runs/{test_run_id}/trajectory`

对照边界 **§2.4** Agent 任务详情；**§6-16**。A8 轨迹存储为 Artifact + CaseResult，非第 24 对象。

1. **鉴权 / 角色 / Token scope**：Sess；项目四角色。不允许 Tok（清单未列）。
2. **同步性**：同步查询。
3. **Query params**：无。非 agent run：返回空轨迹 + 明确标记（见响应），**不**发明新状态。
4. **Response YAML**

```yaml
AgentTrajectory:
  type: object
  required: [test_run_id, available]
  properties:
    test_run_id: { $ref: '#/UUID' }
    available: { type: boolean }
    unavailable_reason:
      type: string
      nullable: true
      description: 如 not_agent_source；不是新领域枚举冻结，TBD
    a8:
      type: object
      nullable: true
      description: ⊆ problem_model A8；脱敏
      properties:
        task_id: { type: string }
        status:
          type: string
          enum: [completed, incomplete, terminated]
          description: A8 轨迹 status，不是 TestRun 10 态
        steps:
          type: array
          items:
            type: object
            properties:
              seq: { type: integer }
              intent: { type: string }
              action:
                type: object
                properties:
                  tool: { type: string }
                  args_hash: { type: string }
              observation_ref: { type: string }
              screenshot_ref: { type: string }
              elapsed_ms: { type: integer }
        assertion_results:
          type: array
          items:
            type: object
            properties:
              expr: { type: string }
              passed: { type: boolean }
        token_usage: { type: object }
        incomplete:
          type: boolean
          description: 超步/超时退出可见
    policy_denials:
      type: array
      items: { type: string }
      description: 拒止记录可见；无秘密
```

禁止：秘密参数原文、凭证、Prompt、未脱敏 Artifact 字节。

5. **成功判定**：边界 **§6-16**：Agent 任务结果权威是后端 A8 `status` + `assertion_results` 以及 **TestRun 终态**（SUCCEEDED / FAILED；超步 / 超时 = incomplete）。前端轨迹呈现 ≠ 终态。`incomplete` 必须可见。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：轨迹本身无 CAS。run 对账用 API-061 `version`。

---

#### API-069 `GET /api/v1/projects/{project_id}/execution-options`

对照边界 **§2.3** 三层配置只读供给。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess。不允许 Tok。
   - 角色：项目四角色可读。发起执行的资格仍在命令侧（viewer 读选项但写被拒）。
2. **同步性**：同步查询。
3. **Query params**：可选 `plan_id`、`execution_source`（`script` / `agent` / `external_ci`）以收窄用例可选性。无分页（选项集；过大时内部截断规则 TBD）。
4. **Response YAML**

```yaml
ExecutionOptions:
  type: object
  required: [project_id, environments, cases]
  properties:
    project_id: { $ref: '#/UUID' }
    environments:
      type: array
      description: |
        默认可选 = ACTIVE 且健康/容量允许。
        非 ACTIVE 不出现在 selectable=true；可另给 unavailable[] 带原因。
      items:
        type: object
        required: [id, name, env_type, status, selectable]
        properties:
          id: { $ref: '#/UUID' }
          name: { type: string, description: Confidential 最小化 }
          env_type:
            type: string
            enum: [platform_executor, external_ci]
          status:
            type: string
            enum: [PENDING_APPROVAL, ACTIVE, DEGRADED, DISABLED]
          selectable: { type: boolean }
          unavailable_reason:
            type: string
            nullable: true
            description: not_active / degraded / no_capacity / combo_unsupported 等 TBD
          health_status:
            type: object
            nullable: true
            properties:
              last_checked_at: { type: string, format: date-time }
              latency_ms: { type: integer }
          capacity:
            type: object
            nullable: true
          credential_present: { $ref: '#/CredentialPresence' }
          version: { $ref: '#/Version' }
    cases:
      type: array
      items:
        type: object
        required: [id, selectable]
        properties:
          id: { $ref: '#/UUID' }
          title: { type: string }
          lifecycle_status:
            type: string
            enum: [DRAFT, PENDING_REVIEW, ACTIVE, DEPRECATED]
          validity:
            type: string
            enum: [valid, invalid]
          execution_mode:
            type: string
            enum: [script, agent]
          selectable: { type: boolean }
          unavailable_reason:
            type: string
            nullable: true
            description: not_active / invalid / mode_mismatch 等
    combo_constraints:
      type: object
      description: Agent × 外部 CI 一期不可用等；前端置灰仅为呈现，受理时后端再拒
      properties:
        agent_times_external_ci_allowed: { type: boolean }
    quota_hint:
      type: object
      description: 容量/配额提示；权威扣减在命令
```

禁止：`credential_ref` 值。

5. **成功判定**：可选环境 / 用例 / Schema 供给成功。**§6-4**：本地动态表单通过 ≠ VALIDATING 成功。非 ACTIVE 环境不可选。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：各环境项带 `version`；本聚合无单一版本。

---

#### API-070 `GET /api/v1/execution-environments/{environment_id}/jobs/{job_id}/params-schema`

对照边界 **§2.3** Job 参数 Schema（P08 动态表单，提示性）。

1. **鉴权 / 角色 / Token scope**：Sess；该环境对调用方项目可见（绑定范围内）的四角色。不允许 Tok。
2. **同步性**：同步查询。
3. **Query params**：无。`environment_id`、`job_id` 为路径参数。
4. **Response YAML**

```yaml
JobParamsSchema:
  type: object
  required: [environment_id, job_id, schema]
  properties:
    environment_id: { $ref: '#/UUID' }
    job_id: { type: string }
    contract_version: { type: integer }
    params_schema_ref: { type: string }
    schema:
      type: object
      description: JSON Schema 对象（或可解析文档）；不含凭证
    supports_cancel: { type: boolean }
```

Job 不存在 → `HT-VAL-002` 或 `HT-RES-001`（存在性：对猜测 job_id 统一不存在 **TBD**，建议 `HT-RES-001` 以免枚举）。

5. **成功判定**：Schema 供前端提示性校验。权威校验在发起执行的 VALIDATING（§6-4 / `HT-VAL-002`）。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-VAL-002`、`HT-INT-001`。
7. **version**：返回 `contract_version`（Job 契约版本，不是环境 CAS；环境 CAS 见 API-101）。

---

#### API-071 `GET /api/v1/command-receipts/{receipt_id}`

操作回执查询（**协议面**，非领域 CRUD，非第 24 对象）。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess **或** Tok（创建该回执的通道；Tok 至少能读回执所属项目）。
   - 角色：回执的 `created_by` 本人，或同项目 `owner` / `admin`。他人 `tester` / `viewer` fail-close `HT-RES-001`（精确矩阵 TBD）。
2. **同步性**：同步查询（回执状态可能仍为 running；完成态以领域 GET 为准）。
3. **Query params**：无。
4. **Response YAML**

```yaml
CommandReceiptView:
  allOf:
    - $ref: '#/CommandReceipt'
    - type: object
      properties:
        poll:
          type: object
          properties:
            path: { type: string }
            sse_path: { type: string }
```

`CommandReceipt` 见 `api_spec.md` §5。禁止在 error.details 中放 Prompt / secret。

5. **成功判定**：回执 `status` 表示命令协议态。**领域完成**以对应资源 GET 为准（例如 TestRun 终态、导入 `failed_items`）。`accepted` ≠ 业务成功（对照 §2.3 受理 vs 完成）。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-003`、`HT-RES-001`、`HT-INT-001`。
7. **version**：回执无领域 CAS。对账用 `id` + `status` + `resource_id`。

---

### 7.8 ExecutionEnvironment（读）

#### API-100 `GET /api/v1/execution-environments`

对照边界 **§2.9**。凭证字段**永不返回**。

1. **鉴权 / 角色 / Token scope**：Sess；组织内对该环境有可见性的成员（组织级环境：任一项目成员；项目级：该项目四角色）。不允许 Tok。
2. **同步性**：同步查询。
3. **Query params**：可选 `project_id`、`env_type`、`status`；`cursor`、`limit`。
4. **Response YAML**

```yaml
ExecutionEnvironmentListItem:
  type: object
  required: [id, env_type, name, status, credential_present, version]
  properties:
    id: { $ref: '#/UUID' }
    env_type:
      type: string
      enum: [platform_executor, external_ci]
    name: { type: string, description: Confidential 最小化 }
    endpoint:
      type: string
      nullable: true
      description: 非密钥；Confidential 最小化
    status:
      type: string
      enum: [PENDING_APPROVAL, ACTIVE, DEGRADED, DISABLED]
    scope_level:
      type: string
      enum: [organization, project]
    credential_present: { $ref: '#/CredentialPresence' }
    version: { $ref: '#/Version' }
    created_at: { type: string, format: date-time }
    updated_at: { type: string, format: date-time }
```

禁止：`credential_ref` 值、`standing_auth_metadata` 当永久豁免返回。Proposed 占位字段不作为当前默认对外语义。

5. **成功判定**：列表快照。DEGRADED / DISABLED 只挡新发起，本列表仍返回这些环境（发起侧用 API-069 过滤可选）。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：必返。

---

#### API-101 `GET /api/v1/execution-environments/{environment_id}`

1. **鉴权 / 角色 / Token scope**：同 API-100。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**

```yaml
ExecutionEnvironmentDetail:
  allOf:
    - $ref: '#/ExecutionEnvironmentListItem'
    - type: object
      properties:
        health_status:
          type: object
          nullable: true
          properties:
            last_checked_at: { type: string, format: date-time }
            latency_ms: { type: integer }
            ok: { type: boolean }
        capacity:
          type: object
          nullable: true
        config_version: { type: integer }
```

`credential_present: boolean`（清单用语 `credential_present`；与骨架 `has_credential` 同义，对外统一 **`credential_present`**）。永不返回 `credential_ref` 值。

5. **成功判定**：详情。ACTIVE 仅当 `env_register` 审批 `EXECUTED + execution_result=ok`（§2.9）；本 GET 反映当前态，不是注册命令成功。健康写入仍系统内部。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：必返；停用等命令带 `expected_version`。

---

#### API-104 `GET /api/v1/execution-environments/{environment_id}/jobs`

Job Registry。

1. **鉴权 / 角色 / Token scope**：同 API-100。
2. **同步性**：同步查询。
3. **Query params**：`cursor`、`limit`；可选 `q`（job_id）。
4. **Response YAML**

```yaml
JobContractListItem:
  type: object
  required: [job_id, supports_cancel, contract_version]
  properties:
    job_id: { type: string }
    params_schema_ref: { type: string, nullable: true }
    report_adapter: { type: string, nullable: true }
    supports_cancel: { type: boolean }
    contract_version: { type: integer }
    artifact_manifest:
      type: object
      nullable: true
      description: Confidential 最小化；无秘密
```

外壳：`ListEnvelope`。

5. **成功判定**：Registry 快照。Job 被外部删除导致用例 `validity=invalid` 由系统标记，本列表缺 job ≠ 前端自行改 validity。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：契约用 `contract_version`；环境 CAS 见 API-101。

---

#### API-105 `GET /api/v1/execution-environments/{environment_id}/health`

健康**投影**（写入仍系统内部）。

1. **鉴权 / 角色 / Token scope**：同 API-100。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**

```yaml
EnvironmentHealthProjection:
  type: object
  required: [environment_id, status]
  properties:
    environment_id: { $ref: '#/UUID' }
    status:
      type: string
      enum: [PENDING_APPROVAL, ACTIVE, DEGRADED, DISABLED]
    health_status:
      type: object
      nullable: true
      properties:
        last_checked_at: { type: string, format: date-time }
        latency_ms: { type: integer }
        ok: { type: boolean }
    environment_version: { $ref: '#/Version' }
```

5. **成功判定**：探活结果以后端为准（§3.1-6）。前端不得因一次慢请求把环境标 DISABLED。在途 run 不因 DEGRADED 中断（问题模型）。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：返回 `environment_version` 供对账。健康 jsonb 本身无独立 CAS。

---

### 7.9 审批（读）

#### API-110 `GET /api/v1/approval-requests`

对照边界 **§2.5** 队列 + 九要素。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess。不允许 Tok（Token 不能替代审批）。
   - 角色：`owner` / `admin` 看组织/项目队列；`tester` 可看自己发起的；`viewer` 只读其项目内队列（无批准权）。候选审批人视角用 query `perspective=approver`。
2. **同步性**：同步查询。
3. **Query params**

```yaml
parameters:
  - { name: cursor, in: query, schema: { type: string } }
  - { name: limit, in: query, schema: { type: integer, minimum: 1 } }
  - name: status
    in: query
    schema:
      type: string
      enum: [CREATED, PENDING, APPROVED, EXECUTED, REJECTED, EXPIRED]
  - name: action_type
    in: query
    schema:
      type: string
      enum:
        - jira_write
        - heal_apply
        - perf_high_risk
        - release_push
        - env_register
        - agent_tool_action
        - gate_waiver
        - kill_switch_restore
  - name: perspective
    in: query
    schema: { type: string, enum: [inbox, initiated, all] }
    description: inbox=待我处理；精确过滤 TBD
  - name: project_id
    in: query
    schema: { type: string, format: uuid }
  - name: target_object_id
    in: query
    schema: { type: string, format: uuid }
```

4. **Response YAML**

```yaml
ApprovalRequestListItem:
  type: object
  required:
    - id
    - action_type
    - target_object_type
    - target_object_id
    - param_hash
    - card_payload
    - status
    - initiator_id
    - expires_at
    - side_effect_level
    - version
  properties:
    id: { $ref: '#/UUID' }
    action_type:
      type: string
      enum:
        - jira_write
        - heal_apply
        - perf_high_risk
        - release_push
        - env_register
        - agent_tool_action
        - gate_waiver
        - kill_switch_restore
    target_object_type: { type: string }
    target_object_id: { $ref: '#/UUID' }
    param_hash: { type: string }
    card_payload:
      type: object
      description: |
        服务端组装九要素：动作、资源、diff、数据来源、模型与 Skill 版本、
        风险等级、成本估计、回滚能力、参数哈希。前端不计算 param_hash。
        Confidential 最小化；无秘密正文。
    status:
      type: string
      enum: [CREATED, PENDING, APPROVED, EXECUTED, REJECTED, EXPIRED]
    execution_result:
      type: string
      nullable: true
      enum: [ok, failed, unknown]
      description: 仅 EXECUTED 非空
    initiator_id: { $ref: '#/UUID' }
    approver_id: { $ref: '#/UUID' }
    expires_at: { type: string, format: date-time }
    escalate_to: { $ref: '#/UUID' }
    expired_reason:
      type: string
      nullable: true
      enum: [ttl, withdrawn, invalidated]
    origin_request_id: { $ref: '#/UUID' }
    side_effect_level:
      type: string
      enum: [L0, L1, L2, L3, L4]
    four_eyes_self:
      type: boolean
      description: 调用方是否为发起人（呈现置灰）；权威四眼在写命令
    version: { $ref: '#/Version' }
    created_at: { type: string, format: date-time }
    updated_at: { type: string, format: date-time }
```

外壳：`ListEnvelope`。`copilot_write` **不**列入当前 enum（M4 预留，未启用）。

5. **成功判定**：队列只读。**§6-6** 批准成功不在本 GET 判定（写命令后资源为 `APPROVED`）。`unknown` 必须可查询（本列表 / 详情）。EXPIRED 不自动放行关联 TestRun（仍 `WAITING_APPROVAL`）。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-001`、`HT-RES-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：必返。

---

#### API-111 `GET /api/v1/approval-requests/{approval_request_id}`

1. **鉴权 / 角色 / Token scope**：同 API-110。不可感知 → `HT-RES-001`。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**

```yaml
ApprovalRequestDetail:
  allOf:
    - $ref: '#/ApprovalRequestListItem'
    - type: object
      properties:
        action_payload_redacted:
          type: object
          description: 参数脱敏投影；消费前仍以服务端重算 hash 为准；禁缓存
        snapshot_ref:
          type: string
          nullable: true
          description: 自愈应用前快照 object_key 或 Version ID；非预签名 URL
        original_initiator_id: { $ref: '#/UUID' }
        execution_reconciliation:
          type: object
          nullable: true
          description: execution_result=unknown 时的对账提示；禁止当失败盲重试
          properties:
            needed: { type: boolean }
            external_request_id: { type: string, nullable: true }
```

不返回 execution intent 基础设施状态机（非对外资源）。

5. **成功判定**
   - **§6-6**：详情 `status=APPROVED` ≠ 执行成功。
   - 执行成功另判：`EXECUTED` + `execution_result=ok`。
   - `unknown`：必须可查询并对账（§6 / 架构）；禁止当成功放行。
   - **§6-7** 外部写：issue 链接等在 EXECUTED+ok 后的资源 / Evidence 上回显，本卡片可含投影。
   - **§6-13** 豁免：`gate_waiver` 以本资源 EXECUTED + 豁免记录可查为准。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：必返；决策命令带 `expected_version`。

---

### 7.10 失败分诊（读）

#### API-130 `GET /api/v1/test-runs/{test_run_id}/failure-clusters`

对照边界 **§2.6** 聚类报告查看。

1. **鉴权 / 角色 / Token scope**：Sess；项目四角色。不允许 Tok。
2. **同步性**：同步查询。报告可能仍生成中：返回已有簇 + `generation_status` 投影（不是新领域对象）。
3. **Query params**：`cursor`、`limit`；可选 `category`（7 值枚举）。
4. **Response YAML**

```yaml
FailureClusterReport:
  type: object
  required: [test_run_id, items, unclustered_refs]
  properties:
    test_run_id: { $ref: '#/UUID' }
    generation_status:
      type: string
      description: pending / ready / degraded；精确值 TBD，不是 TestRun 状态机
    degraded:
      type: boolean
      description: 规则聚类 fallback（confidence 0.3、AIInvocationLog result=degraded）
    unclustered_refs:
      type: array
      items: { $ref: '#/UUID' }
      description: 未能聚类的 CaseResult ID；必须显式
    items:
      type: array
      items: { $ref: '#/FailureClusterListItem' }
    page: { $ref: '#/Page' }

FailureClusterListItem:
  type: object
  required:
    - id
    - test_run_id
    - category
    - confidence
    - blocking_judgment
    - evidence_refs
    - failure_refs
  properties:
    id: { $ref: '#/UUID' }
    test_run_id: { $ref: '#/UUID' }
    category:
      type: string
      enum:
        - env_down
        - auth_expired
        - locator_stale
        - assertion_real_bug
        - flaky
        - data_issue
        - unknown
    root_cause:
      type: string
      nullable: true
      description: Confidential 最小化
    confidence: { type: number }
    blocking_judgment:
      type: string
      enum: [blocker, non_blocker, uncertain]
    evidence_refs:
      type: array
      items: { $ref: '#/UUID' }
    failure_refs:
      type: array
      items: { $ref: '#/UUID' }
    created_at: { type: string, format: date-time }
```

簇随 run 只读生成，无生命周期状态机、无 CAS `version`。`unknown` 兜底，不包装。

5. **成功判定**：报告数据以后端为准（§3.1-5）。本地未提交修正不出现在本响应。`unclustered_refs` 必须可点开（返回 ID）。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：无。修正留痕见详情 `correction_history`。

---

#### API-131 `GET /api/v1/failure-clusters/{failure_cluster_id}`

1. **鉴权 / 角色 / Token scope**：同 API-130。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**

```yaml
FailureClusterDetail:
  allOf:
    - $ref: '#/FailureClusterListItem'
    - type: object
      required: [correction_history]
      properties:
        correction_history:
          type: array
          description: 只追加；[{actor, field, old, new, timestamp}]
          items:
            type: object
            required: [actor, field, old, new, timestamp]
            properties:
              actor: { $ref: '#/UUID' }
              field: { type: string }
              old: {}
              new: {}
              timestamp: { type: string, format: date-time }
        unclustered_refs:
          type: array
          items: { $ref: '#/UUID' }
        fixes_preview:
          type: array
          description: A4 建议只读投影；can_auto_apply 恒 false；非写接口
          items:
            type: object
            properties:
              field: { type: string }
              current: { type: string }
              suggested: { type: string }
              reason: { type: string }
              confidence: { type: number }
```

5. **成功判定**：簇详情 + 修改历史。人工修正成功以写命令提交后本 GET 可见新 history 为准（§5.2 本地编辑未提交无 API）。jira_write / heal_apply 不在本资源上执行。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：无 CAS（修正只追加 history）。

---

#### API-133 `GET /api/v1/failure-clusters/{failure_cluster_id}/similar`

历史相似失败。

1. **鉴权 / 角色 / Token scope**：同 API-130。仅返回调用方有权项目内的历史簇。
2. **同步性**：同步查询。
3. **Query params**：`cursor`、`limit`；相似算法 / 阈值 **TBD**（服务端检索，前端不本地算相似度）。
4. **Response YAML**

```yaml
SimilarFailureClusterItem:
  type: object
  required: [id, test_run_id, category, confidence]
  properties:
    id: { $ref: '#/UUID' }
    test_run_id: { $ref: '#/UUID' }
    category:
      type: string
      enum:
        - env_down
        - auth_expired
        - locator_stale
        - assertion_real_bug
        - flaky
        - data_issue
        - unknown
    confidence: { type: number }
    similarity_score:
      type: number
      description: 服务端投影；算法 TBD
    created_at: { type: string, format: date-time }
```

外壳：`ListEnvelope`。

5. **成功判定**：相似检索以后端为准。空集 = 无相似，不是错误。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：无。

---

### 7.11 质量门禁（读）

#### API-140 `GET /api/v1/quality-gate-policies`

对照边界 **§2.7**。

1. **鉴权 / 角色 / Token scope**：Sess；项目四角色可读。不允许 Tok。写 / blocking 切换另限 admin/owner。
2. **同步性**：同步查询。
3. **Query params**：必填 `project_id`；`cursor`、`limit`；可选 `mode`（`report_only` / `blocking`）。
4. **Response YAML**

```yaml
QualityGatePolicyListItem:
  type: object
  required: [id, project_id, mode, policy_version, version]
  properties:
    id: { $ref: '#/UUID' }
    project_id: { $ref: '#/UUID' }
    thresholds:
      type: object
      required: [min_pass_rate, max_p95_ms, max_error_rate]
      properties:
        min_pass_rate: { type: number }
        max_p95_ms: { type: number }
        max_error_rate: { type: number }
    mode:
      type: string
      enum: [report_only, blocking]
    policy_version: { type: integer }
    version: { $ref: '#/Version' }
    created_at: { type: string, format: date-time }
    updated_at: { type: string, format: date-time }
```

外壳：`ListEnvelope`。`scope` 详情见 API-141（Confidential 最小化）。

5. **成功判定**：策略列表。历史评估不因策略更新改写（只读本列表无法回放历史——用 GateEvaluation 快照）。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：必返（与 `policy_version` 并存：前者 CAS，后者策略内容版本）。

---

#### API-141 `GET /api/v1/quality-gate-policies/{policy_id}`

1. **鉴权 / 角色 / Token scope**：同 API-140。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**

```yaml
QualityGatePolicyDetail:
  allOf:
    - $ref: '#/QualityGatePolicyListItem'
    - type: object
      required: [scope]
      properties:
        scope:
          type: object
          description: 用例集 / 计划 / 仓库分支绑定；Confidential 最小化
```

5. **成功判定**：策略详情含版本。blocking 是否开启以 `mode` 为准（须曾显式确认，写侧约束）。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：必返。

---

#### API-144 `GET /api/v1/gate-evaluations`

对照边界 **§2.7** 评估历史。**不可变**，仅 GET。

1. **鉴权 / 角色 / Token scope**：Sess；项目四角色。不允许 Tok。
2. **同步性**：同步查询。
3. **Query params**：`cursor`、`limit`；可选 `project_id`、`test_run_id`、`result`（`pass` / `fail` / `waived` **仅此三值**）、`created_from` / `created_to`。
4. **Response YAML**

```yaml
GateEvaluationListItem:
  allOf:
    - $ref: '#/AppendOnlyMeta'
    - type: object
      required: [test_run_id, policy_id, result]
      properties:
        test_run_id: { $ref: '#/UUID' }
        policy_id: { $ref: '#/UUID' }
        result: { $ref: '#/GateEvaluationResult' }
        check_run_ref:
          type: object
          nullable: true
          description: GitHub 回写引用与同步状态；无 secret
        waiver_approval_id: { $ref: '#/UUID' }
```

外壳：`ListEnvelope`。禁止 `result=not_evaluated`。无评估的 run **不出现**在本列表（用 API-146 投影 reason）。

5. **成功判定**：历史查询。豁免不改写原行（`waiver_approval_id` 挂接）。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-VAL-001`（含非法 result）、`HT-INT-001`。
7. **version**：无（不可变）。

---

#### API-145 `GET /api/v1/gate-evaluations/{gate_evaluation_id}`

1. **鉴权 / 角色 / Token scope**：同 API-144。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**

```yaml
GateEvaluationDetail:
  allOf:
    - $ref: '#/GateEvaluationListItem'
    - type: object
      required: [policy_snapshot, threshold_details, evidence_refs]
      properties:
        policy_snapshot:
          type: object
          description: 评估时策略快照；Internal
        threshold_details:
          type: object
          description: 逐阈值实测与判定；Confidential 最小化
        evidence_refs:
          type: array
          items: { $ref: '#/UUID' }
```

`result` ∈ `pass` / `fail` / `waived` only。

5. **成功判定**：边界 **§6-9**：可评估时的权威结论为本资源 `result` + 逐阈值明细。豁免记录可查（`waiver_approval_id`）对照 **§6-13**（豁免命令成功另判）。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：无。

---

#### API-146 `GET /api/v1/test-runs/{test_run_id}/gate-evaluation`

对照边界 **§2.7** / **§6-9**。挂接或不可评估投影。

1. **鉴权 / 角色 / Token scope**：Sess；项目四角色。不允许 Tok。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**

```yaml
TestRunGateEvaluationProjection:
  type: object
  required: [test_run_id, evaluation, unevaluated_reason]
  properties:
    test_run_id: { $ref: '#/UUID' }
    gate_evaluation_id:
      type: string
      format: uuid
      nullable: true
      description: 与 TestRun.gate_evaluation_id 一致；agent 恒 null
    evaluation:
      allOf:
        - $ref: '#/GateEvaluationDetail'
      nullable: true
      description: 有评估行时非 null；否则必须为 null
    unevaluated_reason:
      allOf:
        - $ref: '#/UnevaluatedReason'
      nullable: true
      description: |
        evaluation=null 时必填。示例：agent_source / cancelled_or_timeout /
        partial_report / policy_unmet（精确码 TBD）。
        evaluation 非 null 时必须为 null。
        禁止使用 result=not_evaluated。
```

互斥不变量：`(evaluation == null) XOR (unevaluated_reason == null)` 必须为真（二者恰有一个为 null：有评估则 reason 为 null，无评估则 evaluation 为 null 且 reason 必填）。

5. **成功判定**：边界 **§6-9**：
   - 可评估：`evaluation.result` ∈ `pass` / `fail` / `waived` + 逐阈值明细；
   - CANCELLED / TIMEOUT / 缺配 / partial / agent：无 GateEvaluation + **明确** `unevaluated_reason`；
   - **绝不默认通过**；Release fail-close 消费本 reason。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：评估行不可变无 CAS。TestRun 挂接对账用 API-061 `version` + `gate_evaluation_id`。

---

### 7.12 ReleaseTask（读）

#### API-150 `GET /api/v1/release-tasks`

对照边界 **§2.8**（M3）。

1. **鉴权 / 角色 / Token scope**：Sess；项目四角色。不允许 Tok。
2. **同步性**：同步查询。
3. **Query params**：必填 `project_id`；可选 `status`（六态）；`cursor`、`limit`。
4. **Response YAML**

```yaml
ReleaseTaskListItem:
  type: object
  required: [id, project_id, status, jira_version_ref, version]
  properties:
    id: { $ref: '#/UUID' }
    project_id: { $ref: '#/UUID' }
    status:
      type: string
      enum: [DRAFT, PENDING_CONFIRM, SUBMITTED, READY, FAILED_RETRYABLE, CANCELLED]
    jira_version_ref: { type: string }
    version: { $ref: '#/Version' }
    created_at: { type: string, format: date-time }
    updated_at: { type: string, format: date-time }
```

外壳：`ListEnvelope`。READY ≠ 生产已发布。

5. **成功判定**：列表快照。无「执行生产发布」路径。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：必返。

---

#### API-151 `GET /api/v1/release-tasks/{release_task_id}`

含 Readiness 与 A5 草稿**只读**。

1. **鉴权 / 角色 / Token scope**：同 API-150。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**

```yaml
ReleaseTaskDetail:
  allOf:
    - $ref: '#/ReleaseTaskListItem'
    - type: object
      required: [scope_snapshot]
      properties:
        scope_snapshot:
          type: object
          description: 创建后不可变；Confidential 最小化
        gate_result_ref: { $ref: '#/UUID' }
        notes_draft:
          type: string
          nullable: true
          description: A5 草稿只读；禁止当自动推送；Confidential
        a5:
          type: object
          nullable: true
          description: ⊆ problem_model A5；missing_inputs 显式列出
          properties:
            summary: { type: string }
            changes: { type: array, items: { type: object } }
            checklist: { type: array, items: { type: object } }
            missing_inputs:
              type: array
              items: { type: string }
        divergence:
          type: object
          nullable: true
          description: CANCELLED 后迟到 READY 只追加；不覆盖取消
        release_item:
          type: object
          nullable: true
          properties:
            external_item_id: { type: string, nullable: true }
            external_system: { type: string }
        readiness:
          description: 可内嵌与 API-155 同形的投影，避免双源
          $ref: '#/ReadinessProjection'
```

5. **成功判定**
   - A5 **禁止自动推送**；只读。
   - **§6-10**：Readiness 以后端为准（见 API-155）。
   - **§6-11**：`READY` 表示 webhook 观察 + 命令后的权威成功，不是预览提交。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：必返。`scope_snapshot` 不可变。

---

#### API-155 `GET /api/v1/release-tasks/{release_task_id}/readiness`

对照边界 **§6-10**。

1. **鉴权 / 角色 / Token scope**：同 API-150。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**

```yaml
ReadinessProjection:
  type: object
  required: [release_task_id, overall]
  properties:
    release_task_id: { $ref: '#/UUID' }
    overall:
      type: string
      description: 红/黄/绿分区码；精确枚举 TBD，由后端评估，前端不汇总
    items:
      type: array
      items:
        type: object
        required: [key, level]
        properties:
          key: { type: string }
          level: { type: string }
          evidence_refs:
            type: array
            items: { $ref: '#/UUID' }
          unmet: { type: boolean }
    gate_evaluation_id: { $ref: '#/UUID' }
    unevaluated_reason:
      allOf: [{ $ref: '#/UnevaluatedReason' }]
      nullable: true
      description: 门禁不可评估时 fail-close；不得默认通过
    task_version: { $ref: '#/Version' }
```

5. **成功判定**：边界 **§6-10**：Readiness 结论 = 本响应评估数据。前端红黄绿仅为呈现。无评估不得视为通过。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：返回 `task_version`。

---

### 7.13 集成中心（读）

#### API-160 `GET /api/v1/connectors`

对照边界 **§2.11**。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess。不允许 Tok。
   - 角色：fail-close —— `owner` / `admin` 可读完整列表；`tester` / `viewer` 仅能通过项目总览健康摘要（API-012）感知，本列表 → `HT-IAM-001`（若另批放开再改，本文不预先放开）。
2. **同步性**：同步查询。
3. **Query params**：可选 `type`（`jira` / `github` / `ci` / `release`）；`cursor`、`limit`。
4. **Response YAML**

```yaml
ConnectorListItem:
  type: object
  required: [id, type, name, credential_present, outbound_write_enabled, version]
  properties:
    id: { $ref: '#/UUID' }
    type:
      type: string
      enum: [jira, github, ci, release]
    name: { type: string, description: Confidential 最小化 }
    auth_method: { type: string }
    credential_present: { $ref: '#/CredentialPresence' }
    webhook_secret_present:
      type: boolean
      description: 是否已绑定 HMAC 引用；永不返回 secret 值
    outbound_write_enabled: { type: boolean }
    action_contract:
      type: object
      description: sideEffectLevel / supportsPreview / Idempotency / Compensation；未声明默认 DENY
    config_version: { type: integer }
    version: { $ref: '#/Version' }
    created_at: { type: string, format: date-time }
    updated_at: { type: string, format: date-time }
```

外壳：`ListEnvelope`。禁止：`credential_ref` 值、`webhook_secret_ref` 值。

5. **成功判定**：连接器配置快照。健康细节见 API-161。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：必返。

---

#### API-161 `GET /api/v1/connectors/{connector_id}`

1. **鉴权 / 角色 / Token scope**：同 API-160。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**

```yaml
ConnectorDetail:
  allOf:
    - $ref: '#/ConnectorListItem'
    - type: object
      properties:
        health_status:
          type: object
          nullable: true
          properties:
            last_checked_at: { type: string, format: date-time }
            ok: { type: boolean }
            latency_ms: { type: integer }
```

无 secret。

5. **成功判定**：详情 + 健康投影。HMAC 验签失败不在本接口返回密钥细节。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：必返。

---

#### API-164 `GET /api/v1/connectors/{connector_id}/webhook-deliveries`

入站投递历史（观察记录查询；非 Inbox CRUD 资源树对外化——仅投影）。

1. **鉴权 / 角色 / Token scope**：同 API-160。
2. **同步性**：同步查询。
3. **Query params**：`cursor`、`limit`；可选 `signature_ok`、`created_from` / `created_to`。
4. **Response YAML**

```yaml
WebhookDeliveryItem:
  type: object
  required: [id, connector_id, observed_at, signature_ok]
  properties:
    id: { $ref: '#/UUID' }
    connector_id: { $ref: '#/UUID' }
    source:
      type: string
      description: webhook / poll
    observation_key: { type: string }
    signature_ok: { type: boolean }
    observed_at: { type: string, format: date-time }
    data_classification: { $ref: '#/DataClassification' }
    payload_ref:
      type: string
      nullable: true
      description: object_key；无 secret；禁止原文 dump
    accepted:
      type: boolean
      description: 是否已落入观察；不表示已改 TestRun 状态机
```

外壳：`ListEnvelope`。失败重试是系统治理；本接口**只读**（若未定义重试命令则仅查询）。

5. **成功判定**：投递历史可查。验签失败仍可有审计/观察行（无 secret）。乱序只对账，不在本接口改状态。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-001`、`HT-RES-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：观察行无 CAS。连接器对账用 API-161 `version`。

---

#### API-165 `GET /api/v1/connectors/{connector_id}/outbound-channels`

出站通知渠道（配置查询；通知产生仍在服务端）。

1. **鉴权 / 角色 / Token scope**：同 API-160。
2. **同步性**：同步查询。
3. **Query params**：无分页或 `cursor`/`limit` TBD（渠道数量通常很小）。
4. **Response YAML**

```yaml
OutboundChannelItem:
  type: object
  required: [id, enabled, is_primary]
  properties:
    id: { type: string }
    enabled: { type: boolean }
    is_primary: { type: boolean }
    channel_type:
      type: string
      description: 企微/钉钉/飞书等；精确枚举 TBD，不是新领域对象
    endpoint_present:
      type: boolean
      description: 是否已配置端点；永不返回 webhook/bot secret
```

外壳：`ListEnvelope` 或数组（若不用 cursor，仍用 `ListEnvelope` 保持一致）。

5. **成功判定**：渠道配置快照。投递成功与否见通知投影 / 投递治理，不在本 GET 冒充。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：渠道若随连接器 CAS，返回连接器 `version` 于信封级 **TBD**；建议响应根级 `connector_version`。

补充响应根字段：`connector_version: Version`。

---

### 7.14 ApiToken 管理（读）

#### API-170 `GET /api/v1/api-tokens`

对照边界 **§2.11**。列表：**无哈希无明文**。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess。不允许用 ApiToken 列出全部 Token（避免自我枚举升级；fail-close）。
   - 角色：`owner` / `admin`。`tester` / `viewer` → `HT-IAM-001`。签发者是否可只看自己的 Token：**TBD**（未批则仅 owner/admin 全列表）。
2. **同步性**：同步查询。
3. **Query params**：`cursor`、`limit`；可选 `issued_to_user_id`。
4. **Response YAML**

```yaml
ApiTokenListItem:
  type: object
  required: [id, token_prefix, scopes, project_ids, expires_at]
  properties:
    id: { $ref: '#/UUID' }
    issued_to_user_id: { $ref: '#/UUID' }
    token_prefix: { type: string, description: 展示用短前缀；非秘密 }
    scopes:
      type: array
      items:
        type: string
        enum: [read, write, execute, delete]
    project_ids:
      type: array
      items: { $ref: '#/UUID' }
      description: 白名单；空数组语义 TBD（禁止默认全部项目）
    expires_at: { type: string, format: date-time }
    revoked_at:
      type: string
      format: date-time
      nullable: true
    last_used_at:
      type: string
      format: date-time
      nullable: true
      description: 异步；非审计替代
    created_at: { type: string, format: date-time }
```

外壳：`ListEnvelope`。字段 **`token` / `token_hash` 永不出现**。无 CAS `version`（签发后只吊销 / 异步 last_used）。

5. **成功判定**：元数据列表。吊销是否生效以 `revoked_at` 非空为准（即时）。不能从本列表恢复明文。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：无领域 CAS。对账用 `id` + `revoked_at` + `expires_at`。

---

### 7.15 AI 观测、Copilot、技能、路由（读）

#### API-183 `GET /api/v1/ai/cost-dashboard`

对照边界 **§2.13**；唯一数据源 AIInvocationLog。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess。不允许 Tok。
   - 角色：`owner` / `admin` 看组织聚合；`tester` / `viewer` → `HT-IAM-001`（预算看板属治理页）。
2. **同步性**：同步查询。
3. **Query params**：`from` / `to`（date-time，必填窗口上限 TBD）；可选 `project_id`、`dimension`（user / workflow / capability — 精确维 TBD）。无 cursor（聚合）；若拆明细则另 API（本 ID 为看板）。
4. **Response YAML**

```yaml
AiCostDashboard:
  type: object
  required: [window, totals]
  properties:
    window:
      type: object
      required: [from, to]
      properties:
        from: { type: string, format: date-time }
        to: { type: string, format: date-time }
    totals:
      type: object
      required: [token_usage, cost, invocation_count]
      properties:
        token_usage: { type: object }
        cost: { type: number }
        invocation_count: { type: integer }
        adoption_rate:
          type: number
          description: 从 AIInvocationLog.result 聚合；口径 TBD
        degrade_rate:
          type: number
        cost_per_workflow:
          type: object
          additionalProperties: { type: number }
    series:
      type: array
      items: { type: object }
      description: 时序点；前端不二次计算权威值
```

禁止：Prompt、input_ref 解包、按模型原文。

5. **成功判定**：指标以后端聚合为准（§3.1-6 / §4.1-10）。前端图表不得当事实源。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-001`、`HT-VAL-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：聚合无 CAS。对账用窗口 + totals；账本余量另见 API-017。

---

#### API-184 `GET /api/v1/ai-invocation-logs`

**append-only**；**无 Prompt**。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess。不允许 Tok。
   - 角色：`owner` / `admin`；本人 `tester` 仅 `user_id=me` **TBD**（未批则 tester 禁列表，fail-close `HT-IAM-001`）。
2. **同步性**：同步查询。
3. **Query params**：`cursor`、`limit`；可选 `user_id`、`result`（`ok` / `degraded` / `refused`）、`model`、`copilot_session_id`、`created_from` / `created_to`。
4. **Response YAML**

```yaml
AIInvocationLogListItem:
  allOf:
    - $ref: '#/AppendOnlyMeta'
    - type: object
      required: [model, prompt_version, usage, cost, latency_ms, data_classification, result]
      properties:
        user_id: { $ref: '#/UUID' }
        model: { type: string }
        prompt_version:
          type: string
          description: 禁止 Prompt 原文
        usage: { type: object }
        cost: { type: number }
        latency_ms: { type: integer }
        data_classification: { $ref: '#/DataClassification' }
        result:
          type: string
          enum: [ok, degraded, refused]
        skill_version_id: { $ref: '#/UUID' }
        model_route_id: { $ref: '#/UUID' }
        copilot_session_id: { $ref: '#/UUID' }
        input_ref:
          type: string
          nullable: true
          description: 脱敏/截断后 object_key；禁止解包为 Prompt 原文
```

外壳：`ListEnvelope`。无 CAS `version`。

5. **成功判定**：日志可检索。`result=degraded` 必须可感知。采纳率只从此聚合（API-183）。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-001`、`HT-VAL-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：无。

---

#### API-185 `GET /api/v1/ai-invocation-logs/{log_id}`

1. **鉴权 / 角色 / Token scope**：同 API-184。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**：`ResourceEnvelope.data` = `AIInvocationLogListItem`。**禁止** `input_ref` 解包为 Prompt；**禁止** Restricted 出站内容。
5. **成功判定**：单条不可变日志。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：无。

---

#### API-190 `GET /api/v1/copilot-sessions`

对照边界 **§2.12**（M3+）。

1. **鉴权 / 角色 / Token scope**：Sess；仅**当前用户**自己的会话列表。四角色均可（viewer 只读会话）。不允许 Tok。
2. **同步性**：同步查询。
3. **Query params**：`cursor`、`limit`；`sort` = `updated_at` desc。
4. **Response YAML**

```yaml
CopilotSessionListItem:
  type: object
  required: [id, user_id, data_classification, version]
  properties:
    id: { $ref: '#/UUID' }
    user_id: { $ref: '#/UUID' }
    title:
      type: string
      nullable: true
      description: Confidential 最小化
    selected_skill_version_id: { $ref: '#/UUID' }
    data_classification: { $ref: '#/DataClassification' }
    version: { $ref: '#/Version' }
    created_at: { type: string, format: date-time }
    updated_at: { type: string, format: date-time }
```

外壳：`ListEnvelope`。列表**不**返回 `messages`。无发明会话状态机。

5. **成功判定**：会话目录。消息正文见 API-193 最小化。
6. **错误码**：`HT-AUTH-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：必返（摘要可更新）。

---

#### API-193 `GET /api/v1/copilot-sessions/{session_id}`

消息 **Confidential 最小化**。

1. **鉴权 / 角色 / Token scope**：Sess；仅会话归属用户，或 `owner` / `admin` 治理查阅 **TBD**（未批则仅本人，他人 `HT-RES-001`）。
2. **同步性**：同步查询。
3. **Query params**：可选 `message_cursor` / `message_limit`（消息内分页 TBD）。
4. **Response YAML**

```yaml
CopilotSessionDetail:
  allOf:
    - $ref: '#/CopilotSessionListItem'
    - type: object
      required: [messages]
      properties:
        messages:
          type: array
          description: |
            Confidential 最小化：可返回 role、truncated body、citations、tool_calls.args_hash、
            refused_policies。禁止 Restricted 内容、禁止 Prompt 原文、禁止秘密参数。
          items:
            type: object
            required: [role]
            properties:
              role: { type: string }
              content_truncated: { type: string }
              citations:
                type: array
                items:
                  type: object
                  properties:
                    source_type:
                      type: string
                      enum: [jira, github, platform]
                    resource_id: { type: string }
                    evidence_ref: { $ref: '#/UUID' }
              tool_calls:
                type: array
                items:
                  type: object
                  properties:
                    tool: { type: string }
                    args_hash: { type: string }
                    result_summary: { type: string }
              refused_policies:
                type: array
                items: { type: string }
```

citations 须为服务端已校验集合。只读技能不改变 TestRun 控制流。

5. **成功判定**：会话快照。A6 回答权威在后端（含 citations 校验）。`copilot_write` M0/M1 未启用。
6. **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-IAM-001`、`HT-INT-001`。
7. **version**：必返。

---

#### API-194 `GET /api/v1/skills`

对照边界 **§2.12**（M4）。清单无单独 GET-by-id，本列表须够用。

1. **鉴权 / 角色 / Token scope**：Sess；租户成员可读已对角色可见的技能（personal 仅本人；team/org 按发布范围）。不允许 Tok。
2. **同步性**：同步查询。
3. **Query params**：`cursor`、`limit`；可选 `published_scope`（`personal` / `team` / `org`）；可选 `q`（名称）。
4. **Response YAML**

```yaml
SkillListItem:
  type: object
  required: [id, name, version]
  properties:
    id: { $ref: '#/UUID' }
    name: { type: string, description: Confidential 最小化 }
    current_published_version_id:
      type: string
      format: uuid
      nullable: true
      description: 空 = 未版本化，不进生产
    current_published_scope:
      type: string
      nullable: true
      enum: [personal, team, org]
    version: { $ref: '#/Version' }
    latest_version:
      type: object
      nullable: true
      description: 当前指针版本摘要；列表不返回完整 instructions
      properties:
        id: { $ref: '#/UUID' }
        version_seq: { type: integer }
        published_scope:
          type: string
          nullable: true
          enum: [personal, team, org]
        manifest_summary:
          type: object
          description: allowedTools / max_steps / 超时 / 副作用上限；无秘密
        data_classification: { $ref: '#/DataClassification' }
    created_at: { type: string, format: date-time }
    updated_at: { type: string, format: date-time }
```

外壳：`ListEnvelope`。完整 `instructions` 不在列表默认返回（Confidential 最小化；需要时 TBD 另字段，仍禁缓存）。

5. **成功判定**：技能目录。未版本化不进生产（`current_published_version_id` 空）。只读技能不改执行控制流。
6. **错误码**：`HT-AUTH-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：技能聚合 CAS（发布指针）。已发布 SkillVersion 不可覆盖，无 Version 行 CAS。

---

#### API-196 `GET /api/v1/model-routes`

对照边界 **§2.13**。

1. **鉴权 / 角色 / Token scope**：Sess；`owner` / `admin`。`tester` / `viewer` → `HT-IAM-001`。不允许 Tok。
2. **同步性**：同步查询。
3. **Query params**：`cursor`、`limit`；可选 `task_type`、`data_classification`。
4. **Response YAML**

```yaml
ModelRouteListItem:
  type: object
  required:
    - id
    - task_type
    - data_classification
    - provider_allowlist
    - max_cost
    - require_prompt_version
    - require_structured_output
    - credential_present
    - version
  properties:
    id: { $ref: '#/UUID' }
    task_type: { type: string }
    data_classification: { $ref: '#/DataClassification' }
    provider_allowlist:
      type: array
      items: { type: string }
    max_cost: { type: number }
    fallback: { type: object, nullable: true }
    require_prompt_version: { type: boolean }
    require_structured_output: { type: boolean }
    credential_present: { $ref: '#/CredentialPresence' }
    version: { $ref: '#/Version' }
    created_at: { type: string, format: date-time }
    updated_at: { type: string, format: date-time }
```

外壳：`ListEnvelope`。**永不**返回 `credential_ref` 值。清单无 GET-by-id，本列表即配置表全文语义。

5. **成功判定**：路由表快照。测试连接是写命令（API-198），不在本 GET。Restricted 默认不出站由路由约束表达，不在响应中放 Restricted 正文。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-001`、`HT-VAL-001`、`HT-INT-001`。
7. **version**：必返。

---

### 7.16 制品元数据（读）

#### API-220 `GET /api/v1/artifacts/{artifact_id}`

对照边界 **§5.1 类 8**、`api_spec.md` §9.4。仅元数据；**`object_key` 非授权**。正文下载为 API-221（本文件不展开写命令/代理流，除成功判定引用 G5）。

1. **鉴权 / 角色 / Token scope**
   - 通道：Sess。不允许 Tok 下载/读 Restricted（清单仅 Sess；Token 读制品 **未批 = 否**）。
   - 角色：制品所属项目四角色可读**元数据**。`data_classification=Restricted`：仍可返回分级与 kind 等元数据，**不**返回可还原正文的旁路字段。
2. **同步性**：同步查询。
3. **Query params**：无。
4. **Response YAML**

```yaml
ArtifactMetadata:
  allOf:
    - $ref: '#/AppendOnlyMeta'
    - type: object
      required:
        - test_run_id
        - kind
        - object_key
        - checksum
        - data_classification
      properties:
        case_result_id: { $ref: '#/UUID' }
        test_run_id: { $ref: '#/UUID' }
        kind:
          type: string
          description: 截图/视频/Trace/日志/报告/轨迹 等；不当新领域对象；精确枚举 TBD
        object_key:
          type: string
          description: 稳定引用；禁止当下载令牌；禁止预签名 URL
        checksum: { type: string }
        byte_size: { type: integer, nullable: true }
        mime_type: { type: string, nullable: true }
        data_classification: { $ref: '#/DataClassification' }
        original_filename:
          type: string
          nullable: true
          description: 仅展示，不作路径
        content_access:
          type: object
          description: 如何取正文（M0/M1 仅代理）
          properties:
            mode:
              type: string
              enum: [app_proxy]
            content_path:
              type: string
              description: API-221 路径提示；调用仍须独立鉴权
```

不返回存储内部路径遍历。无 CAS `version`（元数据可补 checksum，对账用 `id` + `checksum`）。

5. **成功判定**：元数据可读 ≠ 已授权获取正文（G5：引用不是授权）。**§6** 导出成功 = Artifact 可**授权**获取（走 API-221/223），本 GET 只证明记录存在。Restricted 不走普通预签名（M0/M1 无预签名）。
6. **错误码**：`HT-AUTH-001`、`HT-IAM-001`、`HT-RES-001`、`HT-INT-001`。
7. **version**：无 CAS。对账用 `id` + `checksum` + `data_classification`。关联 TestRun 用 API-061 `version`。

---

### 7.W 写与状态迁移

### 1. 认证会话写（并入 §7.2）

#### API-003 `POST /api/v1/auth/session/logout`

##### 鉴权 / 角色 / scope

- **通道**：Sess。Cookie 已过期时仍应尽力吊销服务端会话记录（尽力而为，不伪装成业务成功）。
- **角色**：任一已认证主体，**含 viewer**（登出不是领域对象写）。
- **ApiToken**：不适用（Token 无浏览器会话可吊销；吊销 Token 走 API-172）。

##### 同步性

**同步完成。** HTTP `204`（无 body）或 `200` `{ logged_out: true }`。无异步 Worker。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 建议。重复登出同 key 同 hash → 同一「已登出」结果，不报错。

LogoutRequest:
  type: object
  additionalProperties: false
  properties: {}
  description: 无业务 body。禁止在 query 携带 token 明文。

# 204 No Content
# 或
LogoutResponse:
  type: object
  required: [logged_out]
  properties:
    logged_out: { type: boolean, const: true }
```

##### 成功判定

- **受理 = 完成**：服务端会话记录不可再用于后续 API（后续请求 `HT-AUTH-001`）。
- 前端清本地态、跳转登录页 **不是**权威成功。
- 完全无 Cookie：视为已登出，仍 `204`（不返回 `HT-AUTH-001` 强迫登录环）。
- 对照边界 §6-14：权限以后端每请求为准；登出后 `API-005` 不得再返回主体。

##### 错误码

| code | 何时 |
| --- | --- |
| `HT-VAL-001` | 非法 Content-Type / 非空未知字段且契约拒绝 |
| `HT-IDEM-001` | 同 key 异 hash |
| `HT-QUOTA-002` | 入口限流 |
| `HT-INT-001` | 内部错误（仍须尽力吊销） |

无 `HT-STATE` / `HT-VER` / `HT-POL`（无领域聚合）。

##### 幂等

`command_type = session.logout`。建议 `Idempotency-Key`。无 CAS。

---

#### API-004 `POST /api/v1/auth/reauth`

##### 鉴权 / 角色 / scope

- **通道**：Sess（已有会话，但新鲜度不足）。
- **角色**：任一已认证主体（含 viewer）。L3+ 动作被 Policy Gate 判 `REQUIRE_REAUTH` 后调用。
- **不可**用本接口替代四眼审批或发放领域授权。

##### 同步性

**同步完成**（step-up 交互形态 **TBD**：IdP 强认证 / 新鲜认证）。完成后会话认证强度更新。窗口秒数 **TBD**，禁止写默认分钟数。

若 step-up 需浏览器跳转 IdP：本接口可返回 `authorization_url`（同步返回 URL ≠ 再认证完成）。权威完成仍是会话新鲜度已更新、Gate 不再因窗口返回 `REQUIRE_REAUTH`。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 建议。完成 step-up 后重放原命令须使用**原命令**的同一 Idempotency-Key（哈希不变），不是本接口的 key。

ReauthRequest:
  type: object
  additionalProperties: false
  properties:
    return_path:
      type: string
      description: 可选；白名单相对路径，防开放重定向

ReauthResponse:
  type: object
  required: [reauth_satisfied]
  properties:
    reauth_satisfied:
      type: boolean
      description: true = 本会话已满足当前再认证窗口（窗口数值 TBD）
    authorization_url:
      type: string
      description: 仅当仍需跳转 IdP；有此字段则 reauth_satisfied=false
    expires_hint_at:
      type: string
      format: date-time
      description: 可选；非 TTL 默认值
```

Body **无** IdP access_token / refresh_token 明文。

##### 成功判定

- **完成**：`reauth_satisfied=true`，随后重放被拒命令时 Gate **不再**仅因窗口返回 `REQUIRE_REAUTH`（仍可能 DENY / REQUIRE_APPROVAL）。
- 返回 `authorization_url` = **未完成**。
- 对照边界 §6-14；架构：再认证不替代审批，审批不替代再认证。
- 重放原写命令：同一 `Idempotency-Key` **仅当请求哈希不变**。

##### 错误码

| code | 何时 |
| --- | --- |
| `HT-AUTH-001` | 无会话 |
| `HT-AUTH-002` | step-up 未完成又被 Gate 再次要求 |
| `HT-AUTH-003` | IdP `state`/`nonce`/PKCE 失败（走回调时） |
| `HT-VAL-001` | 非法 `return_path` |
| `HT-IAM-001` | 循环失败 / 主体无权继续 |
| `HT-IDEM-001` | 同 key 异 hash |
| `HT-QUOTA-002` | 限流（§11 必覆盖本接口） |

无领域 `HT-STATE` / `HT-VER` / `HT-POL`。

##### 幂等

`command_type = session.reauth`。建议 Key。无 CAS。

---

### 2. 成员、通知订阅、已读、SIEM（并入 §7 身份 / 工作台写）

#### API-014 `POST /api/v1/projects/{project_id}/members`

##### 鉴权 / 角色 / scope

- Sess。**角色**：`owner` / `admin`。`tester` / `viewer` → `HT-IAM-001`。
- 添加后角色 ∈ `owner / admin / tester / viewer`。禁止把 Jira 同步当作本命令的隐式调用方。

##### 同步性

**同步完成**（短事务落 `ProjectMember`）。`200` 资源。成员表 CAS 精确资源 **TBD**（`api_spec.md` §14.1）；未冻结前不强制 `expected_version`，并发靠唯一约束 `(organization_id, project_id, user_id)`。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须（可重试创建）。

ProjectMemberCreate:
  type: object
  required: [user_id, role]
  additionalProperties: false
  properties:
    user_id: { $ref: '#/UUID' }
    role:
      type: string
      enum: [owner, admin, tester, viewer]
    expected_project_version:
      type: integer
      minimum: 1
      description: 可选；项目聚合 CAS 未冻结（TBD）。若客户端发送则服务端有则校验、无则忽略不得发明默认版本源

ProjectMember:
  type: object
  required: [project_id, user_id, role]
  properties:
    project_id: { $ref: '#/UUID' }
    user_id: { $ref: '#/UUID' }
    role:
      type: string
      enum: [owner, admin, tester, viewer]
    display_name: { type: string }
```

响应 `ResourceEnvelope.data` = `ProjectMember`。无密码 / IdP 密钥。

##### 成功判定

- **完成**：同租户 GET 成员列表（API-013）可见该 `user_id` + `role`。
- 前端表格刷新 **不是**权威。对照 §6-14。
- 已存在同一 `(project_id, user_id)`：同 key 同 hash 返回已有成员；否则 `HT-VAL-001` 或幂等冲突，**禁止**静默改角色（改角色走 API-015）。

##### 错误码

| code | 何时 |
| --- | --- |
| `HT-AUTH-001` | 未认证 |
| `HT-IAM-001` | viewer/tester 或非本项目管理员 |
| `HT-RES-001` | 项目不存在 / 跨租户 |
| `HT-VAL-001` | 角色非法、user_id 非本租户用户 |
| `HT-IDEM-001` | 同 key 异 hash |
| `HT-VER-001` | 若启用了项目 version 且不匹配 |
| `HT-STATE-001` | 不适用于「最后 owner」本接口（添加不移除） |

##### 幂等

`command_type = project_member.add`。必须 Key。失败也审计。

---

#### API-015 `PATCH /api/v1/projects/{project_id}/members/{user_id}`

##### 鉴权 / 角色 / scope

- Sess。`owner` / `admin`。`tester` / `viewer` → `HT-IAM-001`。
- 不可将**最后一个** `owner` 改为非 owner（`HT-STATE-001`）。

##### 同步性

**同步完成。** `200` 更新后 `ProjectMember`。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

ProjectMemberPatch:
  type: object
  required: [role]
  additionalProperties: false
  properties:
    role:
      type: string
      enum: [owner, admin, tester, viewer]
    expected_project_version:
      type: integer
      minimum: 1
      description: 可选；CAS 资源 TBD
```

响应同 API-014 `ProjectMember`。

##### 成功判定

- **完成**：API-013 读到新 `role`。Jira 同步不得回写覆盖（ADR 0005 为 Proposed；当前平台角色权威）。
- 对照 §6-14。

##### 错误码

`HT-AUTH-001`、`HT-IAM-001`、`HT-RES-001`、`HT-VAL-001`、`HT-STATE-001`（最后 owner）、`HT-IDEM-001`、`HT-VER-001`（若启用）。

##### 幂等

`command_type = project_member.patch_role`。必须 Key。无冻结 CAS 字段名时不以发明的 etag 代替审计。

---

#### API-016 `DELETE /api/v1/projects/{project_id}/members/{user_id}`

##### 鉴权 / 角色 / scope

- Sess。`owner` / `admin`。`tester` / `viewer` → `HT-IAM-001`。
- 语义是**移除成员关系**，不是物理删 User，不是擦审计。
- 不可移除最后一个 `owner` → `HT-STATE-001`。

##### 同步性

**同步完成。** `204` 或 `200` `{ removed: true }`。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。
# Body 可空；若发送 CAS：

ProjectMemberRemove:
  type: object
  additionalProperties: false
  properties:
    expected_project_version:
      type: integer
      minimum: 1
      description: 可选；TBD
```

无成员密文。重复删除同 key → 已移除结果（幂等）。

##### 成功判定

- **完成**：API-013 不再列出该 `user_id`（同租户）。跨租户统一 `HT-RES-001`。
- 对照 §6-14。

##### 错误码

`HT-AUTH-001`、`HT-IAM-001`、`HT-RES-001`、`HT-STATE-001`（最后 owner）、`HT-IDEM-001`、`HT-VER-001`（若启用）。

##### 幂等

`command_type = project_member.remove`。必须 Key。

---

#### API-023 `POST /api/v1/notifications/{notification_id}/read`

##### 鉴权 / 角色 / scope

- Sess。通知是**传输协调面**，非第 24 对象。
- **角色**：该通知的接收者本人（任一项目角色含 viewer —— 标已读不是领域状态机写）。读取他人通知 id → `HT-RES-001`（不泄露存在性）。

##### 同步性

**同步完成。** `200`。通知投递本身异步（架构）；本命令只改已读投影。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须（可重试）。

NotificationRead:
  type: object
  additionalProperties: false
  properties: {}

NotificationReadResult:
  type: object
  required: [id, read]
  properties:
    id: { $ref: '#/UUID' }
    read: { type: boolean, const: true }
```

产品形态 G4 **TBD**；本契约只保证已读位。无 Restricted 正文。

##### 成功判定

- **完成**：`read=true`；API-022 角标递减（最终以 GET 为准）。
- 前端本地红点消失 **不是**权威。边界 §6 无独立「已读」行；属呈现协调。
- 已读再 POST：同 key 返回已有结果，不报业务错误。

##### 错误码

`HT-AUTH-001`、`HT-RES-001`、`HT-VAL-001`、`HT-IDEM-001`、`HT-QUOTA-002`。无 `HT-STATE`（无领域态）。

##### 幂等

`command_type = notification.mark_read`。必须 Key。append-only 审计可选；失败也审计若拒绝越权。

---

#### API-029 `PATCH /api/v1/projects/{project_id}/notification-subscriptions`

##### 鉴权 / 角色 / scope

- Sess。**角色**：`owner` / `admin`（项目设置）。`tester` / `viewer` → `HT-IAM-001`（未列出矩阵 fail-close）。
- 订阅是配置，不是通知对象。渠道主备在连接器（API-166），本接口只存项目偏好。

##### 同步性

**同步完成。** `200` 订阅资源。短配置，无长外部依赖。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

NotificationSubscriptionPatch:
  type: object
  required: [expected_version, channels]
  additionalProperties: false
  properties:
    expected_version:
      type: integer
      minimum: 1
      description: 订阅配置聚合版本（对外 version）。项目设置无独立页面对象时以本资源 version 为准，不得发明第 24 对象
    channels:
      type: array
      items:
        type: object
        required: [channel_id, enabled]
        properties:
          channel_id:
            $ref: '#/UUID'
            description: 已配置出站渠道 ID（API-165/166）；禁止内联 Webhook secret
          enabled: { type: boolean }
          event_categories:
            type: array
            items: { type: string }
            description: 类别对齐通知覆盖（审批、滞留、失效、Check Run、降级、导入导出完成等）；未冻结穷举 TBD，禁止发明领域对象名
```

响应含 `version`、`channels[]`（无 secret）。G4 站内形态 TBD。

##### 成功判定

- **完成**：GET API-019 返回相同偏好。通知**产生与投递**仍只在服务端（边界 §2.11）；本命令成功 ≠ 某条通知已送达。
- 对照 §6 无单独行；配置类以 GET 快照为准。

##### 错误码

`HT-AUTH-001`、`HT-IAM-001`、`HT-RES-001`、`HT-VAL-001`（未知 channel_id）、`HT-VER-001`、`HT-IDEM-001`。渠道未注册不得写 secret 绕过 → `HT-VAL-001`。

##### 幂等

`command_type = notification_subscription.patch`。必须 Key + CAS。

---

#### API-040 `PUT /api/v1/organizations/current/siem-export`

> 边界 §2.13 审计检索「配置 SIEM 外发」。**配置命令**，挂在当前 Organization 治理投影上，**不是**第 24 个领域对象，也不是 AuditEvent 的写接口（AuditEvent 仍 append-only，仅查询 API-024/025）。

##### 鉴权 / 角色 / scope

- Sess。**角色**：`owner`（组织级治理）。`admin` 是否可写 **未列出则 fail-close**：本契约仅 **owner**；`admin`/`tester`/`viewer` → `HT-IAM-001`。
- **禁止** ApiToken。

##### 同步性

**同步完成。** `200` 配置投影。外发**投递**异步（通知/连接器管道）；本 PUT 只持久化配置。受理配置 ≠ SIEM 侧已收到历史审计。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

SiemExportConfigPut:
  type: object
  required: [expected_version, enabled]
  additionalProperties: false
  properties:
    expected_version:
      type: integer
      minimum: 1
      description: Organization.version（CAS，§2.5）
    enabled: { type: boolean }
    destination_connector_id:
      $ref: '#/UUID'
      description: 已注册 Connector；enabled=true 时必填。禁止在本 body 传 endpoint 密钥、HMAC 明文、Webhook secret
    filter:
      type: object
      description: 可选；只引用可对外审计检索字段（actor_user_id / resource_type 等），禁止要求 Prompt / payload 秘密
      additionalProperties: false
      properties:
        resource_types:
          type: array
          items: { type: string }
        include_denied_attempts: { type: boolean }

SiemExportConfig:
  type: object
  required: [enabled, version]
  properties:
    enabled: { type: boolean }
    version: { $ref: '#/Version' }
    destination_connector_id:
      type: string
      format: uuid
      nullable: true
    credential_present:
      type: boolean
      description: 是否已绑定引用；永不返回 credential_ref 值
```

**无密钥明文。** 轮换密钥走连接器凭证通道（API-106 语义），不在本 PUT。

##### 成功判定

- **完成**：Organization 配置已更新，`API-010` 可投影「SIEM 外发已启用/未启用」（不得把内部实现细节塞进横幅）。
- **不构成**：历史 AuditEvent 已全部外发、SIEM 索引完成、保留期满删除（保留期 **TBD**，禁止写 90 天）。
- 对照边界 §2.13；§6 无独立 SIEM 行 → 以资源 GET / 组织投影为准。

##### 错误码

`HT-AUTH-001`、`HT-IAM-001`、`HT-VAL-001`（enabled 却无 connector、非法 filter）、`HT-RES-001`（connector 不可感知）、`HT-VER-001`、`HT-IDEM-001`、`HT-POL-001`（组织 kill 已关停连接器写入且本配置试图启用外发时 fail-close）。

##### 幂等

`command_type = organization.siem_export.put`。必须 Key + Organization CAS。

---

### 3. TestCase 写命令（并入 §7.4）

**总约束**：`ai-generated` 必须经 `PENDING_REVIEW`→`ACTIVE` 人工确认。**禁止**生成 / 导入 / 转脚本 / 保存草稿直写 `ACTIVE`（FR-05，无 `save=true` 路径）。`validity` **无**浏览器写 API（系统内部 §12）。Version 行不可覆盖；写的是新 Version + 指针。

---

#### API-032 `POST /api/v1/test-cases`

##### 鉴权 / 角色 / scope

- Sess。**角色**：`tester` / `admin` / `owner`。`viewer` → `HT-IAM-001`。
- 必须属于 `project_id` 的成员。

##### 同步性

**同步完成**（短事务：TestCase `DRAFT` + TestCaseVersion）。`200`/`201` 资源。A1 生成本身是 API-180 异步；本接口只采纳已编辑草稿落库。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

TestCaseCreate:
  type: object
  required: [project_id, case_type, execution_mode, title]
  additionalProperties: false
  properties:
    project_id: { $ref: '#/UUID' }
    generation_id:
      type: string
      format: uuid
      description: 可选；关联 A1 暂存，不是落库条件
    case_type:
      type: string
      enum: [api, web, performance, referenced]
    execution_mode:
      type: string
      enum: [script, agent]
    title: { type: string }
    priority:
      type: string
      enum: [P0, P1, P2, P3]
    tags:
      type: array
      items: { type: string }
      description: 客户端不得强制写入保留标签语义；ai-generated 由后端打
    drafts:
      type: array
      description: 编辑后的 A1 结构或手工步骤快照；禁止 save=true / lifecycle_status=ACTIVE
    job_binding:
      type: object
      description: referenced 型；无环境凭证明文
    jira_story_key: { type: string }
    script:
      type: object
      description: script 型步骤/脚本语义；正文分级 ≤Confidential；Restricted fail-close
    # 禁止字段：lifecycle_status、validity、current_version_id 客户端指定为 ACTIVE

TestCase:
  type: object
  required: [id, project_id, lifecycle_status, validity, version, current_version_id]
  properties:
    id: { $ref: '#/UUID' }
    project_id: { $ref: '#/UUID' }
    case_type: { type: string, enum: [api, web, performance, referenced] }
    execution_mode: { type: string, enum: [script, agent] }
    title: { type: string }
    priority: { type: string }
    tags: { type: array, items: { type: string } }
    lifecycle_status:
      type: string
      enum: [DRAFT, PENDING_REVIEW, ACTIVE, DEPRECATED]
    validity:
      type: string
      enum: [valid, invalid]
    jira_story_key: { type: string }
    current_version_id: { $ref: '#/UUID' }
    version: { $ref: '#/Version' }
    job_binding:
      type: object
      description: 非秘密绑定；无 credential
```

创建时 `lifecycle_status` **恒为** `DRAFT`。来自 A1 的采纳由后端打 `ai-generated`。

##### 成功判定

- **权威（边界 §6-1）**：返回 TestCase `DRAFT` + Version（含 `id` / `current_version_id` / `version`）。
- 前端「保存成功」提示 **不是**权威。
- **禁止**响应中出现 `ACTIVE`（本命令）。

##### 错误码

`HT-AUTH-001`、`HT-IAM-001`、`HT-RES-001`、`HT-VAL-001`（缺字段、Agent×非法组合由本接口若直接执行则拒）、`HT-VAL-004`（草稿 schema / evidence_refs 非法）、`HT-POL-001`（Restricted 出站/入库 fail-close）、`HT-QUOTA-001`（若扣配额）、`HT-IDEM-001`。
客户端传 `lifecycle_status=ACTIVE` → `HT-VAL-001`（不得发明直写路径）。

##### 幂等

`command_type = test_case.create_draft`。必须 Key。创建无 `expected_version`（无既有聚合）。

---

#### API-033 `PATCH /api/v1/test-cases/{test_case_id}`

##### 鉴权 / 角色 / scope

- Sess。`tester` / `admin` / `owner`。`viewer` → `HT-IAM-001`。
- **仅** `lifecycle_status=DRAFT` 允许改内容（新 Version + 指针）。`PENDING_REVIEW` / `ACTIVE` / `DEPRECATED` → `HT-STATE-001`。
- `ACTIVE` 的生产指针变更走 heal_apply（API-120 + 审批 + §12 Execute），**不是**本 PATCH。

##### 同步性

**同步完成。** `200` TestCase（新 `current_version_id`，`lifecycle_status` 仍为 `DRAFT`）。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

TestCasePatch:
  type: object
  required: [expected_version]
  additionalProperties: false
  properties:
    expected_version:
      type: integer
      minimum: 1
      description: TestCase.version（CAS）；Version 行本身禁止覆盖
    title: { type: string }
    priority: { type: string, enum: [P0, P1, P2, P3] }
    tags: { type: array, items: { type: string } }
    drafts: { type: array }
    job_binding: { type: object }
    jira_story_key: { type: string }
    script: { type: object }
    # 禁止：lifecycle_status、validity
```

响应同 `TestCase`。

##### 成功判定

- **完成**：新 Version 已追加且指针已更新；GET API-031 反映新步骤。生命周期仍为 `DRAFT`。
- 对照 §6 无独立「编辑」行；以资源 GET 为准。
- 不得把本命令成功解释为 heal 应用成功（那是 §6-12：`EXECUTED + execution_result=ok`）。

##### 错误码

`HT-STATE-001`（非 DRAFT）、`HT-VER-001`、`HT-VAL-001`/`HT-VAL-004`、`HT-IDEM-001`、`HT-IAM-001`、`HT-RES-001`、`HT-POL-001`（Restricted）。

##### 幂等

`command_type = test_case.patch_draft`。必须 Key + CAS。

---

#### API-034 `POST /api/v1/test-cases/{test_case_id}/submit-review`

##### 鉴权 / 角色 / scope

- Sess。`tester` / `admin` / `owner`。`viewer` → `HT-IAM-001`。
- 允许当前态：**仅** `DRAFT` → `PENDING_REVIEW`（problem_model §2.1）。其它态 `HT-STATE-001`。

##### 同步性

**同步完成。** `200` TestCase。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

TestCaseSubmitReview:
  type: object
  required: [expected_version]
  additionalProperties: false
  properties:
    expected_version: { type: integer, minimum: 1 }
```

响应 `TestCase`，`lifecycle_status=PENDING_REVIEW`。**仍不得为 ACTIVE。**

##### 成功判定

- **完成**：资源为 `PENDING_REVIEW`（边界 §2.2「提交评审」）。前端按钮态 **不是**权威。
- `ai-generated` 在此之后仍须 API-035 才能到 `ACTIVE`。

##### 错误码

`HT-STATE-001`、`HT-VER-001`、`HT-IDEM-001`、`HT-IAM-001`、`HT-RES-001`、`HT-VAL-001`。

##### 幂等

`command_type = test_case.submit_review`。必须 Key + CAS。

---

#### API-035 `POST /api/v1/test-cases/{test_case_id}/review`

##### 鉴权 / 角色 / scope

- Sess。**角色**：`admin` / `owner`（人工评审确认）。`tester` / `viewer` → `HT-IAM-001`（未列出「tester 可评审」则 fail-close）。
- 允许当前态：**仅** `PENDING_REVIEW`。通过 → `ACTIVE`；驳回 → `DRAFT`。
- 这是 TestCase 生命周期评审，**不是** ApprovalRequest 四眼（四眼用于 L2+ Preview/审批链）。

##### 同步性

**同步完成。** `200` TestCase。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

TestCaseReview:
  type: object
  required: [expected_version, decision]
  additionalProperties: false
  properties:
    expected_version: { type: integer, minimum: 1 }
    decision:
      type: string
      enum: [approve, reject]
    jira_story_key:
      type: string
      description: 可选；通过时可关联单向 Jira story
    reason: { type: string }
```

响应 `TestCase`：`approve` ⇒ `ACTIVE`；`reject` ⇒ `DRAFT`。

##### 成功判定

- **完成**：GET 为 `ACTIVE` 或 `DRAFT`（边界 §2.2 评审确认）。
- **禁止**用本接口把 `DRAFT` 直接标 `ACTIVE`（跳过 `PENDING_REVIEW`）→ `HT-STATE-001`。
- AI 生成路径：无本命令则永远不能因「生成成功」变为 `ACTIVE`。

##### 错误码

`HT-STATE-001`、`HT-VER-001`、`HT-VAL-001`、`HT-IDEM-001`、`HT-IAM-001`、`HT-RES-001`。

##### 幂等

`command_type = test_case.review`。必须 Key + CAS。

---

#### API-036 `POST /api/v1/test-cases/{test_case_id}/deprecate`

##### 鉴权 / 角色 / scope

- Sess。`tester` / `admin` / `owner`。`viewer` → `HT-IAM-001`。
- 允许当前态：`ACTIVE` → `DEPRECATED`（废弃）；`DRAFT` → `DEPRECATED`（弃用）。`PENDING_REVIEW` **无**该迁移（problem_model 未列）→ `HT-STATE-001`。已是 `DEPRECATED` → 同 key 返回已有，否则 `HT-STATE-001`。

##### 同步性

**同步完成。** `200` TestCase（`DEPRECATED`）。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

TestCaseDeprecate:
  type: object
  required: [expected_version]
  additionalProperties: false
  properties:
    expected_version: { type: integer, minimum: 1 }
    reason: { type: string }
```

`validity` 不变（与 DEPRECATED 分离）。

##### 成功判定

- **完成**：`lifecycle_status=DEPRECATED`。不可再被执行选项选为可跑（发起侧资格）。
- 对照边界 §2.2 废弃/弃用。

##### 错误码

`HT-STATE-001`、`HT-VER-001`、`HT-IDEM-001`、`HT-IAM-001`、`HT-RES-001`、`HT-VAL-001`。

##### 幂等

`command_type = test_case.deprecate`。必须 Key + CAS。

---

#### API-039 `POST /api/v1/test-cases/{test_case_id}/rollback`

##### 鉴权 / 角色 / scope

- Sess。**角色**：`admin` / `owner`（heal 回滚；未列出 tester 则 fail-close）。`viewer`/`tester` → `HT-IAM-001`。
- 更新 `current_version_id` 指向已存在 Version。`lifecycle_status` **不变**。
- **不得**用本接口绕过 `heal_apply` 审批去把未批准的草稿指针推到 `ACTIVE` 生产版本：目标 Version 必须已是合法快照（含 heal 事务内 rollback snapshot）。冲突 fail-close `HT-STATE-001` 或 `HT-POL-001`。

##### 同步性

**同步完成**（指针 CAS）。`200` TestCase。heal **应用**本身的权威成功是审批 `EXECUTED + execution_result=ok`（§6-12）；本接口是独立回滚命令，成功 = 指针已改。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

TestCaseRollback:
  type: object
  required: [expected_version, target_version_id]
  additionalProperties: false
  properties:
    expected_version:
      type: integer
      minimum: 1
      description: TestCase.version（current_version CAS）
    target_version_id: { $ref: '#/UUID' }
    reason: { type: string }
```

响应 `TestCase`（新指针）。写 AuditEvent。无 Restricted。

##### 成功判定

- **本命令完成**：`current_version_id = target_version_id` 且 CAS 已升版本；回滚后用例按该快照可执行（资格仍受 `lifecycle_status`/`validity`/环境约束）。
- **≠** §6-12 heal 应用成功（那是新 Version + 指针经审批 Execute）。
- 快照/CAS 失败 fail-close：资产保持原状。

##### 错误码

`HT-STATE-001`（目标 Version 不属于本用例 / 不允许）、`HT-VER-001`、`HT-RES-001`、`HT-VAL-001`、`HT-IDEM-001`、`HT-IAM-001`、`HT-POL-001`。

##### 幂等

`command_type = test_case.rollback_pointer`。必须 Key + CAS。

---

### 4. TestPlan 与 PerfBaseline 写命令（并入 §7.4 续）

#### API-052 `POST /api/v1/test-plans`

##### 鉴权 / 角色 / scope

- Sess。`tester` / `admin` / `owner`。`viewer` → `HT-IAM-001`。

##### 同步性

**同步完成。** `200`/`201` TestPlan。无问题模型状态机（编排资源）。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

TestPlanCreate:
  type: object
  required: [project_id, name]
  additionalProperties: false
  properties:
    project_id: { $ref: '#/UUID' }
    name: { type: string }
    jira_fix_version: { type: string }

TestPlan:
  type: object
  required: [id, project_id, name, version]
  properties:
    id: { $ref: '#/UUID' }
    project_id: { $ref: '#/UUID' }
    name: { type: string }
    jira_fix_version: { type: string }
    version: { $ref: '#/Version' }
    case_ids:
      type: array
      items: { $ref: '#/UUID' }
```

##### 成功判定

- **完成**：GET API-051 可读到该计划。创建 ≠ 已绑定用例集（API-054）≠ 已绑定定时（API-055）≠ 已发起执行。

##### 错误码

`HT-AUTH-001`、`HT-IAM-001`、`HT-RES-001`、`HT-VAL-001`、`HT-IDEM-001`。

##### 幂等

`command_type = test_plan.create`。必须 Key。无 CAS（新聚合）。

---

#### API-053 `PATCH /api/v1/test-plans/{test_plan_id}`

##### 鉴权 / 角色 / scope

- Sess。`tester` / `admin` / `owner`。`viewer` → `HT-IAM-001`。

##### 同步性

**同步完成。** `200` TestPlan。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

TestPlanPatch:
  type: object
  required: [expected_version]
  additionalProperties: false
  properties:
    expected_version: { type: integer, minimum: 1 }
    name: { type: string }
    jira_fix_version: { type: string }
```

用例集不在此 PATCH（走 API-054）。定时不在此（API-055）。

##### 成功判定

- **完成**：编排字段已持久化。历史 TestRun 快照不受影响（执行走冻结 snapshot）。

##### 错误码

`HT-VER-001`、`HT-VAL-001`、`HT-IDEM-001`、`HT-IAM-001`、`HT-RES-001`、`HT-STATE-001`（若未来冻结态；当前无状态机则少用）。

##### 幂等

`command_type = test_plan.patch`。必须 Key + CAS（§2.5 TestPlan）。

---

#### API-054 `PUT /api/v1/test-plans/{test_plan_id}/case-ids`

##### 鉴权 / 角色 / scope

- Sess。`tester` / `admin` / `owner`。`viewer` → `HT-IAM-001`。
- 用例须同租户同项目。不要求本命令把用例迁到 `ACTIVE`（资格在发起执行时复核）。

##### 同步性

**同步完成。** `200` TestPlan（含 `case_ids`）。全量替换列表。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

TestPlanCaseIdsPut:
  type: object
  required: [expected_version, case_ids]
  additionalProperties: false
  properties:
    expected_version: { type: integer, minimum: 1 }
    case_ids:
      type: array
      items: { $ref: '#/UUID' }
```

##### 成功判定

- **完成**：计划 ↔ 用例关联已替换。≠ 执行成功（§6-3/5）。

##### 错误码

`HT-VER-001`、`HT-VAL-001`（跨项目 ID）、`HT-RES-001`、`HT-IDEM-001`、`HT-IAM-001`。

##### 幂等

`command_type = test_plan.put_case_ids`。必须 Key + CAS。

---

#### API-055 `PUT /api/v1/test-plans/{test_plan_id}/schedule`

##### 鉴权 / 角色 / scope

- Sess。`tester` / `admin` / `owner`。`viewer` → `HT-IAM-001`。
- 绑定定时回归配置。到点触发是**系统**命令（`trigger_type=schedule`），不是本 PUT 立刻建 TestRun。
- cron / 时区等字段 **TBD**（`api_spec.md` 已标）；未批不得写默认频率。

##### 同步性

**同步完成**（配置落库）。`200`。调度运行时形态 M0/M1 **TBD**。本命令成功 ≠ 已产生 TestRun。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

TestPlanSchedulePut:
  type: object
  required: [expected_version]
  additionalProperties: false
  properties:
    expected_version: { type: integer, minimum: 1 }
    enabled: { type: boolean }
    schedule:
      type: object
      description: 表达式与时区字段 TBD；禁止发明未批默认「每天凌晨」等
      additionalProperties: true
    env_id:
      $ref: '#/UUID'
      description: 到点发起时使用的环境；须为当时 ACTIVE（到点再校验）
```

响应含 `enabled`、`version`，无密钥。

##### 成功判定

- **完成**：绑定可 GET。权威执行成功仍是到点后 TestRun `PENDING` 创建（§6-3），属系统入口，不是本响应。

##### 错误码

`HT-VER-001`、`HT-VAL-001`、`HT-RES-001`、`HT-IDEM-001`、`HT-IAM-001`、`HT-STATE-001`（env 当前非 ACTIVE 若在绑定时强校验；否则到点拒绝）。

##### 幂等

`command_type = test_plan.put_schedule`。必须 Key + CAS。

---

#### API-057 `POST /api/v1/perf-baselines`

##### 鉴权 / 角色 / scope

- Sess。`tester` / `admin` / `owner`。`viewer` → `HT-IAM-001`。
- 同场景唯一活跃：创建本行 `is_active=true` 时 **CAS 停用**旧活跃行（problem_model 约束 4）。禁止改写旧行 `metrics_snapshot`。

##### 同步性

**同步完成。** `200`/`201` 新基线。压测**发起**走 API-062（可能 API-120 `perf_high_risk`），不是本接口。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

PerfBaselineCreate:
  type: object
  required: [scenario_test_case_id, metrics_snapshot, tolerance]
  additionalProperties: false
  properties:
    scenario_test_case_id:
      $ref: '#/UUID'
      description: case_type=performance 的 TestCase
    metrics_snapshot:
      type: object
      description: 创建后不可变；无 Restricted
    tolerance:
      type: object
      description: RT/TPS 等
    expected_active_version:
      type: integer
      minimum: 1
      description: 可选；若该场景已有活跃基线，对其 CAS 停用（§2.5 PerfBaseline 活跃切换）

PerfBaseline:
  type: object
  required: [id, scenario_test_case_id, is_active, version]
  properties:
    id: { $ref: '#/UUID' }
    scenario_test_case_id: { $ref: '#/UUID' }
    is_active: { type: boolean }
    version: { $ref: '#/Version' }
    metrics_snapshot: { type: object }
    tolerance: { type: object }
```

##### 成功判定

- **完成**：新行 `is_active=true`；同场景旧活跃为 `false`。对比图数据以 GET 为准。
- ≠ 压测跑完、≠ 门禁通过。压测任务 **严禁自动重试**（即使基线创建成功）。

##### 错误码

`HT-VAL-001`（非 performance 用例）、`HT-VER-001`（旧活跃 CAS）、`HT-IDEM-001`、`HT-IAM-001`、`HT-RES-001`、`HT-STATE-001`。

##### 幂等

`command_type = perf_baseline.create`。必须 Key；活跃切换 CAS。

---

#### API-058 `POST /api/v1/perf-baselines/{perf_baseline_id}/deactivate`

##### 鉴权 / 角色 / scope

- Sess。`tester` / `admin` / `owner`。`viewer` → `HT-IAM-001`。
- 停用 `is_active`；**禁止**改 `metrics_snapshot`。

##### 同步性

**同步完成。** `200` PerfBaseline（`is_active=false`）。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

PerfBaselineDeactivate:
  type: object
  required: [expected_version]
  additionalProperties: false
  properties:
    expected_version: { type: integer, minimum: 1 }
```

##### 成功判定

- **完成**：该基线不再是场景活跃。允许场景暂无活跃基线（不发明「必须有活跃」状态）。

##### 错误码

`HT-STATE-001`（已停用且异 key）、`HT-VER-001`、`HT-IDEM-001`、`HT-IAM-001`、`HT-RES-001`。

##### 幂等

`command_type = perf_baseline.deactivate`。必须 Key + CAS。

---

### 5. TestRun 会话写命令（并入 §7.5）

#### API-062 `POST /api/v1/test-runs`

> 会话通道；`trigger_type` ∈ `manual` / `schedule`。Token 发起是 **API-080**（同路径，本分册不展开）。`ci_webhook` 由 API-090 观察 + §12，**禁止**本接口伪造。

##### 鉴权 / 角色 / scope

- **仅 Sess**。`tester` / `admin` / `owner`。`viewer` → `HT-IAM-001`。
- 前置资格（边界 §2.3）：用例 `ACTIVE` 且 `validity=valid`；环境 `ACTIVE`；OrgQuota slot/压测预算；Skill 生产版本（Agent）；模式×环境合法。**Agent × 外部 CI 一期不可用** → `HT-VAL-001` 或 `HT-POL-001`。

##### 同步性

**同步受理 + 异步完成执行。**

- 校验通过并落库：HTTP **`200`**（短事务已创建资源）+ TestRun（`status` 至少 `PENDING`，随即系统转入 `VALIDATING`）。
- 执行跑完、报告、聚类 **异步**；终态另判（§6-5）。
- 高危压测：须先 API-120 `perf_high_risk`；未带有效审批绑定 **不得**直接进入执行队列。白名单外目标 **`HT-POL-002`，不进审批**。
- 不得因「本地表单通过」视为 VALIDATING 成功（§6-4）。

压测型：**严禁自动重试**（平台不得在 FAILED/TIMEOUT 后自行再 POST 本接口）。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 强烈建议；会话可重试场景视为必须。

TestRunCreate:
  type: object
  required: [project_id, env_id, execution_source, case_ids]
  additionalProperties: false
  properties:
    project_id: { $ref: '#/UUID' }
    plan_id: { $ref: '#/UUID' }
    env_id: { $ref: '#/UUID' }
    execution_source:
      type: string
      enum: [script, agent, external_ci]
    trigger_type:
      type: string
      enum: [manual, schedule]
      description: 缺省 manual；禁止 api_token / ci_webhook
    case_ids:
      type: array
      items: { $ref: '#/UUID' }
    params:
      type: object
      description: 无秘密明文；引用 credential_ref 不得传值
    schedule:
      type: object
      description: 仅 trigger_type=schedule 的配置快照；到点仍系统触发
    expected_env_version:
      type: integer
      minimum: 1
      description: 环境 CAS；不匹配 HT-VER-001
    preview_id:
      type: string
      format: uuid
      description: 可选；perf_high_risk 等 Gate 已 ALLOW/已绑定审批时的 Preview 引用
    approval_request_id:
      type: string
      format: uuid
      description: 可选；不得用未 EXECUTED+ok 的审批冒充授权

TestRun:
  type: object
  required: [id, status, trigger_type, execution_source, version]
  properties:
    id: { $ref: '#/UUID' }
    project_id: { $ref: '#/UUID' }
    plan_id: { type: string, format: uuid }
    env_id: { $ref: '#/UUID' }
    execution_source: { type: string, enum: [script, agent, external_ci] }
    trigger_type: { type: string, enum: [manual, schedule, ci_webhook, api_token] }
    status:
      type: string
      enum:
        - PENDING
        - VALIDATING
        - RUNNING
        - WAITING_EXTERNAL
        - WAITING_APPROVAL
        - STOPPING
        - SUCCEEDED
        - FAILED
        - CANCELLED
        - TIMEOUT
    version: { $ref: '#/Version' }
    snapshot_ref:
      type: object
      description: 冻结引用摘要；受理后禁止改写 snapshot
    gate_evaluation_id:
      type: string
      format: uuid
      nullable: true
      description: agent 源恒 null
```

可同时返回 `CommandReceipt`（`status=accepted`，`resource_type=TestRun`）。**禁止**在响应中出现 execution intent。

`params` / snapshot **无**环境凭证值。

##### 成功判定

- **受理权威（边界 §6-3）**：TestRun 已创建并返回 `id`，`status` 至少 `PENDING`，snapshot 已冻结。前端跳转 P09 **不是**权威。
- **≠ 完成**：终态 ∈ `SUCCEEDED / FAILED / CANCELLED / TIMEOUT`（§6-5）。前端不得用进度条推定。
- **§6-4**：本地校验通过 ≠ `VALIDATING`→`RUNNING`；校验失败系统迁 `FAILED` + 结构化原因（可能已过本 HTTP 响应，须 GET）。
- 压测排队（场景互斥）= 受理后等待，**不是** DENY；白名单外 = 本命令失败 `HT-POL-002`。

##### 错误码

| code | 何时 |
| --- | --- |
| `HT-IAM-001` | viewer 或非成员 |
| `HT-VAL-001` | trigger 非法、Agent×external_ci |
| `HT-VAL-002` | Job Schema / 变量 / Job 不存在（若同步暴露；否则落 VALIDATING→FAILED） |
| `HT-STATE-001` | 环境非 ACTIVE；用例非 ACTIVE / invalid |
| `HT-VER-001` | `expected_env_version` |
| `HT-QUOTA-001` | slot / 压测并发 / Token 预算 |
| `HT-POL-001` | Gate DENY（未声明副作用等） |
| `HT-POL-002` | 压测白名单外目标 |
| `HT-IDEM-001` | 同 key 异 hash |
| `HT-APPR-001` | 绑定审批 param_hash 失效 |

##### 幂等

`command_type = test_run.start_session`。必须/强烈建议 Key。创建后 TestRun 自身后续迁移用 CAS（取消见 API-063）。

---

#### API-063 `POST /api/v1/test-runs/{test_run_id}/cancel`

##### 鉴权 / 角色 / scope

- Sess。`tester` / `admin` / `owner`。`viewer` → `HT-IAM-001`。
- 人工取消 / 终止（含 Agent 终止、压测熔断由系统也可写 STOPPING；本接口是人工信号）。

##### 同步性

**同步受理信号 + 异步停止完成。** HTTP **`202`**（或 `200` + Receipt `accepted`，以 Receipt 为准）：终止信号已持久化。

- **受理** = 信号落库（`stop_signal_at` 等），多 Worker 可停。前端「信号已持久化送达」= 受理反馈（边界 §2.4、§6-8 **非**终止完成）。
- **完成** = TestRun 进入 **`CANCELLED`**（可经 `STOPPING`）**或**停止卡死心跳兜底 **`TIMEOUT`**（`STOPPING` 是活跃态，不得永久停留）。
- `VALIDATING` **无独立取消边**；发起后立即取消统一按 `PENDING`→`CANCELLED` 口径吸收（problem_model 裁定 7）。客户端对 VALIDATING 取消：不提供第二套命令，服务端按当前态裁决或 `HT-STATE-001` 后 GET 对账。
- `STOPPING` 中 **禁止**再创建新终止动作；同 `Idempotency-Key` 返回同一回执。
- 终态再取消 → `HT-STATE-001`。
- `WAITING_APPROVAL`：人工取消 → `CANCELLED`（审批过期 **不**自动迁 CANCELLED）。
- `WAITING_EXTERNAL`：幂等取消；已产生构建记录照常采集入库。
- 已采集部分结果照常可见；迟到结果不重开 run。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

TestRunCancel:
  type: object
  required: [expected_version]
  additionalProperties: false
  properties:
    expected_version:
      type: integer
      minimum: 1
      description: TestRun.version（状态迁移 CAS）
    reason: { type: string }

# 202
# data 同时含 CommandReceipt 与可选当前 TestRun 快照（可能仍为 RUNNING/STOPPING/PENDING）
TestRunCancelAccepted:
  type: object
  required: [receipt, test_run]
  properties:
    receipt:
      $ref: '#/CommandReceipt'
      description: status=accepted 表示信号已持久化，不是 CANCELLED
    test_run:
      $ref: '#/TestRun'
```

`CommandReceipt.poll.sse_path` 可指向 API-210；完成以 GET API-061 为准。

##### 成功判定

| 层次 | 含义 | 对照 |
| --- | --- | --- |
| 受理 | Receipt `accepted`；信号持久化 | 前端即时反馈；**不是** §6-8 权威 |
| 完成 | `status=CANCELLED`（经 `STOPPING` 若从 RUNNING）或兜底 `TIMEOUT` | 边界 §6-8；问题模型 STOPPING 出边 |
| 非完成 | 仍 `STOPPING` / 等待采集 | 须 SSE+GET；禁止把 202 当 CANCELLED |

已采集结果入库成功 **独立于** run 终态。

##### 错误码

`HT-STATE-001`（终态 / 非法当前态 / VALIDATING 无独立边时的对账）、`HT-VER-001`、`HT-IDEM-001`、`HT-IAM-001`、`HT-RES-001`、`HT-VAL-001`。
压测停止同样 **禁止**自动再拉起（无自动重试）。

##### 幂等

`command_type = test_run.cancel`。必须 Key + CAS。STOPPING 重复 = 同一 Receipt。

---

#### API-068 `POST /api/v1/test-runs/{test_run_id}/script-drafts`

##### 鉴权 / 角色 / scope

- Sess。`tester` / `admin` / `owner`。`viewer` → `HT-IAM-001`。
- 轨迹 → 新 TestCase **`DRAFT`**。原 TestRun **状态不变**。
- **禁止**直写 `ACTIVE`。

##### 同步性

**同步完成**（新草稿落库）或轨迹校验失败同步拒绝。`200` 新 TestCase。不把原 run 改为终态。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

ScriptDraftFromRun:
  type: object
  additionalProperties: false
  properties:
    expected_run_version:
      type: integer
      minimum: 1
      description: 可选；防止对已变轨迹盲写。TestRun CAS 若用于本命令则必填；未发送时仍须校验轨迹 schema
    title: { type: string }

# 响应：TestCase（DRAFT）+ 原 test_run_id 引用
```

须通过轨迹→脚本产物 schema 校验（A8 结构脱敏后）。无秘密参数原文。

##### 成功判定

- **完成**：新用例 `DRAFT` + Version（可走后续 API-034/035）。原 run 终态/进行态不变。
- 对照边界 §2.4。AI/生成标签由后端按来源打，仍禁止 ACTIVE。

##### 错误码

`HT-VAL-004`（schema）、`HT-STATE-001`（无可用轨迹 / incomplete 不允许转时 — 若不允许须明示；未批则 fail-close 拒）、`HT-IDEM-001`、`HT-IAM-001`、`HT-RES-001`、`HT-VER-001`（若带 run version）。

##### 幂等

`command_type = test_run.to_script_draft`。必须 Key。

---

### 6. ExecutionEnvironment 写命令

> API-102 含 L3 Gate；**Execute / intent 无本路径**。ACTIVE 仅当 `env_register` 审批 `EXECUTED + execution_result=ok`（§12）。

#### API-102 `POST /api/v1/execution-environments`

##### 鉴权 / 角色 / scope

- Sess。**角色**：`admin` / `owner`（环境注册）。`tester` / `viewer` → `HT-IAM-001`。
- 类 2+3：须经 API-120 Preview 或内联 Gate。未声明 sideEffectLevel → DENY。

##### 同步性

**同步完成创建** `PENDING_APPROVAL`（短事务）。HTTP `200`。
**≠** 环境可用：`ACTIVE` 只在内部 Execute 成功后。客户端不得把 200 当「已可发起 TestRun」。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

ExecutionEnvironmentCreate:
  type: object
  required: [env_type, name, scope_level]
  additionalProperties: false
  properties:
    env_type:
      type: string
      enum: [platform_executor, external_ci]
    name: { type: string }
    endpoint:
      type: string
      description: 非密钥
    scope_level:
      type: string
      enum: [organization, project]
    job_contracts:
      type: array
      description: Job 契约；无凭证值
    preview_id: { type: string, format: uuid }
    credential_ref_present:
      type: boolean
      description: 仅声明已走机密通道绑定；禁止 credential 明文 / credential_ref 值
    # 禁止：status=ACTIVE、standing_auth 当作永久豁免

ExecutionEnvironment:
  type: object
  required: [id, env_type, status, version, has_credential]
  properties:
    id: { $ref: '#/UUID' }
    env_type: { type: string, enum: [platform_executor, external_ci] }
    name: { type: string }
    status:
      type: string
      enum: [PENDING_APPROVAL, ACTIVE, DEGRADED, DISABLED]
    version: { $ref: '#/Version' }
    has_credential: { type: boolean }
    endpoint: { type: string }
    health_status: { type: object }
```

响应 **永不**含 `credential_ref` 值。创建时 `status` **必须**为 `PENDING_APPROVAL`（禁止客户端指定 ACTIVE）。

不发明 `DEGRADED→ACTIVE` 恢复边（Proposed）。

##### 成功判定

- **本命令完成**：资源存在且为 `PENDING_APPROVAL`。
- **环境可用完成**：内部 `env_register` Execute `ok` 后 `ACTIVE`（§6 无单独行；资格在 API-069）。
- Preview `DENY` → 本命令不得落 ACTIVE，亦不得静默跳过审批。

##### 错误码

`HT-POL-001` / `HT-POL-002`（未声明）、`HT-AUTH-002`（L3+ 窗口）、`HT-VAL-001`、`HT-IDEM-001`、`HT-IAM-001`、`HT-RES-001`。禁止 `HT-STATE` 把 ACTIVE 当创建结果。

##### 幂等

`command_type = execution_environment.register`。必须 Key。无创建时 expected_version。**无** intent API。

---

#### API-103 `POST /api/v1/execution-environments/{environment_id}/disable`

##### 鉴权 / 角色 / scope

- Sess。`admin` / `owner`。`tester` / `viewer` → `HT-IAM-001`。
- 目标态：`DISABLED`（问题模型：`ACTIVE`→…→`DISABLED`；健康失败可由系统写 `DEGRADED`，本接口是管理员停用）。
- **只挡新 run**；在途 `RUNNING` / `WAITING_EXTERNAL` **不中断**。

##### 同步性

**同步完成**停用位。`200` 环境资源 `DISABLED`。在途 run 完成仍异步。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

ExecutionEnvironmentDisable:
  type: object
  required: [expected_version]
  additionalProperties: false
  properties:
    expected_version: { type: integer, minimum: 1 }
    reason: { type: string }
```

响应 `ExecutionEnvironment`，`has_credential` 布尔，无引用值。不发明 `DISABLED→ACTIVE` 边；恢复未批准前禁止本接口反向操作。

##### 成功判定

- **完成**：`status=DISABLED`；API-069 不可选或带 `unavailable_reason`。
- ≠ 在途 TestRun 已 CANCELLED。

##### 错误码

`HT-STATE-001`（已 DISABLED 异参数 / 非法源态）、`HT-VER-001`、`HT-IDEM-001`、`HT-IAM-001`、`HT-RES-001`。

##### 幂等

`command_type = execution_environment.disable`。必须 Key + CAS。

---

### 7.W.FC FailureCluster 人工修正

#### API-132 `PATCH /api/v1/failure-clusters/{failure_cluster_id}`

##### 鉴权 / 角色 / scope

- Sess。`tester` / `admin` / `owner`。`viewer` → `HT-IAM-001`。
- **本地编辑未提交不调 API**（边界 §5.2）。本接口只追加 `correction_history`。
- 无生命周期状态机。`jira_write` / `heal_apply` **不**在本 PATCH。

##### 同步性

**同步完成。** `200` 簇。append `correction_history`；无 CAS 覆盖簇生成行的 category 而不留痕——修正必须 old→new。

FailureCluster 不在 §2.5 CAS 必带列表（非 TestRun 覆盖）；若实现给簇 `version` 则带 `expected_version`，否则以 `correction_history` 追加幂等。本契约：**若响应暴露 `version` 则请求必带 `expected_version`**，避免静默覆盖。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

FailureClusterPatch:
  type: object
  required: [corrections]
  additionalProperties: false
  properties:
    expected_version:
      type: integer
      minimum: 1
      description: 若簇对外暴露 version 则必填
    corrections:
      type: array
      minItems: 1
      items:
        type: object
        required: [field, new]
        properties:
          field:
            type: string
            description: category / blocking_judgment / root_cause 等已有字段；禁止发明枚举
          old: { description: 服务端校验须匹配当前值 }
          new:
            description: category 新值 ⊆ 七值枚举
```

响应含 `correction_history[]`（actor / field / old / new / timestamp）。`category` 新值 ⊆ 七值。不得删历史簇。

##### 成功判定

- **完成**：历史可查；GET API-131 含新 correction。原 A2 值留痕。
- ≠ 缺陷已建（jira_write）、≠ heal 已应用。

##### 错误码

`HT-VAL-001`（category 非法、old 不匹配）、`HT-VER-001`、`HT-IDEM-001`、`HT-IAM-001`、`HT-RES-001`、`HT-STATE-001`（无）。

##### 幂等

`command_type = failure_cluster.correct`。必须 Key。

---

### 8. QualityGatePolicy 写命令

策略修改 **不改写** 历史 GateEvaluation。`mode` 切 `blocking` 须显式确认。豁免走 Preview `gate_waiver`，不在本分册。

#### API-142 `POST /api/v1/quality-gate-policies`

##### 鉴权 / 角色 / scope

- Sess。`admin` / `owner`。`tester` / `viewer` → `HT-IAM-001`（门禁策略 blocking 矩阵：tester 否）。

##### 同步性

**同步完成。** `200`/`201` 策略。上线初期仅报告：创建 `blocking` 仍须 `confirm_blocking: true`。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

QualityGatePolicyCreate:
  type: object
  required: [project_id, thresholds, mode, scope]
  additionalProperties: false
  properties:
    project_id: { $ref: '#/UUID' }
    thresholds:
      type: object
      required: [min_pass_rate, max_p95_ms, max_error_rate]
      properties:
        min_pass_rate: { type: number }
        max_p95_ms: { type: number }
        max_error_rate: { type: number }
    mode:
      type: string
      enum: [report_only, blocking]
    scope: { type: object }
    confirm_blocking:
      type: boolean
      description: mode=blocking 时必须 true；缺省或 false → HT-VAL-001

QualityGatePolicy:
  type: object
  required: [id, project_id, mode, policy_version, version]
  properties:
    id: { $ref: '#/UUID' }
    project_id: { $ref: '#/UUID' }
    thresholds: { type: object }
    mode: { type: string, enum: [report_only, blocking] }
    scope: { type: object }
    policy_version: { type: integer }
    version: { $ref: '#/Version' }
```

无 `result=not_evaluated`。评估生成是 §12。

##### 成功判定

- **完成**：策略可 GET。≠ 某次 TestRun 门禁已通过（§6-9：可评估时才有 `pass/fail/waived`；缺评估不得默认通过）。

##### 错误码

`HT-VAL-001`（blocking 未确认）、`HT-IAM-001`、`HT-RES-001`、`HT-IDEM-001`。

##### 幂等

`command_type = quality_gate_policy.create`。必须 Key。

---

#### API-143 `PATCH /api/v1/quality-gate-policies/{policy_id}`

##### 鉴权 / 角色 / scope

- Sess。`admin` / `owner`。`tester` / `viewer` → `HT-IAM-001`。
- 修改升 `policy_version`；历史评估不变。切 `blocking` 必须 `confirm_blocking: true`。

##### 同步性

**同步完成。** `200` 新策略版本（同一 id，版本字段递增）。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

QualityGatePolicyPatch:
  type: object
  required: [expected_version]
  additionalProperties: false
  properties:
    expected_version: { type: integer, minimum: 1 }
    thresholds: { type: object }
    mode: { type: string, enum: [report_only, blocking] }
    scope: { type: object }
    confirm_blocking: { type: boolean }
```

##### 成功判定

- **完成**：新 `policy_version` 可查。旧 GateEvaluation.policy_snapshot 不变。
- ≠ 豁免成功（§6-13）。

##### 错误码

`HT-VER-001`、`HT-VAL-001`、`HT-IDEM-001`、`HT-IAM-001`、`HT-RES-001`、`HT-STATE-001`。

##### 幂等

`command_type = quality_gate_policy.patch`。必须 Key + CAS（§2.5）。

---

### 9. ReleaseTask 写命令

无「执行生产发布」路径。`release_push` 确认走 API-120，不在本分册。READY ≠ 生产已发布。

#### API-152 `POST /api/v1/release-tasks`

##### 鉴权 / 角色 / scope

- Sess。`tester` / `admin` / `owner`。`viewer` → `HT-IAM-001`。M3。

##### 同步性

**同步完成创建** `DRAFT` + **范围快照冻结**。`200`/`201`。
Readiness / A5 草稿由系统异步推进到 `PENDING_CONFIRM`（禁止本接口自动推送 Release 系统）。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

ReleaseTaskCreate:
  type: object
  required: [project_id, jira_version_ref]
  additionalProperties: false
  properties:
    project_id: { $ref: '#/UUID' }
    jira_version_ref: { type: string }

ReleaseTask:
  type: object
  required: [id, status, version, jira_version_ref]
  properties:
    id: { $ref: '#/UUID' }
    project_id: { $ref: '#/UUID' }
    status:
      type: string
      enum: [DRAFT, PENDING_CONFIRM, SUBMITTED, READY, FAILED_RETRYABLE, CANCELLED]
    version: { $ref: '#/Version' }
    jira_version_ref: { type: string }
    scope_snapshot: { type: object }
    notes_draft: { type: string, description: A5 只读呈现；本创建可为空 }
```

创建后 `status=DRAFT`。`scope_snapshot` 此后禁止改写。

##### 成功判定

- **完成**：任务 `DRAFT` 且范围已冻。≠ Readiness 通过（§6-10）≠ `SUBMITTED→READY`（§6-11，webhook 观察 + 内部命令）。

##### 错误码

`HT-VAL-001`、`HT-RES-001`、`HT-IDEM-001`、`HT-IAM-001`、`HT-EXT-001`（读 Jira 范围失败且未落草稿时）。

##### 幂等

`command_type = release_task.create`。必须 Key。

---

#### API-153 `POST /api/v1/release-tasks/{release_task_id}/retries`

##### 鉴权 / 角色 / scope

- Sess。`tester` / `admin` / `owner`。`viewer` → `HT-IAM-001`。
- 允许当前态：**仅** `FAILED_RETRYABLE` → 再入 `SUBMITTED`（人工幂等重试）。其它态 `HT-STATE-001`。
- **无**浏览器 Execute；prepare 由内部命令消费稳定幂等键。禁止自动重试循环。

##### 同步性

**同步受理 + 异步 prepare。** HTTP `202` + Receipt。
领域完成：再次 `SUBMITTED` 后由 webhook 观察迁 `READY` 或再回 `FAILED_RETRYABLE`（§6-11 权威是 `SUBMITTED→READY`，不是本 202）。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须（防重复创建外部 item）。

ReleaseTaskRetry:
  type: object
  required: [expected_version]
  additionalProperties: false
  properties:
    expected_version: { type: integer, minimum: 1 }
    reason: { type: string }
```

响应 `CommandReceipt` + `ReleaseTask`（可能已是 `SUBMITTED`）。**不**暴露 intent。

##### 成功判定

- **受理**：命令接受，重试已登记。
- **prepare 成功权威**：`READY`（外部 item 准备完成），**不是**生产发布。
- `unknown` 外部结果禁止盲再点本接口当失败重试（须对账）。

##### 错误码

`HT-STATE-001`、`HT-VER-001`、`HT-IDEM-001`、`HT-EXT-002`（unknown 未对账）、`HT-IAM-001`、`HT-RES-001`、`HT-POL-001`。

##### 幂等

`command_type = release_task.retry_prepare`。必须 Key + CAS。

---

#### API-154 `POST /api/v1/release-tasks/{release_task_id}/cancel`

##### 鉴权 / 角色 / scope

- Sess。`tester` / `admin` / `owner`。`viewer` → `HT-IAM-001`。
- 允许当前态：`PENDING_CONFIRM` / `FAILED_RETRYABLE` → `CANCELLED`。`DRAFT` 是否可取消：问题模型未列 DRAFT→CANCELLED → **fail-close** `HT-STATE-001`（不发明边）。`SUBMITTED`/`READY` 取消未列 → `HT-STATE-001`。`CANCELLED` 吸收；迟到 READY 只记 divergence。

##### 同步性

**同步完成**领域态到 `CANCELLED`（短事务）或 `202` 若仍需对账外部分叉。本契约：状态机写入 **同步 `200`**；外部分叉记录异步不阻断 `CANCELLED`。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

ReleaseTaskCancel:
  type: object
  required: [expected_version]
  additionalProperties: false
  properties:
    expected_version: { type: integer, minimum: 1 }
    reason: { type: string }
```

响应 `ReleaseTask` `CANCELLED`。READY ≠ 本命令目标。

##### 成功判定

- **完成**：`status=CANCELLED`。≠ 外部 item 已删除。迟到 READY 不覆盖取消。

##### 错误码

`HT-STATE-001`、`HT-VER-001`、`HT-IDEM-001`、`HT-IAM-001`、`HT-RES-001`。

##### 幂等

`command_type = release_task.cancel`。必须 Key + CAS。

---

### 10. Connector 与绑定写命令

无凭证明文。HMAC secret 只存引用。egress 白名单限定已注册域。

#### API-162 `POST /api/v1/connectors`

##### 鉴权 / 角色 / scope

- Sess。`admin` / `owner`。`tester` / `viewer` → `HT-IAM-001`。

##### 同步性

**同步完成注册**（配置）。`200`/`201`。健康探活异步；本 200 ≠ 健康绿。凭证绑定走 API-106 语义（body 无明文）。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

ConnectorCreate:
  type: object
  required: [type, name, auth_method, action_contract]
  additionalProperties: false
  properties:
    type:
      type: string
      enum: [jira, github, ci, release]
    name: { type: string }
    auth_method: { type: string }
    action_contract:
      type: object
      description: sideEffectLevel / supportsPreview / Idempotency / Compensation；未声明副作用默认 DENY
    has_credential_binding: { type: boolean }
    # 禁止：credential、webhook_secret、credential_ref 值

Connector:
  type: object
  required: [id, type, name, version, has_credential]
  properties:
    id: { $ref: '#/UUID' }
    type: { type: string, enum: [jira, github, ci, release] }
    name: { type: string }
    version: { $ref: '#/Version' }
    has_credential: { type: boolean }
    has_webhook_secret: { type: boolean }
    outbound_write_enabled: { type: boolean }
    health_status: { type: object }
    action_contract: { type: object }
```

##### 成功判定

- **完成**：连接器可 GET，无 secret。≠ 出站已通、≠ 已触发 TestRun。

##### 错误码

`HT-VAL-001`、`HT-POL-001`（契约未声明）、`HT-IDEM-001`、`HT-IAM-001`、`HT-RES-001`。

##### 幂等

`command_type = connector.register`。必须 Key。

---

#### API-163 `PATCH /api/v1/connectors/{connector_id}`

##### 鉴权 / 角色 / scope

- Sess。`admin` / `owner`。`tester` / `viewer` → `HT-IAM-001`。
- 更新契约 / `config_version`。旧 webhook 按绑定版本解析。

##### 同步性

**同步完成。** `200` Connector。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

ConnectorPatch:
  type: object
  required: [expected_version]
  additionalProperties: false
  properties:
    expected_version: { type: integer, minimum: 1 }
    name: { type: string }
    action_contract: { type: object }
    outbound_write_enabled:
      type: boolean
      description: 连接器写入关停属 kill 位：本字段收紧可与 API-199 协同；**放开写入**须走 restore 审批，禁止用本 PATCH 把 false→true 当 L1 恢复（与 API-199 不对称纪律一致，冲突 fail-close HT-POL-001）
```

无 secret 字段。

##### 成功判定

- **完成**：新 `version`/`config_version`。历史投递记录不改写。

##### 错误码

`HT-VER-001`、`HT-VAL-001`、`HT-POL-001`（试图无审批放开 outbound）、`HT-IDEM-001`、`HT-IAM-001`、`HT-RES-001`、`HT-STATE-001`。

##### 幂等

`command_type = connector.patch`。必须 Key + CAS。

---

#### API-166 `PUT /api/v1/connectors/{connector_id}/outbound-channels`

##### 鉴权 / 角色 / scope

- Sess。`admin` / `owner`。`tester` / `viewer` → `HT-IAM-001`。
- 出站通知渠道主备。通知产生仍服务端。

##### 同步性

**同步完成配置。** `200`。投递异步。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

OutboundChannelsPut:
  type: object
  required: [expected_version, channels]
  additionalProperties: false
  properties:
    expected_version:
      type: integer
      minimum: 1
      description: Connector.version
    channels:
      type: array
      items:
        type: object
        required: [kind, is_primary]
        properties:
          kind: { type: string }
          is_primary: { type: boolean }
          endpoint_ref:
            type: string
            description: 已登记出口引用；禁止 URL+密钥内联
```

响应渠道列表无 secret。

##### 成功判定

- **完成**：GET API-165 一致。≠ 某条通知已投递成功。

##### 错误码

`HT-VER-001`、`HT-VAL-001`、`HT-IDEM-001`、`HT-IAM-001`、`HT-RES-001`、`HT-POL-001`。

##### 幂等

`command_type = connector.put_outbound_channels`。必须 Key + Connector CAS。

---

#### API-167 `PUT /api/v1/projects/{project_id}/ci-trigger-bindings`

##### 鉴权 / 角色 / scope

- Sess。`admin` / `owner`。`tester` / `viewer` → `HT-IAM-001`（集成绑定 fail-close）。
- 仓库/分支 ↔ 计划。匹配后由 API-090 观察触发内部 `ci_webhook` 受理，**本 PUT 不直接起 TestRun**。

##### 同步性

**同步完成绑定配置。** `200`。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

CiTriggerBindingsPut:
  type: object
  required: [expected_version, bindings]
  additionalProperties: false
  properties:
    expected_version:
      type: integer
      minimum: 1
      description: 绑定配置 version（项目集成配置，非第 24 对象）
    bindings:
      type: array
      items:
        type: object
        required: [repository, ref_pattern, test_plan_id]
        properties:
          repository: { type: string }
          ref_pattern: { type: string }
          test_plan_id: { $ref: '#/UUID' }
          connector_id: { $ref: '#/UUID' }
```

##### 成功判定

- **完成**：绑定可查。≠ TestRun 已创建（那是 webhook+§12，成功口径同 §6-3）。

##### 错误码

`HT-VER-001`、`HT-VAL-001`、`HT-RES-001`、`HT-IDEM-001`、`HT-IAM-001`。

##### 幂等

`command_type = project.put_ci_trigger_bindings`。必须 Key + CAS。

---

### 11. ApiToken 管理

#### API-171 `POST /api/v1/api-tokens`

##### 鉴权 / 角色 / scope

- Sess。`admin` / `owner`。`tester` / `viewer` → `HT-IAM-001`。
- **token 明文仅本响应出现一次**。之后列表/GET **永不**返回 `token` / `token_hash`。

##### 同步性

**同步完成签发。** `200`。限流见 §11。`last_used_at` 初始空。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

ApiTokenCreate:
  type: object
  required: [scopes, project_ids, expires_at]
  additionalProperties: false
  properties:
    scopes:
      type: array
      items:
        type: string
        enum: [read, write, execute, delete]
    project_ids:
      type: array
      items: { $ref: '#/UUID' }
      description: 白名单；空数组语义 TBD，禁止默认「全部项目」——空数组须 HT-VAL-001 直至冻结
    expires_at:
      type: string
      format: date-time
      description: 必填绝对时间；禁止服务端填未批默认「90 天」
    name: { type: string }

ApiTokenIssued:
  type: object
  required: [id, token, token_prefix, scopes, project_ids, expires_at]
  properties:
    id: { $ref: '#/UUID' }
    token:
      type: string
      description: 仅此响应一次；客户端须自行保存
    token_prefix: { type: string }
    scopes:
      type: array
      items: { type: string, enum: [read, write, execute, delete] }
    project_ids:
      type: array
      items: { $ref: '#/UUID' }
    expires_at: { type: string, format: date-time }
    revoked_at:
      type: string
      format: date-time
      nullable: true
```

错误与后续查询不得回显 `token`。

##### 成功判定

- **完成**：哈希已存；调用方持有唯一明文。再 GET 无明文仍算签发成功（以 `id`+`token_prefix` 为准）。
- Token **不能**替代审批。

##### 错误码

`HT-VAL-001`（空 project_ids、非法 expires）、`HT-IAM-001`、`HT-IDEM-001`、`HT-QUOTA-002`（签发限流）、`HT-RES-001`。

##### 幂等

`command_type = api_token.issue`。必须 Key。同 key 同 hash **不得第二次返回明文**（返回已有元数据且 `token` 缺省，并明示不可再取明文）。

---

#### API-172 `POST /api/v1/api-tokens/{api_token_id}/revocations`

##### 鉴权 / 角色 / scope

- Sess。`admin` / `owner`。`tester` / `viewer` → `HT-IAM-001`。
- 吊销**即时**生效。`delete` scope 语义是吊销类，不能物理删审计。

##### 同步性

**同步完成。** `200` 元数据（`revoked_at` 非空）。无明文。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

ApiTokenRevoke:
  type: object
  additionalProperties: false
  properties:
    reason: { type: string }

ApiToken:
  type: object
  required: [id, token_prefix, revoked_at]
  properties:
    id: { $ref: '#/UUID' }
    token_prefix: { type: string }
    scopes: { type: array }
    project_ids: { type: array }
    expires_at: { type: string, format: date-time }
    revoked_at: { type: string, format: date-time }
    last_used_at:
      type: string
      format: date-time
      description: 异步，非审计替代
  # 无 token、无 token_hash
```

##### 成功判定

- **完成**：持该 Token 的后续调用 `HT-IAM-004` / `HT-AUTH-001`。即时，不以 `last_used_at` 为准。

##### 错误码

`HT-RES-001`、`HT-IAM-001`、`HT-IDEM-001`、`HT-STATE-001`（已吊销同结果幂等）。无 CAS 覆盖哈希。

##### 幂等

`command_type = api_token.revoke`。必须 Key。

---

### 12. Skill 发布、ModelRoute、kill switch 关停

#### API-195 `POST /api/v1/skill-versions/{skill_version_id}/publications`

##### 鉴权 / 角色 / scope

- Sess。三级发布（problem_model）：`personal` → `team`（Owner 审核）→ `org`（管理员+安全）。
- `personal`：`tester`+ 且为版本作者（未列出作者规则则：tester/admin/owner）。
- `team`：`owner`。
- `org`：`admin` / `owner`。
- `viewer` 一律 `HT-IAM-001`。
- 未版本化不进生产：`published_scope` 空草稿允许改；非空后 **禁止 UPDATE** 该 Version 行（新发布 = 新 Version 或指针 CAS）。

##### 同步性

**同步完成指针/scope 更新**（短事务）。金标准测试执行可异步；未完成不得把 org 生产指针切过去（fail-close `HT-STATE-001`）。M4。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

SkillPublication:
  type: object
  required: [expected_version, published_scope]
  additionalProperties: false
  properties:
    expected_version:
      type: integer
      minimum: 1
      description: Skill 聚合发布指针 CAS（§2.5）
    published_scope:
      type: string
      enum: [personal, team, org]
    gold_standard_ok:
      type: boolean
      description: org 级须服务端核实测试结果，客户端 true 不构成授权

SkillVersionPublished:
  type: object
  required: [id, skill_id, published_scope, version]
  properties:
    id: { $ref: '#/UUID' }
    skill_id: { $ref: '#/UUID' }
    published_scope:
      type: string
      enum: [personal, team, org]
    version: { $ref: '#/Version' }
    current_published_version_id: { $ref: '#/UUID' }
```

无 instructions 全量转储义务以外的最小化；**无** Prompt。已发布行禁止覆盖。

##### 成功判定

- **完成**：`published_scope` 已设且生产指针仅指向已发布 Version。≠ Agent TestRun 已跑。
- 跳级（personal→org 无 team）未批准则 `HT-STATE-001`。

##### 错误码

`HT-STATE-001`、`HT-VER-001`、`HT-IAM-001`、`HT-VAL-001`、`HT-IDEM-001`、`HT-POL-001`、`HT-RES-001`。

##### 幂等

`command_type = skill.publish`。必须 Key + Skill CAS。

---

#### API-197 `PUT /api/v1/model-routes/{model_route_id}`

##### 鉴权 / 角色 / scope

- Sess。`admin` / `owner`。`tester` / `viewer` → `HT-IAM-001`。

##### 同步性

**同步完成。** `200` ModelRoute。无 `credential_ref` 值。测试连通性走 API-198，不是本 PUT 的完成条件。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

ModelRoutePut:
  type: object
  required: [expected_version, task_type, data_classification, provider_allowlist, max_cost]
  additionalProperties: false
  properties:
    expected_version: { type: integer, minimum: 1 }
    task_type: { type: string }
    data_classification:
      type: string
      description: 四级之一；Restricted 默认不出站
    provider_allowlist:
      type: array
      items: { type: string }
    max_cost: { type: number }
    fallback: { type: object }
    require_prompt_version: { type: boolean }
    require_structured_output: { type: boolean }
    credential_bound: { type: boolean }

ModelRoute:
  type: object
  required: [id, task_type, data_classification, version, credential_present]
  properties:
    id: { $ref: '#/UUID' }
    task_type: { type: string }
    data_classification: { type: string }
    provider_allowlist: { type: array, items: { type: string } }
    max_cost: { type: number }
    fallback: { type: object }
    version: { $ref: '#/Version' }
    credential_present: { type: boolean }
```

##### 成功判定

- **完成**：路由表 GET API-196 一致。≠ 模型调用成功（那是 AIInvocationLog）。

##### 错误码

`HT-VER-001`、`HT-VAL-001`、`HT-POL-001`（Restricted 违规出站配置）、`HT-IDEM-001`、`HT-IAM-001`、`HT-RES-001`。

##### 幂等

`command_type = model_route.put`。必须 Key + CAS。

---

#### API-198 `POST /api/v1/model-routes/{model_route_id}/connection-tests`

##### 鉴权 / 角色 / scope

- Sess。`admin` / `owner`。`tester` / `viewer` → `HT-IAM-001`。
- 探测；**无**密钥回显。长连接器调用 → 同步受理 + 异步完成。

##### 同步性

**同步受理 + 异步探测。** HTTP `202` + `CommandReceipt`。短探测完成可用 `200` + 结果，但默认以受理+回取为准（架构：长连接器异步）。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

ModelRouteConnectionTest:
  type: object
  required: [expected_version]
  additionalProperties: false
  properties:
    expected_version: { type: integer, minimum: 1 }

# 202 CommandReceipt
# 完成查询：receipt.status=succeeded|failed + 无秘密的 reachability
ConnectionTestResult:
  type: object
  properties:
    reachable: { type: boolean }
    latency_ms: { type: integer }
    error_class:
      type: string
      description: 失败时业务/网络；无内部栈、无密钥
```

##### 成功判定

- **受理**：Receipt `accepted`/`running`。
- **完成**：探测 `succeeded` 且 `reachable` 由后端判定。前端 spinner **不是**完成。
- 本测试 **不**写业务状态机，不签发 Token。

##### 错误码

`HT-VER-001`、`HT-EXT-001`（可达性失败可落 Receipt failed）、`HT-IDEM-001`、`HT-IAM-001`、`HT-RES-001`、`HT-QUOTA-002`、`HT-POL-001`。

##### 幂等

`command_type = model_route.connection_test`。必须 Key。

---

#### API-199 `POST /api/v1/organizations/current/capability-controls/tighten`

##### 鉴权 / 角色 / scope

- Sess。**角色**：`admin` / `owner`（kill 关停 L1）。`tester` / `viewer` → `HT-IAM-001`。
- **只做关停（收紧）**。四级目标：单能力 → 模块 → 连接器写入 → 全局 AI（边界 §2.13）。
- **恢复（放开）不是本端点。** 恢复 = API-120 `action_type=kill_switch_restore`（L3 审批）。用本接口传 `enabled=true` / `direction=restore` → `HT-VAL-001`。
- L1 即时生效、**不走审批**（事故响应）。两向均写 AuditEvent（恢复在审批链上写）。

##### 同步性

**同步完成关停位。** `200` 组织 `capability_controls` 投影。过载时仍尽量保留本命令（§11）。无 202。

压测 kill 演练：关停可导致在途压测 `RUNNING`→`STOPPING`（系统）；**严禁**因此自动重试压测任务。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

CapabilityTighten:
  type: object
  required: [expected_version, target]
  additionalProperties: false
  properties:
    expected_version:
      type: integer
      minimum: 1
      description: Organization.version
    target:
      type: object
      required: [level]
      additionalProperties: false
      properties:
        level:
          type: string
          description: 单能力 / 模块 / 连接器写入 / 全局 AI；具体码 TBD，不得发明第 24 对象
        capability_id: { type: string }
        module:
          type: string
          description: Copilot / Release / 压测 等已登记模块名
        connector_id: { $ref: '#/UUID' }
    reason: { type: string }
    # 禁止：direction=restore、loosen=true

OrganizationCapabilityControls:
  type: object
  required: [version, tightened]
  properties:
    version: { $ref: '#/Version' }
    tightened: { type: boolean }
    effective_scope: { type: object }
    banner:
      type: object
      description: 横幅范围投影，供 API-010/005；无内部实现
```

##### 成功判定

- **完成**：关停位已持久化；后续写命令 / AI 出口按位 DENY 或降级（`result=degraded` 可感知）。
- **≠** 恢复完成。GET 仍显示收紧，直到 restore 审批 `EXECUTED+ok`。
- 对照边界 §2.13；§6 无独立 kill 行 → 以组织投影为准。

##### 错误码

`HT-VER-001`、`HT-VAL-001`（restore 误用）、`HT-IAM-001`、`HT-IDEM-001`、`HT-RES-001`、`HT-POL-001`（若目标非法）。关停本身不是 `HT-POL-001`（L1 ALLOW）。

##### 幂等

`command_type = organization.capability_tighten`。必须 Key + Organization CAS。重复关停同目标同 hash 返回已收紧。

---

### 13. 导入导出写命令（类 5 受理）

Excel 导入初始生命周期 **TBD（G2）**，本契约 **不冻结**为 `DRAFT` 或 `PENDING_REVIEW`。**无论落何态，禁止 AI/导入直写 `ACTIVE`。**

---

#### API-200 `POST /api/v1/test-cases/imports`

##### 鉴权 / 角色 / scope

- Sess。`tester` / `admin` / `owner`。`viewer` → `HT-IAM-001`。
- `multipart/form-data` 或先登记对象再引用。不可信文件：类型/大小/checksum/扫描（`HT-VAL-003`）。

##### 同步性

**同步受理 + 异步解析/校验/入库。** HTTP **`202`** + `CommandReceipt`。大文件不得占满同步请求直到完成。
普通导入 **不默认 HITL**。行失败可查询；partial 不静默（`HT-ASYNC-001` / Receipt `partial`）。

初始 `lifecycle_status`：**TBD**。响应与任务结果不得把未批默认写成 `ACTIVE`。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。
# Content-Type: multipart/form-data

TestCaseImport:
  type: object
  required: [project_id]
  properties:
    project_id: { $ref: '#/UUID' }
    file:
      type: string
      format: binary
    checksum: { type: string }
    # 禁止：force_lifecycle=ACTIVE、save=true

# 202
# CommandReceipt.command_type = test_case.excel_import
# poll: API-201、SSE API-212
```

完成态查询 API-201：`failed_items[]` 必现于 partial。无 Restricted 文件原文 dump。

##### 成功判定

- **受理**：Receipt `accepted`，源文件已隔离登记。
- **完成**：导入任务 `succeeded` / `partial` / `failed`；成功条已创建 TestCase（**生命周期 TBD**，但 **不是 ACTIVE** 除非未来变更流程批准 — 当前禁止）。
- 对照 §6 无 Excel 行；以回执 + 列表 GET 为准。前端下载中 **不是**完成。

##### 错误码

`HT-VAL-003`、`HT-VAL-001`、`HT-IAM-001`、`HT-IDEM-001`、`HT-QUOTA-001`/`002`、`HT-ASYNC-001`、`HT-ASYNC-002`、`HT-POL-001`（分级）。**禁止**用成功导入绕过评审直达 ACTIVE。

##### 幂等

`command_type = test_case.excel_import`。必须 Key。无 TestCase CAS（批量创建）。

---

#### API-202 `POST /api/v1/test-cases/exports`

##### 鉴权 / 角色 / scope

- Sess。`tester` / `admin` / `owner`。`viewer`：只读导出是否允许 **未列出则 fail-close** → 本契约 **拒绝 viewer 写导出命令**（`HT-IAM-001`）；viewer 用已有制品授权另议。
- Restricted 用例正文不得进普通导出包（fail-close / 剔除并显式 partial）。

##### 同步性

**同步受理 + 异步生成文件。** `202` + Receipt。完成经 §9 授权下载（API-203/223）。导出成功权威 = Artifact **可授权获取**（边界 §6 导出口径在证据包同行精神：引用≠授权）。

禁止把预签名当默认（M0/M1 代理）。TTL/90 天 **TBD**。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

TestCaseExport:
  type: object
  required: [project_id]
  additionalProperties: false
  properties:
    project_id: { $ref: '#/UUID' }
    test_case_ids:
      type: array
      items: { $ref: '#/UUID' }
    filters: { type: object }
    format:
      type: string
      description: 表格格式 TBD；不得默认含 Restricted
```

##### 成功判定

- **受理**：打包任务已接受。
- **完成**：Receipt `succeeded` 且导出包可经授权 GET content。按钮「已提交」**不是**完成。
- partial：部分行因分级跳过须显式。

##### 错误码

`HT-IAM-001`、`HT-VAL-001`、`HT-IDEM-001`、`HT-POL-001`、`HT-ASYNC-001`、`HT-RES-001`、`HT-QUOTA-002`。

##### 幂等

`command_type = test_case.excel_export`。必须 Key。

---

#### API-205 `POST /api/v1/import-sources`

##### 鉴权 / 角色 / scope

- Sess。`tester` / `admin` / `owner`。`viewer` → `HT-IAM-001`。
- 登记 OpenAPI / Postman / curl 源。A1 生成是 API-180，**本接口不落 TestCase**、不直写 ACTIVE。
- 数据分级 ≤Confidential 才允许后续出站；Restricted fail-close。

##### 同步性

**同步完成元数据登记**（短事务）。`200`/`201` 源资源（无原文 dump）。随后 A1 异步（API-180 `202`）。导入源登记本身不受 AI 降级关闭（边界 §2.2：导入本身不受降级影响）。

##### 请求 / 响应

```yaml
# Headers
# Idempotency-Key: 必须。

ImportSourceCreate:
  type: object
  required: [project_id, source_type]
  additionalProperties: false
  properties:
    project_id: { $ref: '#/UUID' }
    source_type:
      type: string
      enum: [openapi, postman, curl]
    inline_content:
      type: string
      description: 可选；分级校验；禁止 Restricted
    object_key:
      type: string
      description: 可选；已上传对象引用，非预签名 URL
    original_filename: { type: string }

ImportSource:
  type: object
  required: [id, source_type, project_id]
  properties:
    id: { $ref: '#/UUID' }
    project_id: { $ref: '#/UUID' }
    source_type: { type: string, enum: [openapi, postman, curl] }
    original_filename: { type: string }
    data_classification: { type: string }
    byte_size: { type: integer }
    # 无原文、无 Prompt
```

##### 成功判定

- **完成**：源 id 可 GET API-204（元数据）。≠ A1 草稿已生成（§6-2）≠ TestCase 已保存（§6-1）。

##### 错误码

`HT-VAL-003`、`HT-VAL-001`、`HT-POL-001`（Restricted）、`HT-IDEM-001`、`HT-IAM-001`、`HT-RES-001`、`HT-QUOTA-001`。

##### 幂等

`command_type = import_source.register`。必须 Key。

---

### 7.L L2+ Preview、审批、ApiToken 发起、入站 Webhook

# 以下为 L2+ Preview / 审批决策 / ApiToken 发起 / 入站 Webhook / Execute 内部化。

### 0. L2+ Preview / Execute 边界（总则）

| 面 | 是否产品 API | 职责 |
| --- | --- | --- |
| **Preview（API-120/121）** | 是 · 浏览器会话 | Policy Gate 裁决、冻结参数、**服务端生成** `param_hash`、组装九要素 `card_payload`；Gate=`REQUIRE_APPROVAL` 时创建 ApprovalRequest |
| **人工作业（API-112/113）** | 是 · 浏览器会话 | 批准 / 拒绝 / 修改后重新提交；**不**执行副作用 |
| **Execute** | **否** · **仅系统内部** | 行锁 consume、创建 execution intent、连接器真实调用、回写 `EXECUTED + execution_result` |
| 持续授权（L2 CI / Check Run） | **无资源** | **Proposed**；见 §8。未批准前不得做成绕过审批的通道 |

不变量（architecture §7.2 / §11.3，problem_model §2.3）：

1. 只有 Policy Gate 返回 `REQUIRE_APPROVAL` 才创建 ApprovalRequest；九要素、候选审批人（已排除发起人且非空）、TTL、`param_hash` 缺一不入队。
2. `param_hash` **禁止**客户端提交或前端从可见字段复算；与 ETag / `Idempotency-Key` 不可互换。
3. `APPROVED` ≠ 副作用成功。权威执行成功 = `status=EXECUTED` **且** `execution_result=ok`（边界 §6 第 6 行）。
4. Execute **无** `/api/v1` 浏览器或 Token 端点；无 Worker HTTP；无 Outbox CRUD。
5. `execution_result` 仅 EXECUTED 有值，枚举 **只允许** `ok / failed / unknown`。`unknown`：必须对账或人工接管，**禁止**当失败盲目重试，**禁止**当成功放行。

---

### 1. API-120 `POST /api/v1/action-previews`

Policy Gate Preview。对应边界 §5.1 第 3 类（L2+）；**不是**第 24 个领域对象，也**不是** Execute。

#### 1.1 鉴权 / 角色 / scope

- **鉴权**：OIDC 会话（Sess）。**禁止** ApiToken 调用本接口（Token 不能替代审批、不能跳过 Policy Gate）。
- **角色**：`tester / admin / owner` 可发起需审批的 Preview；`viewer` → `HT-IAM-001`。各 `action_type` 另见 §6 行级角色。
- **幂等**：可重试命令，建议 `Idempotency-Key`。同 key 同 hash → 已有 Preview；同 key 异 hash → `HT-IDEM-001`。

#### 1.2 同步性

同步完成 Gate 评估并（在 `REQUIRE_APPROVAL` 时）短事务创建 ApprovalRequest（`CREATED`→`PENDING`）。副作用执行仍走 §7 内部 Execute。

#### 1.3 请求 / 响应（OpenAPI 3.1）

```yaml
ActionType:
  type: string
  description: |
    与 problem_model §2.3 action_ref.type 完全一致，不得增删。
    copilot_write 为 M4 预留：M0–M3 调用一律拒绝。
  enum:
    - jira_write
    - heal_apply
    - perf_high_risk
    - release_push
    - env_register
    - agent_tool_action
    - gate_waiver
    - kill_switch_restore
    - copilot_write

PolicyGate:
  type: string
  description: Policy Gate 四值；未声明 sideEffectLevel 或白名单外目标默认 DENY。
  enum:
    - ALLOW
    - DENY
    - REQUIRE_APPROVAL
    - REQUIRE_REAUTH

CardPayload:
  type: object
  description: |
    九要素卡片，服务端组装；分区顺序冻结（动作 / 资源 / diff / 数据来源 /
    模型与 Skill 版本 / 风险等级 / 成本估计 / 回滚能力 / 参数哈希）。
    前端只渲染，不得补算 param_hash。缺一不得入队。
  required:
    - action
    - resource
    - diff
    - data_source
    - model_and_skill_version
    - risk_level
    - cost_estimate
    - rollback
    - param_hash
  properties:
    action:
      type: object
      required: [action_type, summary]
      properties:
        action_type:
          $ref: '#/ActionType'
        summary:
          type: string
          description: 写哪个系统 / 对象的人可读摘要
        payload_redacted:
          type: object
          description: 展示用参数投影；禁止密钥、Webhook secret、凭证原文
    resource:
      type: object
      required: [target_object_type, target_object_id]
      properties:
        target_object_type: { type: string }
        target_object_id: { $ref: '#/UUID' }
        display_name: { type: string }
    diff:
      type: object
      description: 目标资源变更前后对照；无变更时显式空 diff，不得省略该要素
      properties:
        before: { type: object, nullable: true }
        after: { type: object, nullable: true }
        summary: { type: string }
    data_source:
      type: object
      description: 结论引用的输入证据池 / 簇 / 评估 / 配置来源
      properties:
        evidence_refs:
          type: array
          items: { $ref: '#/UUID' }
        source_summary: { type: string }
    model_and_skill_version:
      type: object
      description: 模型、prompt_version、SkillVersion；非 AI 动作可为空对象但字段必须存在
      properties:
        model: { type: string, nullable: true }
        prompt_version: { type: string, nullable: true }
        skill_version_id: { $ref: '#/UUID' }
    risk_level:
      type: object
      required: [side_effect_level]
      properties:
        side_effect_level:
          type: string
          enum: [L0, L1, L2, L3, L4]
        rationale: { type: string }
    cost_estimate:
      type: object
      description: 成本估计（Token / 外部调用 / 压测机时等）；未知则显式 unknown_reason，不得省略要素
      properties:
        amount: { type: number, nullable: true }
        unit: { type: string, nullable: true }
        unknown_reason: { type: string, nullable: true }
    rollback:
      type: object
      required: [capability]
      description: 回滚 / 补偿能力；无回滚能力必须声明
      properties:
        capability:
          type: string
          enum: [snapshot, compensation, none]
        snapshot_ref: { type: string, nullable: true }
        compensation_summary: { type: string, nullable: true }
        none_declared: { type: boolean }
    param_hash:
      type: string
      description: 与顶层 param_hash 相同，供人工核对；真正比较只在服务端

ActionPreviewRequest:
  type: object
  required: [action_type, target_object_type, target_object_id, payload]
  properties:
    action_type:
      $ref: '#/ActionType'
    project_id:
      $ref: '#/UUID'
      description: 项目上下文；与目标资源归属不一致 → HT-VAL-001
    target_object_type:
      type: string
      description: |
        多态目标类型，随 action_type 约束，例如：
        jira_write → failure_cluster | case_result；
        heal_apply → test_case；
        perf_high_risk → test_run；
        release_push → release_task；
        env_register → execution_environment；
        agent_tool_action → test_run；
        gate_waiver → gate_evaluation | test_run；
        kill_switch_restore → organization（能力开关投影）。
    target_object_id:
      $ref: '#/UUID'
    payload:
      type: object
      additionalProperties: true
      description: |
        完整执行参数（冻结进 param_hash）。禁止含密钥明文、credential_ref 值、
        Webhook secret。客户端不得附带 param_hash / card_payload / gate。
    expected_target_version:
      type: integer
      minimum: 1
      description: 目标聚合 CAS；消费前重读比较，冲突 fail-close

# 禁止字段（出现即 HT-VAL-001）
# param_hash, card_payload, gate, approval_request_id, snapshot_ref（heal 快照由服务端在 consume 时创建）

ActionPreview:
  type: object
  required:
    - preview_id
    - action_type
    - gate
    - param_hash
    - card_payload
    - side_effect_level
    - created_at
  properties:
    preview_id:
      $ref: '#/UUID'
    action_type:
      $ref: '#/ActionType'
    gate:
      $ref: '#/PolicyGate'
    param_hash:
      type: string
      description: 服务端对冻结参数与目标语义生成；客户端不可提交、不可复算
    bound_hash:
      type: string
      description: 入队后与 ApprovalRequest 绑定的哈希来源；未入队可空
    card_payload:
      $ref: '#/CardPayload'
    side_effect_level:
      type: string
      enum: [L0, L1, L2, L3, L4]
    approval_request_id:
      $ref: '#/UUID'
      description: 仅 gate=REQUIRE_APPROVAL 且入队成功时出现
    expires_at:
      type: string
      format: date-time
      description: Preview 回取 TTL；数值 TBD，未批不得写默认小时数
    target:
      type: object
      required: [object_type, object_id]
      properties:
        object_type: { type: string }
        object_id: { $ref: '#/UUID' }
        version: { type: integer }
```

响应信封：`200` + `ResourceEnvelope`（`data` = `ActionPreview`），**仅当** `gate ∈ {ALLOW, REQUIRE_APPROVAL}`。

#### 1.4 Gate 裁决与 HTTP 映射

| `gate` | HTTP | 行为 |
| --- | --- | --- |
| `ALLOW` | `200` | L0/L1 可继续对应短命令（如 kill **关停**走 API-199，不走本接口）。当前默认下 L2/L3 **不会**因「普通发起」得到 ALLOW；L2 持续授权为 Proposed（§8），未批准前不得当作 ALLOW 旁路 |
| `REQUIRE_APPROVAL` | `200` | 创建 ApprovalRequest（`CREATED`→`PENDING`），返回 `approval_request_id` + 九要素；TTL 启动；通知候选审批人 |
| `DENY` | `403` `HT-POL-001`（未声明等级 / 禁止动作 → `HT-POL-002`） | **不**创建审批；写 AuditEvent。压测白名单外目标属此类，**不进审批** |
| `REQUIRE_REAUTH` | `401` `HT-AUTH-002` | L3+ 会话超过再认证窗口（窗口秒数 TBD）。客户端经 API-004 后再重放（同一 `Idempotency-Key` 仅当请求哈希不变） |

未声明 `sideEffectLevel` 的 Connector Action / Skill / Agent 工具 → 默认 `DENY`（`HT-POL-002`）。审批不能把禁止动作变成允许动作。

`copilot_write`：M4 预留。M0–M3 调用 → `HT-STATE-001` 或 `HT-POL-001`（与「未启用」一致，**不得**入队）。

#### 1.5 成功判定

- Preview **受理/评估成功**：返回 `preview_id` 且 `param_hash` 由服务端生成。
- Preview **不是**执行成功，也**不是**审批成功。
- `REQUIRE_APPROVAL` 时，审批资源可 GET（API-111）且 `status=PENDING` 才算入队完成。
- 后续两段成功判定见 API-112（`APPROVED`）与内部 Execute（`EXECUTED + ok`）。

#### 1.6 错误码（子集）

`HT-AUTH-001`、`HT-AUTH-002`、`HT-IAM-001`、`HT-RES-001`、`HT-VAL-001`、`HT-STATE-001`、`HT-VER-001`、`HT-IDEM-001`、`HT-POL-001`、`HT-POL-002`、`HT-QUOTA-001`、`HT-QUOTA-002`、`HT-APPR-001`。

客户端若在 body 中提交 `param_hash` / `gate` / `card_payload` → `HT-VAL-001`。

#### 1.7 幂等 / 分页

幂等 scope = `tenant + command_type=action_preview + Idempotency-Key`。无分页。

---

### 2. API-121 `GET /api/v1/action-previews/{preview_id}`

回取尚未过期的 Preview，供多端续审或审批卡片对照。

- **鉴权**：Sess；与创建者同租户且对目标资源可见，否则 `HT-RES-001`。
- **同步性**：查询。
- **响应**：同 `ActionPreview`。过期或已消费绑定后不可当新执行授权（TTL **TBD**）→ `HT-RES-001` 或 `HT-APPR-002`（已失效、需新 Preview）。
- **成功判定**：返回当前快照；**不**延长审批 TTL，**不**重新跑 Gate。
- **错误**：`HT-AUTH-001`、`HT-RES-001`、`HT-APPR-002`。
- **禁止**：本接口不接受参数修改；修改走 API-113（新请求）或重新 POST API-120。

---

### 3. 审批读（API-110 / API-111，配套）

#### 3.1 API-110 `GET /api/v1/approval-requests`

- **鉴权**：Sess。队列按审批人视角过滤；发起人可见自己提交的卡片，但「批准」由服务端四眼拒绝（前端置灰只是呈现）。
- **响应**：`ListEnvelope`；每项含 `id`、`status`、`action_type`、`side_effect_level`、`param_hash`、`card_payload`（九要素全量）、`initiator_id`、`approver_id`、`expires_at`、`escalate_to`、`execution_result`（仅 EXECUTED）、`expired_reason`、`version`、`origin_request_id`。
- **筛选（TBD 白名单外不得发明）**：`status`、`action_type`、作为候选审批人 / 发起人。
- `card_payload` **只**由服务端组装。

#### 3.2 API-111 `GET /api/v1/approval-requests/{approval_request_id}`

详情同上。跨租户 / 不可感知 → `HT-RES-001`。`execution_result=unknown` 时前端显示「结果待对账」，本契约不另发明状态。

---

### 4. API-112 `POST /api/v1/approval-requests/{approval_request_id}/decisions`

人工作业：批准或拒绝。对应边界 §2.5「批准 / 拒绝」；**不**触发浏览器侧 Execute。

#### 4.1 鉴权 / 角色 / 四眼

- **鉴权**：Sess。**禁止** ApiToken（`HT-IAM-003`）。
- **角色**：`admin / owner`，且属于该请求的候选审批人集合。`tester` / `viewer` → `HT-IAM-001`。
- **四眼（服务端三处强制：候选人路由、本命令、内部 consume 前）**：
  - `approver_id != initiator_id`；
  - 备审批人同样受四眼约束；
  - 重新提交后以**新** `initiator_id` 校验，不能沿用原发起人绕过；
  - 前端「本人批准置灰」不是安全边界。
- 四眼违例 → `403` `HT-IAM-002`，写 AuditEvent，状态不变。

#### 4.2 同步性

短事务完成 `PENDING → APPROVED | REJECTED`。批准后的副作用由 **系统内部 consume** 异步推进（§7）；本命令返回时 **不必**已是 `EXECUTED`。

#### 4.3 请求 / 响应

```yaml
ApprovalDecision:
  type: object
  required: [decision, expected_version]
  properties:
    decision:
      type: string
      enum: [approve, reject]
    reason:
      type: string
      description: reject 必填；approve 可选。禁止密钥/Prompt 原文
    expected_version:
      type: integer
      minimum: 1

ApprovalRequest:
  type: object
  required:
    - id
    - action_type
    - status
    - param_hash
    - card_payload
    - initiator_id
    - expires_at
    - version
  properties:
    id: { $ref: '#/UUID' }
    action_type: { $ref: '#/ActionType' }
    status:
      type: string
      enum: [CREATED, PENDING, APPROVED, EXECUTED, REJECTED, EXPIRED]
    execution_result:
      type: string
      nullable: true
      enum: [ok, failed, unknown]
      description: 仅 status=EXECUTED 非空；禁止其它值（含 not_evaluated）
    param_hash: { type: string }
    card_payload: { $ref: '#/CardPayload' }
    initiator_id: { $ref: '#/UUID' }
    approver_id: { $ref: '#/UUID', nullable: true }
    expires_at: { type: string, format: date-time }
    escalate_to: { $ref: '#/UUID' }
    expired_reason:
      type: string
      nullable: true
      enum: [ttl, withdrawn, invalidated]
    origin_request_id: { $ref: '#/UUID' }
    original_initiator_id: { $ref: '#/UUID' }
    snapshot_ref: { type: string, nullable: true }
    side_effect_level:
      type: string
      enum: [L0, L1, L2, L3, L4]
    version: { type: integer }
```

- 当前态非 `PENDING` → `HT-STATE-002`（已消费 / 不可再决）。
- `expected_version` 不匹配 → `HT-VER-001`。
- 已 `EXPIRED` → `HT-APPR-002`。
- `param_hash` 与目标现行参数不一致（审批后参数已变）→ 内部先将请求置 `EXPIRED + invalidated`，本命令 `HT-APPR-001`。

#### 4.4 两段成功判定（边界 §6 第 6 行，不可合并）

| 段 | 命令 | 权威成功 | 不是成功 |
| --- | --- | --- | --- |
| **1. 审批通过** | API-112 `approve` | `ApprovalRequest.status=APPROVED` | 按钮回执、SSE 提示 |
| **2. 副作用成功** | **无浏览器 API**（§7） | `status=EXECUTED` **且** `execution_result=ok` | 仅 `APPROVED`；`EXECUTED + failed`；`EXECUTED + unknown` |

- `reject` 成功 = `status=REJECTED`。关联 TestRun **仅**拒绝或人工取消才进入 `CANCELLED`；过期不自动取消。
- `unknown` 必须可 GET / 对账；UI 文案「结果待对账」。再次执行必须 **新**审批（API-113 或新的 API-120），不得重放本批准。

#### 4.5 拒绝联动（摘要，完整矩阵见 §6）

- `agent_tool_action` / `perf_high_risk`：TestRun → `CANCELLED`。
- `jira_write` / `heal_apply`：不写外部、不改版本；TestRun 保持终态。
- `env_register`：环境保持 `PENDING_APPROVAL`。
- `gate_waiver`：不豁免；原 `GateEvaluation` 不可变。
- `release_push`：ReleaseTask 保持 `PENDING_CONFIRM`。
- `kill_switch_restore`：能力保持关停。

#### 4.6 错误码 / 幂等

`HT-AUTH-001`、`HT-IAM-001`、`HT-IAM-002`、`HT-IAM-003`、`HT-RES-001`、`HT-VAL-001`、`HT-STATE-002`、`HT-VER-001`、`HT-IDEM-001`、`HT-APPR-001`、`HT-APPR-002`。

幂等：`Idempotency-Key` 建议携带。重复批准返回同一 `APPROVED` 资源，**不**创建第二个 execution intent（intent 由内部 consume 保证单次）。

---

### 5. API-113 `POST /api/v1/approval-requests/{approval_request_id}/resubmissions`

修改后重新提交 = **新** ApprovalRequest，不是重开旧单。

#### 5.1 鉴权 / 角色

- **鉴权**：Sess。
- **角色**：原发起人或对目标资源有发起权的 `tester / admin / owner`（重提人成为新 `initiator_id`）。`viewer` → `HT-IAM-001`。
- 旧请求须为可被替代的态（`PENDING` / `EXPIRED` / `REJECTED` / `EXECUTED` 且结果为 `failed|unknown`）。仍为 `APPROVED` 未执行完 → `HT-STATE-002`（先失效或等待对账，不得并行双批准）。

#### 5.2 请求 / 响应

```yaml
ApprovalResubmission:
  type: object
  required: [payload]
  properties:
    payload:
      type: object
      description: 修改后的完整执行参数；服务端重新生成 param_hash 与九要素
    expected_target_version:
      type: integer
    expected_origin_version:
      type: integer
      description: 可选；校验源请求未被并发改写

ApprovalResubmissionResult:
  type: object
  required: [origin_request_id, new_approval_request]
  properties:
    origin_request_id:
      $ref: '#/UUID'
    origin_final_status:
      type: string
      enum: [EXPIRED, REJECTED, EXECUTED]
      description: 旧单不被重新打开；PENDING 源在重提成功后置 EXPIRED + withdrawn
    new_approval_request:
      $ref: '#/ApprovalRequest'
```

不变量：

- 新 `param_hash`、新 TTL、新 `initiator_id` = **重提人**；
- 保留 `origin_request_id` / `original_initiator_id` 归因链；
- 重新走 Policy Gate、四眼（基于新 initiator）、权限、目标版本；
- Gate 非 `REQUIRE_APPROVAL` 时按 API-120 同一映射返回（DENY / REQUIRE_REAUTH），**不**偷偷 ALLOW 执行。

#### 5.3 成功判定

权威成功 = 新 ApprovalRequest 可 GET 且 `status=PENDING`（或 Gate 拒绝已用错误外壳表达）。旧单保持终态 / `EXPIRED`。

执行成功仍另判新单的 `EXECUTED + ok`。

#### 5.4 错误码 / 幂等

同 API-120 + `HT-STATE-002`、`HT-APPR-001`、`HT-APPR-002`。建议 `Idempotency-Key`。

---

### 6. 各 `action_type` 契约（Preview 入参语义 + 联动）

下列动作 **一律**先 API-120，禁止在 FailureCluster / ReleaseTask / 环境 / 门禁资源上直接 POST「外部写」。Execute 全走 §7。联动以 `EXECUTED + ok` 为唯一成功推进条件；`failed` / `unknown` **不得**自动推进 TestRun、ReleaseTask、ExecutionEnvironment。

#### 6.1 `jira_write`（L2）

- **目标**：终态 TestRun 上的 FailureCluster / CaseResult。TestRun **不**改回 `WAITING_APPROVAL`。
- **payload**：缺陷描述、目标 Jira 项目、证据附件引用列表（`evidence_id[]`，非字节）。
- **Preview 成功**：九要素含附件清单与目标项目；入队。
- **Execute 成功（内部）**：连接器返回可对账 `{status, external_request_id}`，issue 链接回写，Evidence/Audit 落账（边界 §6 第 7 行）。
- **失败 / unknown**：不重复建缺陷；TestRun 不变；再试须新审批。连接器短错可在**同一次** intent 内按幂等策略处理；一旦最终 `failed` 不得静默再消费同一批准。

#### 6.2 `heal_apply`（L3）

- **目标**：`test_case`（生命周期保持 `ACTIVE`，只改版本指针）。
- **payload**：建议 id、确认后的字段 patch。`can_auto_apply` 恒为 false；confidence ≥0.7 只影响前端入口可见性。
- **快照 fail-close（已定稿）**：
  1. 批准后 consume **锁** ApprovalRequest，对 `TestCase.current_version` 做 CAS；
  2. 版本一致才在**资产事务内**创建真正 rollback snapshot，再写新 `TestCaseVersion` 并切换 `current_version_id`；
  3. 快照、写版本、CAS **任一步失败** → 资产保持原状，ApprovalRequest = `EXECUTED + failed`；
  4. Preview/入队阶段若快照前置条件不满足 → fail-close，**不进入可应用/不入队**。
- **权威成功（边界 §6 第 12 行）**：新 Version + `current_version_id` 更新，且 `EXECUTED + ok`。快照失败 = **未成功**。
- 回滚走已有 API-039，不绕过本审批去改生产版本。

#### 6.3 `perf_high_risk`（L3）

- **目标**：压测型 TestRun。大并发 / 长时长经本动作；**白名单外目标** → `HT-POL-002`，**100% DENY、不进审批**。
- 发起时 TestRun `RUNNING → WAITING_APPROVAL`（或受理时直接进入等待，不开始高危阶段）。
- `EXECUTED + ok` → TestRun `RUNNING`（开始/恢复高危阶段）。
- 拒绝 → `CANCELLED`。过期 → 停在 `WAITING_APPROVAL`。
- `failed` / `unknown`：不开始高危阶段；停留等待人工处置。**压测严禁自动重试**。
- 场景互斥与 OrgQuota 在受理侧；超限 `HT-QUOTA-001`。

#### 6.4 `release_push`（L4 · 仅准备）

- **目标**：`release_task`，当前态 `PENDING_CONFIRM`。
- **平台只允许 prepare release item**（再认证、四眼、`param_hash`、幂等键防重复创建 item）。
- **不提供「执行生产发布」API**；任何「真正发到生产」的动作不存在或恒 `DENY`。L4 标签 ≠ 平台获得发布执行权。
- `EXECUTED + ok` → ReleaseTask `PENDING_CONFIRM → SUBMITTED`。
- **权威完成（边界 §6 第 11 行）**：后续由入站观察（API-090）+ **内部命令**将 `SUBMITTED → READY`；预览提交回执不是完成。
- 拒绝 / 过期：保持 `PENDING_CONFIRM`，可取消或 API-113 重提。
- 执行失败：可见失败处置，**不**重复创建外部 item；人工重试走领域命令（非本文件的生产 ship API）。

#### 6.5 `env_register`（L3）与 API-102 的交互

见 §11。ACTIVE **仅当**本动作 `EXECUTED + ok`。拒绝 / 过期 / failed / unknown：环境保持 `PENDING_APPROVAL`，不激活。

#### 6.6 `gate_waiver`（L3）

- **目标**：已有 `GateEvaluation`（或可评估的 TestRun 引用）。`owner` / 对门禁有权的 admin。
- **payload**：豁免说明。`confirm` 类字段必须显式。
- `GateEvaluation.result` **禁止**出现 `not_evaluated`。不可评估 = 无评估行 + 查询投影 `unevaluated_reason`，本动作不能「豁免一个不存在的评估」。
- 豁免 **不改写**原评估行（不可变）；`EXECUTED + ok` 后挂接 `waiver_approval_id`，重评估才生成新记录。权威成功 = 审批 `EXECUTED` 且豁免记录可查（边界 §6 第 13 行）。
- 拒绝 / 过期 / 失败：不豁免。

#### 6.7 `kill_switch_restore`（L3）

- **关停（收紧）** = L1，走 API-199，**不走**本 Preview。
- **恢复（放开）** = 必须本动作 + 审批；禁止用 tighten 接口放开。
- `EXECUTED + ok`：恢复生效并审计。拒绝 / 过期 / failed / unknown：保持关停，fail-close。

#### 6.8 `agent_tool_action`（按工具声明，≥L2 才入审批）

- **目标**：执行中 TestRun；发起时 `RUNNING → WAITING_APPROVAL`。
- **payload**：工具名、已声明 sideEffectLevel、参数（无秘密原文）。未声明 → `HT-POL-002`。
- `EXECUTED + ok` → TestRun `RUNNING`。拒绝 → `CANCELLED`。过期 → 停 `WAITING_APPROVAL`。
- `failed` / `unknown`：TestRun **不得**自动放行回 `RUNNING`；后续处置 TBD（人工取消或 API-113），**不得**误标为审批拒绝。
- LangGraph interrupt **不是** API：bridge 只关联本 ApprovalRequest；resume 前重新 GET 审批、权限、`param_hash`、目标版本。无 checkpoint HTTP。

#### 6.9 `copilot_write`（M4 预留，≥L2）

M0–M3：**不启用**。API-120 调用 → `HT-STATE-001` / `HT-POL-001`。不得创建 ApprovalRequest。

---

### 7.L.X Execute = 系统内部（无浏览器 / Token / Worker HTTP）

> 对应 `api_spec.md` §12「审批 consume / 创建 execution intent」。本节目的是把契约写清：**产品面看不到这些状态**。  
> **禁止**：为 consume、intent、Outbox、Inbox、Worker 领取、Temporal Signal 设立 `/api/v1` 路径。

#### 7.1 触发

API-112 将请求置为 `APPROVED` 后，控制面 **同一模块内**调度 consume。前端只轮询/SSE 展示 API-111 的 `status` 与 `execution_result`。

#### 7.2 行锁 consume（单次消费）

1. `SELECT … FOR UPDATE` 锁定 ApprovalRequest。
2. 重算 `param_hash`，重校验 tenant、当前权限、四眼、目标版本、kill switch（持续授权若将来启用亦在此复核）。任一失败 → fail-close：`EXPIRED + invalidated` 或保持不可执行，**不**调用外部。
3. **同一事务**原子创建唯一基础设施 execution intent（标识 `(organization_id, approval_request_id, bound_hash)`）及模块 Outbox。事务内 **不**发远程调用，**不**把 ApprovalRequest 写成 `EXECUTED`。
4. **重复 consume**（含 Outbox 重投、Worker 重领、客户端误以为要「再执行」）：返回 **同一** intent 引用，不创建第二行。

execution intent **不是**第 24 个领域对象，**不是**对外资源。

#### 7.3 execution intent 状态（仅内部）

枚举与 `data_model.md` §5.3 / architecture §7.2 一致（`CONFIRMED_*` = `CONFIRMED_OK` / `CONFIRMED_FAILED`）：

| 内部状态 | 含义 | 崩溃恢复 |
| --- | --- | --- |
| `READY` | 已创建、待领取 | 可重新领取同一行 |
| `CLAIMED` | Worker 已领、尚未出网 | 可重新领取同一行 |
| `DISPATCHING` | **网络调用前**已持久化；即将/正在出网 | **先**按 `external_request_id` / 稳定幂等键查询，禁止第二意图 |
| `CONFIRMED_OK` | 外部效果已确认成功 | 控制面写领域 `EXECUTED + ok` |
| `CONFIRMED_FAILED` | 外部效果已确认失败 | 控制面写领域 `EXECUTED + failed` |
| `UNKNOWN` | 请求可能已到达外部，效果不可判定 | 持续对账；对应领域 `unknown` |
| `ABANDONED` | 授权失效/人工放弃该意图 | 不得再用该意图执行新参数 |

产品 API **不**返回上表。对外只见 ApprovalRequest 六态 + `execution_result`。

#### 7.4 何时写 `EXECUTED`

- **首次真实外部/资产调用已经发出之后**，才允许控制面命令把 ApprovalRequest 置为 `EXECUTED`。
- 调用前崩溃停留 `READY` / `CLAIMED`：重领同一 intent，领域状态仍为 `APPROVED`。
- 确定成功 / 失败 → `execution_result=ok / failed`。
- 响应丢失或落账前崩溃 → intent `UNKNOWN`，领域 `EXECUTED + unknown`（若已发出）或保持 `APPROVED` 并进入查询协议（若无法证明已发出——实现须能区分；无法区分则按 unknown 对账，**仍禁止盲重试**）。
- 提供方既不支持幂等创建也不能查询 → fail-close，保持 `EXECUTED + unknown`，转人工接管，**禁止自动重发**。

#### 7.5 `unknown` 禁令

- **禁止**当作 `failed` 自动再 consume / 再 dispatch。
- **禁止**当作 `ok` 推进 TestRun / ReleaseTask / ExecutionEnvironment / 门禁豁免 / kill 恢复 / 用例指针。
- 客户端若对 `unknown` 的请求再 POST 决策或「重试执行」→ `HT-EXT-002` 或 `HT-STATE-002`。需要再跑 = API-113 新请求。

#### 7.6 与产品错误码的关系

内部失败映射到领域 GET：`execution_result=failed|unknown` + AuditEvent / Evidence。不把 Outbox 投递失败暴露为独立 API。`HT-EXT-001` 仅用于**产品命令**已能确定的外部失败回执；Execute 无产品命令，故外部结果以 GET ApprovalRequest 为准。

---

### 8. 作用域化持续授权（Proposed · 无 API 资源）

L2 系统动作（外部 CI trigger、GitHub Check Run 等）拟用 Connector / ExecutionEnvironment 上的版本化治理元数据承接，**不**新增第 24 对象，**不**提供 `/api/v1/standing-authorizations`。

当前契约：

- **不得**把 Proposed 写成已批准默认；
- **不得**用「已注册环境」解释为跳过 Policy Gate；
- 每次动作仍须 Gate + 审计；未批的合格动作清单 / 有效期 / 撤销 SLA = TBD；
- `standing_auth_metadata` JSON 占位列 **不**出现在本 A4 任何响应 schema 中。

---

### 9. API-080 `POST /api/v1/test-runs`（ApiToken 发起）

与 **API-062 同一路径**。系统入口单列（§6.7）：鉴权通道 + `trigger_type` 区分，不是第二套执行状态机。

#### 9.1 鉴权 / scope

- **鉴权**：`Authorization: Bearer <token>`，**不是** Sess。
- **必须** scope 含 `execute`。仅 `read` / `write` / `delete` → `HT-IAM-003`。`write` **不含**发起 TestRun。
- `project_id` ∈ Token `project_ids[]`，否则 `HT-IAM-005`。空数组语义 TBD，**禁止**默认全部项目。
- `revoked_at` 非空或过期 → `HT-IAM-004`。
- Token **不能**：调用 API-112/113/120（审批与 Preview）、跳过 Policy Gate、下载 Restricted 正文、做 L3 配置（环境/连接器/门禁 blocking/kill 恢复）。

#### 9.2 必须 `Idempotency-Key`

缺少该头 → `HT-VAL-001`。幂等 scope = `tenant + command_type=test_run_create + key`。同 key 同 hash 返回已有 `test_run_id`；异 hash → `HT-IDEM-001`。

#### 9.3 请求

Body 字段与 API-062 对齐，但 `trigger_type` **强制** `api_token`：

```yaml
TestRunCreateApiToken:
  type: object
  required: [project_id, env_id, execution_source, case_ids]
  properties:
    project_id: { $ref: '#/UUID' }
    plan_id: { $ref: '#/UUID' }
    env_id: { $ref: '#/UUID' }
    execution_source:
      type: string
      enum: [script, agent, external_ci]
    trigger_type:
      type: string
      enum: [api_token]
      description: 省略时由服务端按 Token 通道写入；传入 manual|schedule|ci_webhook → HT-VAL-001
    case_ids:
      type: array
      items: { $ref: '#/UUID' }
    params: { type: object }
    expected_env_version: { type: integer }
```

- Sess 通道的 API-062 **不得**传 `api_token`（反之亦然）。
- Agent × 外部 CI 一期不可用 → `HT-VAL-001` / `HT-POL-001`。
- 环境非 `ACTIVE` → `HT-STATE-001`。Job Schema / 变量 → `HT-VAL-002`。配额 → `HT-QUOTA-001`。
- 压测高危：Token 发起后仍须内部 Policy Gate；需审批则 TestRun 进入 `WAITING_APPROVAL`，**不能**由 Token 自批。白名单外 → `HT-POL-002`。

#### 9.4 成功判定

与 API-062 / 边界 §6 第 3 行相同：TestRun 已创建、返回可 GET 的 `test_run_id`，状态至少 `PENDING`。**不是**终态。本地/调用方校验通过 ≠ `VALIDATING` 成功。

#### 9.5 错误码 / 限流

`HT-AUTH-001`、`HT-IAM-003`、`HT-IAM-004`、`HT-IAM-005`、`HT-VAL-001`、`HT-VAL-002`、`HT-STATE-001`、`HT-IDEM-001`、`HT-POL-001`、`HT-POL-002`、`HT-QUOTA-001`、`HT-QUOTA-002`。限流见 `api_spec.md` §11。

响应 **永不**包含 `token` / `token_hash`。`last_used_at` 异步更新，非本接口成功条件。

---

### 10. API-090 `POST /api/v1/inbound-webhooks/{connector_id}`

入站观察入口（CI / GitHub / Release）。**先验签，再 Inbox / ExternalObservation**。不是 TestRun 创建 API，也不是状态机 PATCH。

#### 10.1 鉴权

- **HMAC 强制无例外**。头名按连接器类型 TBD（如 `X-Hub-Signature-256`），验签失败不得放行。
- 无 Sess、无 ApiToken、**无** `Idempotency-Key`（该头出现可忽略，不以它去重）。
- 密钥只存在 `webhook_secret_ref`；验签在服务端完成。

#### 10.2 观察优先（observe-first）

1. 验签；失败 → `401`/`403`（`HT-AUTH-001` / `HT-IAM-001`），**不**泄露算法、密钥、内部路由；仍写审计（无 secret）。
2. 归属：`connector_id` 属于当前租户、类型匹配、job/仓库绑定可解析；否则 `HT-RES-001`（猜测 UUID 统一不存在，不泄露跨租户连接器）。
3. 去重键 = **外部稳定事件 ID + tenant（organization_id）+ connector_id**。落入 `external_observations`（`source=webhook`），再 Inbox。重复事件返回已有 `observation_id`，不二次触发命令。
4. **禁止**本请求直接 `UPDATE` TestRun / ReleaseTask / GateEvaluation / ApprovalRequest。先到且版本更新者经 **已登记内部命令** 推动；重复/同版本忽略；迟到/较旧只对账 + 审计。
5. 持久轮询是可靠性兜底（内部），与 Webhook 双通道「先到者推动、后到者对账」。轮询不是本 API。

#### 10.3 CI vs Release：payload 不透明

```yaml
InboundWebhookAck:
  type: object
  required: [accepted, observation_id]
  properties:
    accepted:
      type: boolean
    observation_id:
      $ref: '#/UUID'
    duplicate:
      type: boolean
      description: true 表示命中去重，已有观察
```

- HTTP **`202`**：新观察已受理（尚未完成领域迁移）。
- 去重命中：`200` 或 `202` + `duplicate: true` + 同一 `observation_id`（实现择一，须稳定；推荐 `200` 表示「已存在」）。
- **请求 body**：按连接器原生产物作为 **不透明字节/JSON** 接收。本契约 **不**为 GitHub Check Run、Jenkins、Release 系统分别公开字段 schema。
- **内部**再归一为 ExternalObservation（`payload_ref`、外部版本、构建 ID 等），然后发出控制面命令（例如 CI：匹配 trigger binding → 内部创建 `trigger_type=ci_webhook` 的 TestRun；Release：`SUBMITTED → READY` / `FAILED_RETRYABLE`）。归一失败记观察 + 审计，不伪造领域成功。
- 仅收到「已排队」**不得**把 TestRun 提前打成 `RUNNING`。

#### 10.4 成功判定

权威成功 = 观察已落库且可对账。**不等于** TestRun 终态，**不等于** ReleaseTask `READY`。后者由后续内部命令 + GET 判定。

#### 10.5 禁止出现在任何响应中的内容

`webhook_secret` / `webhook_secret_ref` **值**、HMAC 密钥、连接器 `credential_ref` 值、原始 payload 中的凭证、签名明文。错误 `message` 不得回显签名字符串。

#### 10.6 错误码 / 限流

验签失败、未知 connector、归属失败见上。网关限流 `HT-QUOTA-002`。不把乱序当 4xx——乱序仍 `202`/`200` 并审计。

---

### 11. API-102 / API-106 与 `env_register`

#### 11.1 API-106 `POST /api/v1/connectors/{connector_id}/credential-refs`

登记**已存在**的凭证引用。浏览器 **禁止**提交密钥明文。

```yaml
CredentialRefBind:
  type: object
  required: [credential_ref]
  properties:
    credential_ref:
      type: string
      description: 已由独立机密通道产生的引用；本字段在后续 GET 中永不回显值
    expected_version:
      type: integer
      description: Connector CAS
```

- **鉴权**：Sess；`admin / owner`。
- **同步性**：短事务绑定引用。
- **成功**：连接器 `has_credential=true`（布尔），响应无引用值、无明文。
- 明文上传会话形态 **TBD**，不在本契约展开；未完成机密通道前调用本接口绑定未知引用 → `HT-VAL-001`。
- **错误**：`HT-IAM-001`、`HT-RES-001`、`HT-VAL-001`、`HT-VER-001`。

环境凭证同样只存引用：API-102 body 只允许 `credential_ref` 或「稍后绑定」，**从不**收密码。

#### 11.2 API-102 `POST /api/v1/execution-environments`

创建环境，状态 **必须**为 `PENDING_APPROVAL`。真正 `ACTIVE` **仅当** `env_register` 审批 **内部 Execute** 得到 `EXECUTED + ok`。

```yaml
ExecutionEnvironmentCreate:
  type: object
  required: [name, env_type, scope_level]
  properties:
    name: { type: string }
    env_type:
      type: string
      enum: [platform_executor, external_ci]
    scope_level:
      type: string
      enum: [organization, project]
    project_id: { $ref: '#/UUID' }
    endpoint: { type: string }
    credential_ref:
      type: string
      description: 可选；禁止明文。响应永不返回该值
    job_contracts:
      type: array
      description: external_ci 的 Job 契约（schema 引用、产物、适配器、取消能力）
    preview_id:
      $ref: '#/UUID'
      description: 推荐：先 API-120 action_type=env_register；或本命令内联同一 Gate
    expected_preview_param_hash:
      type: string
      description: 可选核对；服务端仍以 Preview 绑定为准，客户端不得发明哈希
```

#### 11.3 与 Preview 的交互（必须）

`env_register` 为 L3，默认 `REQUIRE_APPROVAL`（会话陈旧则 `REQUIRE_REAUTH`）。

推荐时序：

1. 调用方准备非秘密配置；凭证经 API-106 / 机密通道得到引用。
2. **API-120** `action_type=env_register`（目标可先为占位：若尚未有 `environment_id`，允许「创建+Preview」内联——见下）。
3. **API-102** 落库 `PENDING_APPROVAL`（`has_credential` 布尔）。
4. Gate=`REQUIRE_APPROVAL` → ApprovalRequest；管理员四眼批准（API-112）。
5. **内部 Execute** 成功 → `PENDING_APPROVAL → ACTIVE`，随后系统探活与 Job 发现（API-104/105 只读）。

允许 **内联 Gate**：API-102 在同一受理事务中调用与 API-120 相同的 Policy Gate。内联 **不能**跳过 Gate，**不能**因调用方是 admin 直接 `ACTIVE`。内联成功时响应同时给出 `environment_id` + `approval_request_id`（若需审批）或 `HT-AUTH-002` / `HT-POL-001`。

无 Preview 且无内联 Gate 的 API-102 → `HT-POL-001` / `HT-STATE-001`（未评估不得激活，也不得假装已批准）。

#### 11.4 响应纪律

```yaml
ExecutionEnvironment:
  type: object
  required: [id, name, env_type, status, has_credential, version]
  properties:
    id: { $ref: '#/UUID' }
    name: { type: string }
    env_type:
      type: string
      enum: [platform_executor, external_ci]
    status:
      type: string
      enum: [PENDING_APPROVAL, ACTIVE, DEGRADED, DISABLED]
    has_credential: { type: boolean }
    health_status: { type: object, nullable: true }
    version: { type: integer }
    approval_request_id: { $ref: '#/UUID' }
```

**禁止**字段：`credential_ref` 值、Vault 路径原文、standing auth 对象。

#### 11.5 成功判定

- API-102 权威受理成功 = 环境可 GET 且 `status=PENDING_APPROVAL`。
- 注册**完成**成功 = `env_register` 的 `EXECUTED + ok` 且 `status=ACTIVE`。
- DEGRADED / DISABLED 只挡新 run；由 API-103 / 内部探活写入，与本审批链独立。

#### 11.6 角色 / 错误

- 创建：`admin / owner`。`tester` 不可注册环境。
- `HT-IAM-001`、`HT-VAL-001`、`HT-POL-001`、`HT-AUTH-002`、`HT-VER-001`、`HT-IDEM-001`。

---

### 12. 本扩写明确不设立的端点

| 禁止项 | 说明 |
| --- | --- |
| Execute / consume / intent CRUD | §7；无 `/execute` 万能 RPC（Preview 路径除外） |
| Worker HTTP、Temporal HTTP | Worker 只走已登记领域命令 |
| Outbox / Inbox 产品 API | 基础设施表，非资源树 |
| 生产发布执行 API | `release_push` 只准备 item |
| 持续授权资源 | Proposed，§8 |
| `GateEvaluation.result=not_evaluated` | 禁止；用无行 + `unevaluated_reason` |
| 凭证明文、Webhook secret、`token_hash` 响应 | Restricted |
| Token 调审批 / Preview | API-080 不能批准、不能跳过 Gate |

---

### 7.A AI、导入导出、SSE 与制品端点

### 4. 端点契约 7.9 — AI / G1

> 每个端点：鉴权 / 同步性 / 请求响应 / 成功判定 / 错误码 / 幂等。角色未列则 fail-close。

#### 4.1 公共 schema（A1 / 回执 / 日志投影）

```yaml
A1FailedItem:
  type: object
  required: [endpoint, reason]
  properties:
    endpoint: { type: string }
    reason: { type: string, description: 用户可理解；禁止 Prompt 原文与内部栈 }

A1DraftCase:
  type: object
  required: [name, priority, case_type, steps, assertions, tags]
  properties:
    name: { type: string }
    priority:
      type: string
      enum: [P0, P1, P2, P3]
    case_type:
      type: string
      description: 对外 ⊆ 问题模型；示例 api（Web 等以问题模型为准，禁止发明）
    steps:
      type: array
      items:
        type: object
        required: [action, params]
        properties:
          action: { type: string }
          params: { type: object }
    assertions:
      type: array
      minItems: 2
      description: 断言 ≥2 类；服务端 schema 校验，失败进 failed_items 或拒整批
      items:
        type: object
        required: [type, expression]
        properties:
          type:
            type: string
            enum: [status_code, json_path, contains, header, response_time, equals]
          expression: { type: string }
          expected: {}
    variable_extractions: { type: array }
    preconditions: { type: string }
    tags:
      type: array
      items: { type: string }
      description: 保存入库时由后端保证含 ai-generated；暂存草稿可预填

A1DraftBundle:
  type: object
  required: [cases, failed_items, meta]
  properties:
    cases:
      type: array
      items: { $ref: '#/A1DraftCase' }
    failed_items:
      type: array
      items: { $ref: '#/A1FailedItem' }
      description: 即使长度为 0 也必须出现；partial 时长度 ≥1
    meta:
      type: object
      required: [prompt_version, model]
      properties:
        prompt_version: { type: string, description: 版本标识，不是 Prompt 正文 }
        model: { type: string }
    degraded:
      type: boolean
      description: 对应 AIInvocationLog.result=degraded 时为 true

GenerationStatus:
  type: string
  enum: [accepted, running, succeeded, failed, partial]
  description: 对齐 CommandReceipt.status；不是 TestCase 生命周期，不是第 24 对象

AiInvocationLogView:
  type: object
  description: |
    对外投影 ⊆ data_model.ai_invocation_logs 可对外语义。
    禁止字段：Prompt 原文、input_ref 解包正文、credential_ref 值。
  required: [id, model, prompt_version, usage, cost, latency_ms, data_classification, result]
  properties:
    id: { $ref: '#/UUID' }
    model: { type: string }
    prompt_version: { type: string }
    usage: { type: object }
    cost: { type: number }
    latency_ms: { type: integer }
    data_classification:
      type: string
      enum: [Public, Internal, Confidential, Restricted]
    result:
      type: string
      enum: [ok, degraded, refused]
    skill_version_id: { type: string, format: uuid, nullable: true }
    model_route_id: { type: string, format: uuid, nullable: true }
    copilot_session_id: { type: string, format: uuid, nullable: true }
    created_at: { type: string, format: date-time }
```

A6 回答 schema（问题模型原文，服务端校验后返回）：

```yaml
A6Citation:
  type: object
  required: [source_type, resource_id]
  properties:
    source_type:
      type: string
      enum: [jira, github, platform]
    resource_id: { type: string }
    evidence_ref: { type: string }

A6ToolCall:
  type: object
  required: [tool, args_hash]
  properties:
    tool: { type: string }
    args_hash: { type: string, description: 参数哈希，禁止秘密参数原文 }
    result_summary: { type: string, description: 脱敏摘要 }

A6Answer:
  type: object
  required: [answer, citations, tool_calls, refused_policies]
  properties:
    answer: { type: string, description: Confidential 最小化；无引用的关键事实禁止作为已核实结论 }
    citations:
      type: array
      items: { $ref: '#/A6Citation' }
      description: 服务端校验——调用方不可见的资源必须剥离或改 refused；禁止前端自造 citation
    tool_calls:
      type: array
      items: { $ref: '#/A6ToolCall' }
    refused_policies:
      type: array
      items: { type: string }
      description: 白名单外工具 / 越权 / 分级拒绝；必须显式，禁止静默
    meta:
      type: object
      properties:
        prompt_version: { type: string }
        model: { type: string }
        degraded: { type: boolean }
```

---

#### API-180 `POST /api/v1/ai/generations`

- **鉴权 / 角色**：Sess。`tester` / `admin` / `owner` 可发起；`viewer` → `HT-IAM-001`。项目成员且项目 ∈ 当前租户。
- **同步性**：**同步受理 + 异步完成**。默认 HTTP `202`。
- **幂等**：必须可带 `Idempotency-Key`（可重试命令）。同 key 同 hash → 已有回执；同 key 异 hash → `HT-IDEM-001`。
- **不是** TestCase 持久化 API。

请求：

```yaml
GenerationCreate:
  type: object
  required: [project_id, source_type]
  properties:
    project_id: { $ref: '#/UUID' }
    source_type:
      type: string
      enum: [openapi, postman, curl]
    import_source_id:
      type: string
      format: uuid
      description: 与 inline 二选一；指向 API-205 已登记源
    inline_content:
      type: string
      description: 内联规范/脚本；分级校验；体积上限 TBD；Restricted fail-close
    case_type_policy:
      type: object
      description: 用例类型策略提示；不得含模型超参
  additionalProperties: false
  description: |
    禁止字段：temperature、top_p、retry、save、prompt、model。
    出现 → HT-VAL-001。
```

响应 `202`：

```yaml
GenerationAccepted:
  type: object
  required: [data]
  properties:
    data:
      type: object
      required: [receipt, generation_id]
      properties:
        receipt: { $ref: '#/CommandReceipt' }
        generation_id:
          type: string
          format: uuid
          description: 暂存回取键；可与 receipt.resource_id 相同，仍不是 TestCase id
        poll:
          type: object
          properties:
            path:
              type: string
              example: /api/v1/ai/generations/{generation_id}
            sse_path:
              type: string
              example: /api/v1/ai/generations/{generation_id}/events
            drafts_path:
              type: string
              example: /api/v1/ai/generations/{generation_id}/drafts
```

短任务例外：若生成在短事务内完成，可用 `200` + 同上结构且 `receipt.status ∈ {succeeded, partial}` 并内嵌 `drafts`（`A1DraftBundle`）。**默认不以该例外为客户端契约。**

- **成功判定（受理）**：认证 / tenant / RBAC / 分级 / 配额 / 幂等通过，回执可 GET（API-071 或 API-181）。**完成**见 API-182 / 边界 §6-2。
- **错误码**：`HT-AUTH-001`、`HT-IAM-001`、`HT-RES-001`、`HT-VAL-001`（缺源、内联非法、禁止超参）、`HT-VAL-003`（源文件扫描/checksum）、`HT-QUOTA-001`（Token/预算）、`HT-QUOTA-002`（入口限流）、`HT-POL-001`（Restricted 出站 / kill switch 关停 A1）、`HT-IDEM-001`、`HT-INT-001`。
- **副作用**：写 `AIInvocationLog`（受理后异步调用亦写；无 Prompt 列）。扣减/预留 OrgQuota 由命令内账本完成。失败也审计。
- **Worker**：冻结 `import_source_id` 或已扫描的内联引用；**不**依赖浏览器会话内存。temperature/分批/重试仅服务端。

---

#### API-181 `GET /api/v1/ai/generations/{generation_id}`

- **鉴权 / 角色**：Sess。同项目可读成员（含 `viewer`）。跨租户 / 不可感知 → `HT-RES-001`。
- **同步性**：同步查询（**staging GET**）。
- **请求**：path `generation_id`。无 query 副作用。

响应 `200`：

```yaml
GenerationStaging:
  type: object
  required: [data]
  properties:
    data:
      type: object
      required: [generation_id, status, project_id]
      properties:
        generation_id: { $ref: '#/UUID' }
        project_id: { $ref: '#/UUID' }
        status: { $ref: '#/GenerationStatus' }
        accepted_at: { type: string, format: date-time }
        completed_at:
          type: string
          format: date-time
          nullable: true
        degraded: { type: boolean }
        drafts_available: { type: boolean }
        failed_items_preview:
          type: array
          description: 可选摘要；权威列表以 API-182 为准；partial 时不得省略「有失败」语义
          items: { $ref: '#/A1FailedItem' }
        error:
          description: 仅 failed 时；形状同 ErrorEnvelope.error；无 Prompt
        ttl_expires_at:
          type: string
          format: date-time
          nullable: true
          description: 有值仅当策略已批；未批则省略或 null，禁止填未批默认小时
        multi_device_resume:
          type: boolean
          description: 未批多端续审前恒为 false 或不出现；禁止写成已支持
```

- **成功判定**：返回当前暂存快照。`status=succeeded|partial` 不代替 API-182 的草稿权威体。
- **错误码**：`HT-AUTH-001`、`HT-RES-001`（含 TTL 过期后）、`HT-IAM-001`。
- **分页**：不适用。

---

#### API-182 `GET /api/v1/ai/generations/{generation_id}/drafts`

- **鉴权 / 角色**：同 API-181。
- **同步性**：同步查询。仍 **不是** TestCase 读接口。
- **前置**：`status ∈ {succeeded, partial}` 才返回 `A1DraftBundle`。`accepted` / `running` → `HT-STATE-001`。`failed` → `HT-ASYNC-002`（或 `200` + 空 `cases` **且** 非空错误外壳——禁止静默空成功；推荐错误码路径）。

响应 `200`（完成或 partial）：

```yaml
GenerationDrafts:
  type: object
  required: [data]
  properties:
    data:
      allOf:
        - { $ref: '#/A1DraftBundle' }
        - type: object
          required: [generation_id, status]
          properties:
            generation_id: { $ref: '#/UUID' }
            status:
              type: string
              enum: [succeeded, partial]
```

partial 纪律：

- HTTP 可为 `200`，`error.subclass=async_partial` 可放在 `CommandReceipt` / `details`；错误码 **`HT-ASYNC-001`** 语义适用。
- **`failed_items` required**，长度 ≥ 1。禁止省略该键。
- `cases` 为已成功结构化的子集；不得把失败 endpoint 丢弃后假装 `succeeded`。

- **成功判定**：边界 §6-2。schema 不合法 → 不得作为成功草稿返回（服务端应已重试；仍失败则该项进 `failed_items` 或整任务 `failed`）。
- **错误码**：`HT-STATE-001`、`HT-ASYNC-002`、`HT-VAL-004`（若错误地把未校验输出当草稿——实现必须先校验）、`HT-RES-001`、`HT-AUTH-001`。
- **缓存**：Confidential 禁缓存；草稿属 Confidential。

---

#### API-190 `GET /api/v1/copilot-sessions`

- **鉴权 / 角色**：Sess。仅返回**当前用户**在当前租户的会话（`copilot_sessions.user_id`）。`viewer` 可读自己的会话。
- **同步性**：同步查询。里程碑 **M3+**（契约存在，实现可延后）。
- **筛选 / 分页**：cursor 分页；`limit` 默认/上限 **TBD**。禁止按 Prompt 正文筛选。

响应列表项最小集：`id`、`title`（可空）、`updated_at`、`data_classification`、`selected_skill_version_id`。**不**返回完整 `messages`（避免列表打满 Confidential）。

- **错误码**：`HT-AUTH-001`、`HT-POL-001`（Copilot 模块 kill switch 关停时列表是否可见 **TBD**，fail-close 可 `HT-POL-001`）。

---

#### API-191 `POST /api/v1/copilot-sessions`

- **鉴权 / 角色**：Sess。`tester` / `admin` / `owner`；`viewer` 是否可开只读会话 **TBD**，未批则 fail-close `HT-IAM-001`。
- **同步性**：短命令，可 `201` 同步完成会话行创建。
- **幂等**：`Idempotency-Key` 建议。

```yaml
CopilotSessionCreate:
  type: object
  properties:
    title: { type: string }
    selected_skill_version_id:
      type: string
      format: uuid
      description: 必须已发布；未版本化不进生产
    project_id:
      type: string
      format: uuid
      description: 权限上下文锚点；跨项目注入由服务端裁剪
  additionalProperties: false
```

- **成功判定**：返回 `CopilotSession` id，可 GET API-193。问题模型**未定义**会话状态机，**不发明** `OPEN/CLOSED` 枚举。
- **错误码**：`HT-VAL-001`、`HT-RES-001`（技能不存在）、`HT-STATE-001`（未发布技能）、`HT-QUOTA-001`、`HT-POL-001`、`HT-IAM-001`。
- Restricted 内容 **不得**写入 `messages`（fail-close）。

---

#### API-192 `POST /api/v1/copilot-sessions/{session_id}/messages`

- **鉴权 / 角色**：Sess。仅会话所有者。
- **同步性**：**同步受理 + 异步完成**（模型调用）。可用 `202` + 回执；短问答可用 `200` + `A6Answer`。进度可订会话相关 hint（若走 API-213）或轮询 API-193；**不**把本接口当 SSE 命令通道。
- **幂等**：`Idempotency-Key` 建议（防重复扣费）。

```yaml
CopilotMessageCreate:
  type: object
  required: [content]
  properties:
    content:
      type: string
      description: 用户问题；服务端作不可信输入。禁止客户端传 temperature/retry/prompt 覆写
  additionalProperties: false
```

处理纪律（`02_api` §10.3 + 问题模型 A6）：

1. 全部经后端 LLM 工厂；写 `AIInvocationLog`（`copilot_session_id` 可空字段填本会话；**无 Prompt 列**，`input_ref` 仅为脱敏 object_key）。
2. 输出先 schema 校验，再 **citations 服务端校验**（`source_type`/`resource_id`/`evidence_ref` 必须落在调用方 RBAC + 输入证据池内；越权 citation 剥离并记 `refused_policies`）。
3. 白名单外工具 **不得调用**；记 `refused_policies`，`tool_calls` 不含该次调用。
4. 只读技能 **不**改变 TestRun / ApprovalRequest 控制流。L2+ 工具意图 → API-120 `agent_tool_action` 或 M4 `copilot_write`（M0/M1 调用 `copilot_write` → `HT-STATE-001` / `HT-POL-001`）。
5. 工具失败：声明无法获取，**不猜测**（填 `answer` 的不确定语义 + `refused_policies` 或 `result=degraded`）。
6. 无引用的关键事实不得当作已核实结论。
7. **禁止**把本接口做成 LangGraph checkpoint 提交；**禁止** MCP tool 入口。

- **成功判定**：返回 `A6Answer`（`answer` / `citations` / `tool_calls` / `refused_policies` 四键均在）。`result=refused` 仍是结构化成功体，不是 5xx。
- **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-IAM-001`、`HT-VAL-001`、`HT-VAL-004`（schema 失败且重试耗尽）、`HT-QUOTA-001`、`HT-POL-001`、`HT-ASYNC-002`、`HT-QUOTA-002`。
- 配额超限：**`HT-QUOTA-001`**，不调用模型。

---

#### API-193 `GET /api/v1/copilot-sessions/{session_id}`

- **鉴权 / 角色**：Sess。仅所有者（或未来组织审计角色 **TBD**；未批不得给 admin 默认全文）。
- **同步性**：同步查询。
- **响应**：`id`、`title`、`selected_skill_version_id`、`data_classification`、`updated_at`、`messages`（Confidential **最小化**：可截断、可去 Prompt 级原文；工具参数只留 `args_hash`）。**禁止**把 Restricted 写入后的回放。
- **成功判定**：当前有权快照。
- **错误码**：`HT-AUTH-001`、`HT-RES-001`。
- Confidential **禁缓存**。

---

### 5. 端点契约 7.10 — 导入导出

对照边界 §5.1 类 5、§6 导出成功、G2；`02_api` §6.2 / §10.1 / §10.4。普通导入导出 **不默认 HITL**。

#### 5.1 异步任务公共纪律（导入 / 导出 / 证据包）

- 入口短事务：认证、tenant、RBAC、配额、格式、幂等、基础大小。
- Worker 使用冻结输入引用，不依赖浏览器内存。
- 进度可观察（API-212 SSE），领域完成态不由进度推导。
- 结果语义 ∈ `succeeded` / `partial` / `failed`（对齐 `CommandReceipt.status`）；**不**新增业务状态枚举。
- **partial 必须列出失败项**，禁止静默截断。
- 完成后通知 + AuditEvent；不要求每种都建 Evidence。
- 大文件生成 **不得**占用同步 API 直到完成。
- **无** Redis 任务表；回执查询走 PostgreSQL / 领域行 + `CommandReceipt` 协议（是否持久化为通用表 = A-01 TBD）。

---

#### API-028 `POST /api/v1/evidence-objects/export-packages`

- **鉴权 / 角色**：Sess。证据中心导出：至少项目内 `tester`+；`viewer` 是否可导出 **TBD**，未批 fail-close `HT-IAM-001`。Restricted 证据默认禁止打包出站。
- **同步性**：**同步受理 + 异步打包**。`202` + `CommandReceipt`。
- **幂等**：`Idempotency-Key`。

```yaml
EvidenceExportCreate:
  type: object
  required: [format]
  properties:
    format:
      type: string
      enum: [zip, md, json]
    subject_type: { type: string }
    subject_id: { type: string, format: uuid }
    evidence_object_ids:
      type: array
      items: { $ref: '#/UUID' }
    project_id: { $ref: '#/UUID' }
```

- **成功判定（受理）**：回执可查。**权威完成** = 导出 Artifact 已登记且调用方经 **API-223 代理**可获取（边界：导出成功 = Artifact **可授权获取**，不是按钮提示）。
- **进度**：`GET /api/v1/command-receipts/{receipt_id}` 与 **API-212**。
- **下载**：完成前 API-223 → `HT-STATE-001`。完成后每次下载重做授权（引用 ≠ 授权）。**不**在 Evidence 行写入预签名 URL。
- **错误码**：`HT-VAL-001`、`HT-IAM-001`、`HT-RES-001`、`HT-POL-001`（Restricted）、`HT-QUOTA-002`、`HT-IDEM-001`、`HT-ASYNC-002`。
- Evidence `source_object` / `content_ref` 保持稳定引用；导出包是新 Artifact，不是改写历史证据。

---

#### API-200 `POST /api/v1/test-cases/imports`

- **鉴权 / 角色**：Sess。`tester` / `admin` / `owner`。
- **同步性**：**异步**。上传私有存储（M0/M1 = 本地卷登记）后异步解析、格式校验、逐行汇总。`202`。
- **幂等**：`Idempotency-Key`。
- **内容类型**：`multipart/form-data`（文件）或先 API-205 类登记再引用（Excel 专用本接口）。
- **上传校验**：MIME/magic、大小、checksum、扫描；失败 `HT-VAL-003`。对象 key 服务端生成。
- **HITL**：普通导入 **否**。
- **G2**：导入后 TestCase **初始生命周期 TBD**（DRAFT vs PENDING_REVIEW、是否强制两步审阅）。本契约 **不冻结**。响应不得把未批默认写成规范。

```yaml
ExcelImportCreate:
  type: object
  required: [project_id]
  properties:
    project_id: { $ref: '#/UUID' }
    original_filename:
      type: string
      description: 仅展示
```

响应：`CommandReceipt` + `receipt_id`（即后续 API-201 路径参数）+ `sse_path` → API-212。

- **成功判定（受理）**：文件已隔离登记且任务已受理。**完成** = API-201 给出明确 `succeeded|partial|failed` + 行失败可下载/可查。
- **错误码**：`HT-VAL-001`、`HT-VAL-003`、`HT-IAM-001`、`HT-QUOTA-001`（若计入执行/存储预算）、`HT-QUOTA-002`、`HT-IDEM-001`、`HT-POL-001`。

---

#### API-201 `GET /api/v1/test-cases/imports/{receipt_id}`

- **鉴权 / 角色**：Sess。导入发起者或同项目 `admin`/`owner`（精确矩阵未列则 fail-close 到发起者 + admin/owner）。
- **同步性**：同步查询。

响应：

```yaml
ExcelImportResult:
  type: object
  required: [data]
  properties:
    data:
      type: object
      required: [receipt_id, status]
      properties:
        receipt_id: { $ref: '#/UUID' }
        status:
          type: string
          enum: [accepted, running, succeeded, failed, partial]
        totals:
          type: object
          properties:
            row_count: { type: integer }
            created_count: { type: integer }
            failed_count: { type: integer }
        created_test_case_ids:
          type: array
          items: { $ref: '#/UUID' }
          description: 已落库 id；lifecycle_status 以 GET TestCase 为准，本文不冻结初始态（G2）
        failed_items:
          type: array
          description: partial/failed 必现；禁止静默
          items:
            type: object
            required: [row_number, reason]
            properties:
              row_number: { type: integer }
              reason: { type: string }
              column: { type: string }
        failures_download:
          type: object
          description: 行失败可下载；引用 ≠ 授权
          properties:
            artifact_id: { $ref: '#/UUID' }
            content_path:
              type: string
              example: /api/v1/artifacts/{artifact_id}/content
              description: M0/M1 走 API-221 代理，不返回预签名 URL
        error:
          description: 仅 failed
```

- **成功判定**：`status=succeeded` 且失败列表为空；或 `partial` **且** `failed_items` 非空（可下载）。权威用例状态以 API-030/031 为准，不以本回执发明生命周期。
- **错误码**：`HT-RES-001`、`HT-AUTH-001`、`HT-IAM-001`。任务失败体用 `HT-ASYNC-002` 投影。
- **下载失败明细**：经 API-221，每次重验授权；checksum 与扫描状态必须为已通过。

---

#### API-202 `POST /api/v1/test-cases/exports`

- **鉴权 / 角色**：Sess。项目内可读且允许导出的角色（`viewer` 导出 **TBD**，未批 fail-close）。
- **同步性**：异步生成 Excel。`202` + `CommandReceipt`。
- **幂等**：`Idempotency-Key`。
- **请求**：`project_id` + 与 API-030 同语义的筛选（`lifecycle_status` / `tags` 等）。筛选是查询投影，不是 URL 私有状态上传。
- **成功判定（完成）**：导出 Artifact 可经 **授权** GET（API-203 完成后走 **API-223**）。
- **错误码**：`HT-VAL-001`、`HT-IAM-001`、`HT-QUOTA-002`、`HT-IDEM-001`、`HT-POL-001`。
- 导出内容受 tenant/RBAC；Restricted 字段不得进普通 Excel。

---

#### API-203 `GET /api/v1/test-cases/exports/{receipt_id}`

- **鉴权 / 角色**：Sess。与导出发起范围一致。
- **同步性**：同步查询。

```yaml
ExcelExportStatus:
  type: object
  required: [data]
  properties:
    data:
      type: object
      required: [receipt_id, status]
      properties:
        receipt_id: { $ref: '#/UUID' }
        status:
          type: string
          enum: [accepted, running, succeeded, failed, partial]
        artifact_id:
          type: string
          format: uuid
          nullable: true
          description: 完成后出现；仍须经 API-223，本字段不是下载令牌
        byte_size: { type: integer, nullable: true }
        checksum: { type: string, nullable: true }
        content_path:
          type: string
          nullable: true
          example: /api/v1/export-packages/{receipt_id}/content
        error: {}
```

- **成功判定**：`status=succeeded` 且 `artifact_id` 非空 **并且** API-223 对当前调用方授权通过。前端持有 `artifact_id` ≠ 已授权。
- **错误码**：`HT-RES-001`、`HT-AUTH-001`、`HT-STATE-001`（未完成时若误打 content）。
- **禁止**：响应内嵌预签名 URL、长期直链、90 天 TTL。

---

#### API-204 `GET /api/v1/import-sources/{source_id}`

- **鉴权 / 角色**：Sess。同项目成员。
- **同步性**：同步查询。
- **响应**：源类型、`original_filename`（展示）、`byte_size`、`checksum`、`data_classification`、`created_at`。**无原文 dump**、无内联规范全文、无 Prompt。
- **成功判定**：元数据快照。
- **错误码**：`HT-RES-001`、`HT-AUTH-001`。
- 导入源登记是传输协调面，**不是**第 24 对象。

---

#### API-205 `POST /api/v1/import-sources`

- **鉴权 / 角色**：Sess。`tester` / `admin` / `owner`。
- **同步性**：短事务登记 + 扫描；大文件扫描可异步，则 `202`。登记成功不等于 A1 完成。
- **幂等**：`Idempotency-Key`。
- **输入**：`project_id`、`source_type ∈ {openapi, postman, curl}`、文件或内联。
- **校验**：分级 ≤Confidential 才允许后续 A1 出站；checksum + 扫描；路径安全。
- **成功判定**：返回 `source_id`，可 GET API-204。A1 降级 **不**阻断本接口（边界：导入本身不受 A1 降级影响）。
- **错误码**：`HT-VAL-001`、`HT-VAL-003`、`HT-IAM-001`、`HT-POL-001`（Restricted）。
- 本接口 **不**创建 TestCase，**不**调用模型。

---

### 6. 端点契约 7.11 — SSE

公共请求：

```http
GET {sse_path} HTTP/1.1
Accept: text/event-stream
Last-Event-ID: <optional-opaque-id>
Cookie: <OIDC session>
```

公共响应：`200 Content-Type: text/event-stream`。未认证 `401` **不得**伪装 404。授权失败同资源 GET：跨租户 `HT-RES-001`。

```yaml
SseEventData:
  type: object
  required: [id, type, occurred_at]
  properties:
    id: { type: string, description: 与 SSE 帧 id 一致 }
    type:
      type: string
      enum: [progress, resource_changed, resync_required, heartbeat, degraded]
    resource_type: { type: string }
    resource_id: { type: string, format: uuid }
    progress_percent:
      type: number
      description: 仅展示；可缺省；禁止据此推定终态
    hint: { type: string }
    occurred_at: { type: string, format: date-time }
```

帧命名：SSE `event:` 字段 = `SseEventData.type`。`data:` 为上述 JSON **一行**（禁止多行 data 夹带命令）。

---

#### API-210 `GET /api/v1/test-runs/{test_run_id}/events`

- **鉴权**：Sess。对 TestRun 有读权限。默认 **无** Tok SSE。
- **同步性**：长连接只读。
- **hint 范围**：执行进度、WAITING_* 等待提示、报告解析/聚类进度。**不**携带取消命令。
- **对账**：终态以 API-061 GET 为准（边界 §6-5）。Agent 轨迹权威以 API-067 为准（§6-16）。
- **断连**：不得把该 run 标 `FAILED`/`TIMEOUT`。
- **错误**：握手失败用错误外壳；已连接后断流可能无 JSON（`HT-NET-003`）。

---

#### API-211 `GET /api/v1/ai/generations/{generation_id}/events`

- **鉴权**：Sess。同 API-181 可见性。
- **hint 范围**：A1 分批进度、`degraded` 提示。完成仍须 GET API-181/182。
- **禁止**：在流上推送 Prompt、完整规范原文、未校验草稿当终态。

---

#### API-212 `GET /api/v1/command-receipts/{receipt_id}/events`

- **鉴权**：Sess。能 GET 该回执者可订。
- **hint 范围**：Excel 导入/导出、证据包打包进度。
- **完成**：以 API-201 / API-203 / 回执 `status` + 制品授权下载为准，不以 100% 进度条为准。

---

#### API-213 `GET /api/v1/events`

- **鉴权**：Sess。租户级轻量 hint：审批待办、降级、通知角标刷新提示。
- **事件全集**：Proposed / TBD，不得假装已冻结。
- **冲突**：与任意领域 GET 冲突时 **GET 为准**。本流 **不是** 通知已读命令（已读走 API-023）。

---

#### 6.1 示例：`text/event-stream` 帧（规范文本，非实现）

以下为契约示例。`id` 为服务端不透明串；客户端重连时原样放入 `Last-Event-ID`。

**进度（TestRun，仅展示）：**

```
id: 01j8sse-000001
event: progress
data: {"id":"01j8sse-000001","type":"progress","resource_type":"test_run","resource_id":"11111111-1111-1111-1111-111111111111","progress_percent":42,"hint":"running","occurred_at":"2026-08-29T12:00:00Z"}

```

**资源变化 hint（仍须 GET）：**

```
id: 01j8sse-000002
event: resource_changed
data: {"id":"01j8sse-000002","type":"resource_changed","resource_type":"test_run","resource_id":"11111111-1111-1111-1111-111111111111","hint":"status_may_have_changed","occurred_at":"2026-08-29T12:00:05Z"}

```

**心跳（间隔 TBD）：**

```
id: 01j8sse-000003
event: heartbeat
data: {"id":"01j8sse-000003","type":"heartbeat","occurred_at":"2026-08-29T12:00:15Z"}

```

**缺口 / 过旧 Last-Event-ID → 强制对账：**

```
id: 01j8sse-000004
event: resync_required
data: {"id":"01j8sse-000004","type":"resync_required","hint":"event_gap_or_window_elapsed","occurred_at":"2026-08-29T12:01:00Z"}

```

**降级提示（AI/平台，非命令）：**

```
id: 01j8sse-000005
event: degraded
data: {"id":"01j8sse-000005","type":"degraded","resource_type":"organization","resource_id":"22222222-2222-2222-2222-222222222222","hint":"ai_capability_degraded","occurred_at":"2026-08-29T12:02:00Z"}

```

**A1 进度：**

```
id: 01j8gen-000010
event: progress
data: {"id":"01j8gen-000010","type":"progress","resource_type":"generation","resource_id":"33333333-3333-3333-3333-333333333333","progress_percent":70,"hint":"batch_running","occurred_at":"2026-08-29T12:03:00Z"}

```

**导入打包：**

```
id: 01j8imp-000020
event: progress
data: {"id":"01j8imp-000020","type":"progress","resource_type":"command_receipt","resource_id":"44444444-4444-4444-4444-444444444444","progress_percent":55,"hint":"parsing_rows","occurred_at":"2026-08-29T12:04:00Z"}

```

非法示例（契约禁止）：`event: cancel`、`event: approve`、`data` 内含 `command`/`expected_version` 写意图、WebSocket 升级、MCP JSON-RPC。

---

### 7.A.ART 制品访问端点

`artifacts`：正文不进库；`object_key` 服务端生成、租户 scope；`checksum` 必有；`original_filename` 仅展示；禁止把预签名 URL 当稳定引用。

---

#### API-220 `GET /api/v1/artifacts/{artifact_id}`

- **鉴权 / 角色**：Sess。对所属 `test_run` / 项目有读权限。ApiToken `read` 是否可读元数据 **TBD**；Restricted 元数据对 Token 默认否。
- **同步性**：同步查询。

```yaml
ArtifactMetadata:
  type: object
  required: [data]
  properties:
    data:
      type: object
      required: [id, kind, checksum, data_classification, test_run_id]
      properties:
        id: { $ref: '#/UUID' }
        kind: { type: string, description: 截图/视频/Trace/日志/报告/轨迹/导出包 等，不当新领域对象 }
        mime_type: { type: string, nullable: true }
        byte_size: { type: integer, nullable: true }
        checksum: { type: string }
        data_classification:
          type: string
          enum: [Public, Internal, Confidential, Restricted]
        original_filename: { type: string, nullable: true }
        test_run_id: { $ref: '#/UUID' }
        object_key:
          type: string
          description: 稳定引用，不是授权，不是路径遍历输入
        scan_status:
          type: string
          description: 已扫描/待扫描等对外码 TBD；未通过扫描不得开放 content
```

- **成功判定**：元数据快照。持有 `id`/`object_key` **≠** 可下载。
- **错误码**：`HT-AUTH-001`、`HT-RES-001`。
- **禁止**：预签名 URL、内部卷绝对路径、90 天过期字段冒充策略。

---

#### API-221 `GET /api/v1/artifacts/{artifact_id}/content`

- **鉴权 / 角色**：Sess。每次请求重验 tenant / project / RBAC / classification / 扫描通过 /（TBD）保留与 Legal Hold。
- **同步性**：同步代理字节流（M0/M1 **唯一**普通制品下载）。`Content-Type` 按 `mime_type`；主动内容 **不得**与主站同源默认 inline 执行（`Content-Disposition` 策略 TBD，安全默认 attachment）。
- **M0/M1**：从本地卷代理。**不** 302 到对象存储，**不**签发预签名。
- **Restricted**：仅代理或拒绝；**永不**普通预签名。高审计内容可禁导出（`HT-POL-001`）。
- **成功判定**：授权通过且扫描/checksum 已验证后的正文流。审计记录敏感访问（无正文）。
- **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-IAM-001`、`HT-POL-001`、`HT-VAL-003`（扫描未通过）、`HT-STATE-001`（尚未就绪）。
- Token：默认不得下载 Restricted；普通制品 Token 下载 **TBD**，未批否。

---

#### API-222 `POST /api/v1/artifacts/{artifact_id}/access-grants`

- **状态**：**Proposed · M2+**（ADR 0007 混合预签名；ADR 0009：启用 MinIO 前不得假设预签名）。
- **M0/M1**：调用本接口 → **`HT-STATE-001`**（未启用）。不得文档化为当前成功路径。
- **Proposed 语义（非当前默认）**：后端再授权后签发**短期、单对象、只读**访问；TTL / 次数 / IP 绑定 **TBD**。签发与下载行为审计。
- **Restricted**：即使 M2+ **拒绝**走普通预签名（继续 API-221 或隔离查看）。
- **禁止**：把 grant URL 写入 EvidenceObject；把 90 天当 TTL 默认。

```yaml
AccessGrantCreate:
  type: object
  description: M2+ Proposed；M0/M1 不接受成功体
  properties:
    purpose: { type: string }
```

---

#### API-223 `GET /api/v1/export-packages/{receipt_id}/content`

- **鉴权 / 角色**：Sess。与对应导出命令（API-028 / API-202 等）授权一致。每次重验。
- **同步性**：M0/M1 **代理下载**（与 API-221 同类，按回执定位 Artifact）。
- **前置**：回执 `status=succeeded`（或 `partial` 且产物仍可交付的已批语义——未批则仅 `succeeded`）。否则 `HT-STATE-001`。
- **成功判定**：授权后的包字节。引用回执 id ≠ 授权。
- **错误码**：`HT-AUTH-001`、`HT-RES-001`、`HT-IAM-001`、`HT-POL-001`、`HT-STATE-001`。
- **禁止**：预签名、直链、把本 URL 存进 Evidence。

---

#### 7.1 上传（非独立「直传生产路径」浏览器 API）

不可信输入一律：隔离 → 类型/扩展名/内容嗅探 → 大小与解压预算 → 路径安全 → **checksum** → **恶意扫描** → 准入后才解析或给模型。

- 对象 key **服务端生成**，客户端不可指定任意路径。
- Worker 产物以服务身份写入本地卷（M0/M1），浏览器不直传生产路径。
- 大文件异步校验；普通上传 **不默认 HITL**。
- 失败清理策略 **TBD**（`02_api` Q9），未批不得写默认保留天数。
- Excel / OpenAPI 源走 API-200 / API-205，不另开匿名上传。

---

## 8. SSE 契约（G3）

### 2. G3 收口：SSE 只读通道

对照边界 §9-G3、§6-5、§6-16；`02_api` §8；frontend_design_spec 缺口 G3。

#### 2.1 定位

SSE 是**只读**进度与变化 **hint** 通道，**不是**命令通道、状态机引擎或事实存储。

禁止在 SSE 上发送：取消、审批、执行、导入确认、下载授权、任何会改变状态的帧。客户端不得把 SSE 当 RPC。

适用：TestRun 执行 / 外部等待 / 采集、报告解析与聚类、A1 生成、导入导出打包、审批 / 降级 / 通知轻量 hint（API-213）。

**不提供** WebSocket 替代通道。无 SSE 的页面：资源 GET + 可见性唤醒刷新；自动刷新间隔 **TBD**。

#### 2.2 GET 为准（冲突纪律）

1. 进入页面先 **GET** 领域快照，再订阅 SSE。
2. 事件只表示「有变化 / 可展示进度」。终态、资格、`execution_result`、A8 `status` / `assertion_results` **以资源 GET 为准**。
3. 关键状态、终态、版本跳跃、命令未决、从后台恢复、网络恢复、SSE 重连成功后 **必须 GET**。
4. **SSE 与 GET 冲突时，以 GET 为准。**
5. 禁止用进度百分比或 SSE 文本推导 TestRun 终态（边界 §6-5），或把 Agent 轨迹 UI 推定为 SUCCEEDED/FAILED（边界 §6-16）。
6. 禁止用 SSE 把审批标为 `EXPIRED`。

#### 2.3 Last-Event-ID 与 `resync_required`

重连请求头：

```http
Last-Event-ID: <server-opaque-id>
```

- 事件 `id` 由服务端生成、单调可排序、不可伪造。
- **仅**用于断线续传与缺口检测，**不是**业务 `version`，**不是**幂等键，**不是** CAS `expected_version`。
- 保留窗口内可补发；过旧 / 窗口已清理 / 检测到缺口 → 推送 `event: resync_required`，客户端 **全量 GET**，禁止伪造连续事件、禁止前端补插丢失 id。
- 保留窗口时长、每租户连接数、每用户订阅上限：**TBD**。

#### 2.4 重连、降级轮询、心跳

| 项 | 契约 |
| --- | --- |
| 重连 | 指数退避 + 抖动 + 上限；认证过期则**停止**自动重连，先完成登录 / `API-004` |
| 降级 | 连续失败达阈值后改 **GET 轮询**，并展示「实时更新已降级」 |
| 轮询秒数 | RUNNING/STOPPING 较频；等待态较低；终态停止自动轮询；**秒数 TBD**（未批不得写默认） |
| 页面不可见 | 降低频率；可见时立即 GET |
| 恢复 SSE | 仍先 GET 再订 |
| 心跳 | 服务端定期 `event: heartbeat`；**间隔 TBD** |
| **禁止** | 因 SSE **断连**将 TestRun 标 `FAILED` / `TIMEOUT`，或将 ApprovalRequest 标 `EXPIRED`。断连 = 网络类（`HT-NET-003`），业务语义**未知** |

Token 默认 **不**订 SSE（仅 Sess）；ApiToken 调用方用轮询 GET。

#### 2.5 安全

端点必须 Sess、tenant 过滤、RBAC、限连接数。帧内禁止凭证、Restricted 正文、未脱敏 Artifact 字节、Prompt 原文、token 明文。

---

## 9. 制品与导出访问（G5）

### 3. G5 收口：制品与导出访问

对照边界 §9-G5；`02_api` §13；ADR 0007 **Proposed**；ADR 0009 **Accepted**（M0/M1 无 MinIO，启用前不得假设 S3 预签名）。

#### 3.1 硬规则

1. **引用 ≠ 授权。** `object_key`、Evidence `content_ref` / `source_object`、列表中的 `artifact_id` **不能**当作下载令牌。每次 API-221 / API-223 /（Proposed）API-222 都重验 tenant、project、RBAC、classification、保留与 Legal Hold（后两项策略 **TBD**）。
2. **M0/M1 唯一浏览器下载通道**：后端 **代理** `GET .../content`（**仅 API-221 / API-223**）。制品正文在本地卷；元数据在 `artifacts`。
3. **API-222 为 Proposed M2+**（ADR 0007 混合预签名）。M0/M1 调用 → `HT-STATE-001`（能力未启用）。**不得**当作当前默认。
4. **Restricted 永不走普通预签名**（即使未来启用 API-222）：后端代理、隔离查看或禁止导出。
5. EvidenceObject **禁止**存储预签名 URL；只存稳定 `object_key` / `source_object`。
6. 保留期 / 下载次数 / 预签名 TTL / IP 绑定 / **「90 天」一律 TBD**。**禁止**把 90 天写成默认。
7. 上传：隔离、MIME/magic、大小、解压预算、路径安全、**checksum、恶意扫描**通过后才可被解析 / 模型 / 用户消费。对象 key **服务端生成**；`original_filename` 仅展示、不作路径。
8. 响应与错误体无 Restricted 明文。敏感下载写 AuditEvent（无秘密正文）。

#### 3.2 M0/M1 vs Proposed M2+

| 里程碑 | 下载 | 预签名 | 存储 |
| --- | --- | --- | --- |
| **M0/M1（已冻结数据面）** | API-221、API-223 代理 | **不签发** | 本地卷 + `artifacts` 元数据 |
| **M2+ Proposed** | 普通大文件可短期、单对象、只读预签名（API-222）；Restricted 仍代理 | 启用 MinIO 前须迁移本地卷；TTL/次数 TBD | 私有对象存储 |

`02_api` A-11 混合模式保持 **Draft/Proposed**，不覆盖 ADR 0009 的 M0/M1 禁预签名。

---

## 10. AI 草稿暂存（G1）

### 1. G1 收口：AI 草稿暂存

对照边界 §9-G1、§6-2；`02_api` §6.2 / §10.3；开放问题 Q15。

#### 1.1 结论（本阶段可写入契约的部分）

| 项 | 契约 |
| --- | --- |
| 交互模型 | A1 = **同步受理 + 异步完成**（`02_api` §6.2）。API-180 默认 `202` + `CommandReceipt` + `generation_id`。 |
| 暂存回取 | **staging GET**：API-181 任务/暂存状态；API-182 结构化草稿。均以 `generation_id` 为回取键。 |
| 与 TestCase | **不是** TestCase 持久化 API。未人工保存前 **不**插入 `test_cases`。落库仅走 API-032（`DRAFT` + Version + 后端打 `ai-generated`）。 |
| 禁止 | `save=true` 直写 `ACTIVE`；生成端点内嵌「保存并激活」；用业务标题派生幂等键。 |
| TTL | 暂存生命周期 **TBD**。未批不得写默认小时/天。过期后 GET → `HT-RES-001`（与跨租户统一不存在；不泄露「曾存在」以外的内部路径）。 |
| 多端续审 | **TBD**。契约预留 `generation_id`；未批准前实现可仅单会话。不得写成已支持多设备。 |
| partial | **`failed_items` 必现**。后端判定 `partial`；禁止静默丢空、禁止把空 `cases` 包装成成功。 |
| 模型超参 | **temperature / 重试次数 / 分批大小由后端策略决定**。请求体 **禁止** 客户端传 `temperature`、`top_p`、`retry`、Prompt 覆写。A1 失败同参数重试 1 次（temperature 0）是服务端行为，不是前端开关。 |
| 配额 | OrgQuota Token 不足 → **`HT-QUOTA-001`**（`429`，`error.subclass=quota`）。超限拒新调用；通知 Owner 由系统发出，不另开浏览器命令。入口限流走网关 → `HT-QUOTA-002`，**不**用 Redis 配额表。 |
| 分级 | 默认出站 ≤Confidential；Restricted **fail-close**（`HT-POL-001` 或 `HT-VAL-001`，按入口校验阶段）。分类缺失按 Confidential fail-close。 |
| 降级 | `AIInvocationLog.result=degraded` 必须可感知（组织投影横幅 + 本任务 `degraded: true`）。网关不可用 → A1 入口应被后端标为不可用；**导入源登记本身不受 A1 降级阻断**（API-205 仍可受理）。 |
| HITL | 普通 A1 生成 **不默认审批**。采纳入库是后续人工流程（API-032），不是 L2+。 |

#### 1.2 与 TestCase 的边界（重申）

| 阶段 | API | 落库 |
| --- | --- | --- |
| 登记源 / 发起 A1 | API-205、API-180 | `AIInvocationLog`；**不**插入 `test_cases` |
| 暂存回取 | API-181、API-182 | 暂存介质 **TBD**（对象 key / 短表）；非 TestCase |
| 本地编辑未提交 | **无 API**（边界 §5.2） | 前端内存 |
| 保存采纳 | API-032 | TestCase `DRAFT` + Version |

可选 `generation_id` 可随 API-032 提交，仅作溯源，**不是**落库条件。

#### 1.3 权威成功（边界 §6-2）

- 前端「生成中结束」**不是**权威成功。
- 权威成功 = API-182（或短任务同步 `200` 的等价体）返回 **A1 Schema 草稿 + `failed_items`**；`partial` **由后端判定**。
- 批次全失败：`CommandReceipt.status=failed` 或 `HT-ASYNC-002`；**禁止** `200` + 空数组冒充成功。
- 是否在 API-180 同步响应里塞齐草稿：**不作为默认**（生成耗时）。短任务可用 `200` + 草稿，契约仍以受理 + 回取为准。

---

## 11. 限流语义

### 11.1 三层职责（网关 vs OrgQuota vs 应用语义）

| 层 | 职责 | 明确不是 | 超限对外 |
| --- | --- | --- | --- |
| **网关入口限流** | 保护控制面入口：按 IP / 客户端 / 路由整形，防刷 OIDC、签发、Webhook、执行发起 | 配额账本；审批是否可消费；幂等记录；OrgQuota 余量 | `HT-QUOTA-002` |
| **OrgQuota** | Token 预算、执行 slot、压测并发预算的 CAS 预留/确认/释放（`API-017` 查询投影） | QPS 计数器；网关令牌桶的事实源 | `HT-QUOTA-001` |
| **应用语义限流 / 过载保序** | 能力级公平：过载时**先**拒绝或排队 AI 增强与低优先级解析，**再**限制新执行；**尽量保留**状态查询、审计、证据写入、取消/停止、kill switch **关停**、审批**拒绝** | Redis 表设计；把限流当审批或状态机 | `HT-QUOTA-002`（频率）或与配额叠加时的 `HT-QUOTA-001` |

Redis（目标形态）仅可作**可重建**的限流辅助；不得作为审批、工作流、终止信号、授权、配额账本或幂等的唯一事实源。本契约**不**给出 Redis key / 表结构。M0/M1 无 Redis 时，入口限流仍在网关完成，应用语义限流用进程内/网关策略即可，不得另行发明存储表。

### 11.2 必须覆盖的入口

下列入口**必须**有入口限流（网关）登记；QPS、突发、窗口全部 **TBD**。L2+ **Execute** 无浏览器产品端点：消费靠行锁 + 唯一 execution intent，**不用 QPS 表达防双花**。

| 入口 | API | 限流 Owner | 与其它层关系 | QPS/窗口 |
| --- | --- | --- | --- | --- |
| OIDC start | `API-001` | 网关：IP + 客户端 | 防授权码刷取；配合 `HT-VAL-005` | **TBD** |
| OIDC callback | `API-002` | 网关：IP + `state` 相关维度（具体 **TBD**） | 必覆盖；失败仍可审计 | **TBD** |
| 会话建立后探测 | `API-006`、`API-005` | 网关；查询优先保留 | 过载时优于 AI 与新执行 | **TBD** |
| 登出 | `API-003` | 网关（宽松） | 吊销不得被限流长期挡住 | **TBD** |
| 再认证 | `API-004` | 网关 + 用户 | 与 `HT-AUTH-002` 重放纪律配合 | **TBD** |
| Token 签发 | `API-171` | 网关 + 用户/组织 | 防批量签发；吊销 `API-172` 优先保留 | **TBD** |
| Token 发起执行 | `API-080` | 网关 + OrgQuota slot | 必须 `Idempotency-Key`；scope `execute` | **TBD** |
| 会话发起执行 | `API-062` | 网关 + OrgQuota slot | 压测另受白名单 / `HT-POL-002` | **TBD** |
| L2+ Preview | `API-120` | 网关 | Preview 不是 Execute | **TBD** |
| L2+ Execute（内部消费） | **无** `/api/v1` 浏览器端点（§12） | **不行 QPS 防双花** | 行锁 consume + `(approval_request_id, bound_hash)` 唯一 intent；重复 consume 返回同一引用 | 数值不适用；若对内部 worker 调控制面命令设保护，仍 **TBD** 且非产品 API |
| 审批决策 | `API-112` | 网关；**拒绝**尽量保留 | 批准后 Execute 内部化 | **TBD** |
| AI 受理与一切 LLM 出口 | `API-180` 及 Copilot 写消息、路由测试等 | 网关 + OrgQuota Token | Restricted 默认不出站；超限通知 Owner | **TBD** |
| 入站 Webhook | `API-090` | 网关 | 验签前即可丢弃过量；去重在应用；验签失败审计 | **TBD** |

kill switch **关停**（`API-199`）在过载时**尽量保留**；**恢复**走 `API-120` `kill_switch_restore`，不得用 tighten 接口放开。

### 11.3 对外码选择

| 情况 | code |
| --- | --- |
| 预算 / slot / 压测并发不足 | `HT-QUOTA-001` |
| 入口或能力频率超限 | `HT-QUOTA-002` |
| 两者同时 | 优先表达配额（`001`）或同时在 `details` 区分，但不得发明新码名以外的第三种配额码 |

具体数字未批不得写入默认。无 Redis 限流表、无 90 天、无秒级窗口默认。

## 12. 系统内部命令（无浏览器端点）

下列**必须**存在于控制面命令集，但 **无** `/api/v1` 浏览器/Token 产品端点（Webhook 与 Token 发起已在 §6.7–6.8 单列）。

| 内部命令 | 触发 | 说明 |
| --- | --- | --- |
| 审批 consume / 创建 execution intent | APPROVED 后系统 | 行锁；不提前 EXECUTED；无 CRUD |
| execution intent 领取/DISPATCHING/确认 | Worker | 非对外资源 |
| `execution_result` 对账 | 连接器查询 | unknown 禁止盲重试 |
| TestRun VALIDATING 校验推进 | 受理后系统 | PENDING→VALIDATING→… |
| 外部 CI 触发 Job / 轮询 | 系统 | 双通道先到者 |
| 报告分片解析 / A2 聚类 / A3 A4 建议 | 终态或失败触发 | 无「生成报告」浏览器按钮 API |
| GateEvaluation 生成 / Check Run 回写 | 系统 | agent run 不生成 |
| Release 状态回传落账 | API-090 观察后命令 | |
| 环境健康探活写 health_status | 系统 | API-105 只读 |
| TestCase validity=invalid | Job 消失 | 通知 Owner |
| 审批 TTL 升级 / EXPIRED | 系统 | 不自动放行 TestRun |
| Outbox relay / Inbox 消费 | 系统 | 无产品 API |
| Temporal Start/Signal | M2+ | M0/M1 定时任务；无 Temporal HTTP API |
| 配额预留/确认/释放 | 命令内 | 无独立账本 CRUD |

Worker 回写**唯一**业务路径是已登记领域命令，不是「Worker HTTP」。

---

## 13. 覆盖矩阵

### 13.1 边界 §5.1 八类

| 类 | 覆盖 |
| --- | --- |
| 1 领域读 | API-005–012、017–018、020、024–027、030–031、037–038、050–051、056、059–061、064–067、069–071、100–101、104–105、110–111、130–131、133、140–141、144–146、150–151、155、160–161、164–165、170、183–185、190、193–194、196、220 等 |
| 2 写与状态迁移 | API-003–004、014–016、023、029、032–036、039–040、052–055、057–058、062–063、068、102–103、112–113、132、142–143、152–154、162–163、166–167、171–172、195、197–199、032 保存等 |
| 3 L2+ | API-120–121、112–113；Execute 见 §12；环境注册 API-102 |
| 4 AI | API-180–182、190–193、184–185；A2–A4 系统内部 |
| 5 导入导出 | API-028、180、200–205 |
| 6 SSE | API-210–213 |
| 7 通知 | API-021–023、019/029 |
| 8 制品 | API-220–223 |

### 13.2 边界 §2 必须调 API 的操作 → ID

| §2 操作 | API 或内部 |
| --- | --- |
| SSO 登录与会话 | API-001–006 |
| 角色判定 | 每请求；投影 API-005 |
| A1 生成 | API-180–182、205、211 |
| 草稿本地编辑 | **无 API**（§5.2） |
| 保存草稿 | API-032 |
| 提交评审 / 评审 / 废弃 | API-034–036 |
| validity 系统标记 | §12 |
| 用例详情编辑 / 版本 | API-031、033、037–038 |
| Excel 导入导出 | API-200–203 |
| 执行选项 / 发起 | API-069–070、062；Token API-080；webhook 触发 §12+API-090 |
| TestRun 列表详情 | API-060–061、064–067、210 |
| 取消终止 | API-063 |
| 转脚本 | API-068 |
| 外部 CI 链路 | API-090 + §12 |
| 审批队列与三键 | API-110–113 |
| 批准后执行 | §12 |
| 审批 TTL | §12 |
| 聚类查看/修正 | API-130–132 |
| jira_write / heal_apply | API-120 + 审批；回滚 API-039 |
| 门禁策略/历史/豁免 | API-140–146、120 |
| 门禁评估生成 | §12 |
| Release 全操作 | API-150–155、120、090 |
| 环境注册/健康 | API-100–105、120；探活 §12 |
| 压测/基线 | API-062、057–059、120 |
| 连接器/绑定/Token/投递 | API-160–172、090 |
| Copilot/技能 | API-190–195 |
| 工作台/成本/路由/kill/审计/证据/SIEM | API-020、183、196–199、024–028、040 |
| 项目/成员/计划 | API-011–016、050–055、019/029 |

### 13.3 边界 §5.2 不设 API

本地表单校验、联动置灰、动态表单渲染、查看器控件、**URL 状态**、响应式、**未提交**的 P07 草稿与聚类修正、确认对话与防抖、**SSE 订阅状态**（Zustand）。本文件不为这些分配 ID。

---

## 14. TBD 与 Proposed

### 14.1 TBD（不得当作已批默认）

- OIDC Cookie 名、会话时长、IdP claim、MFA、JIT、禁用传播、再认证窗口秒数
- 分页 `limit` 默认/上限；多数列表排序白名单细节
- 幂等键 TTL；SSE 心跳/保留窗口/连接上限/轮询秒数
- 制品预签名 TTL、下载次数、扫描器产品、保留期、Legal Hold（含「90 天」）
- A1 暂存 TTL、多端续审、暂存物理介质
- Excel 导入初始生命周期（G2）
- 通知站内形态完整产品（G4）；通知 `category` 穷举
- `project_ids` 空数组；API-106 机密上传细节
- 限流 QPS；成员 CAS 精确资源
- M0/M1 定时任务调度形态（tech_stack G1）
- CommandReceipt 是否持久化为通用表（A-01）

### 14.2 Proposed（不得当已批准实现）

- ADR 0007 混合预签名作为 **M2+** 访问；API-222
- L2 作用域化持续授权独立对象（不建 API 资源）
- GateEvaluation `not_evaluated` 枚举
- LDAP 独立端点
- API-213 组织级 hint 的事件全集
- LangGraph interrupt bridge（无 checkpoint HTTP）
- M4 `copilot_write` 启用

### 14.3 明确拒绝写进契约的项

- MCP 端点、LangGraph checkpoint API、WebSocket、gRPC、GraphQL
- execution intent CRUD、Outbox/Inbox 资源树
- Temporal / Vault / MinIO / Redis 管理 API
- Prompt 原文、token 明文（除 API-171 一次性）、`token_hash`、Webhook secret 值、`credential_ref` 值
- 把 90 天或任何未批数字写成默认 TTL

---

## 15. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1.1 | 2026-09-06 | API-001 可选 `prompt=login`；API-002 浏览器失败 302 回 SPA（`oidc=failed`）。不新增端点编号，不升格 LDAP |
| v1.0 | 2026-08-29 | 首版 Stage 7 API 契约：OpenAPI 3.1 风格、API-001… 清单、错误码、SSE/G1/G3/G5、限流语义 |
