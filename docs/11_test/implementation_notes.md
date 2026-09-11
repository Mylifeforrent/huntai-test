# Stage 11 · 实现说明与联调记录

> - **阶段**：Stage 11（`docs/11_test`）—— 前端/后端实现与联调测试
> - **日期**：2026-09-11
> - **代码基线**：分支 `main`，HEAD `075ae8b`（`chore(frontend): 固定 Vite 开发服务器绑定 127.0.0.1`）
> - **事实来源**：`docs/10_ai_context/ai_context.md` §4 切片总表、`docs/10_ai_context/context/m0.md`–`m3.md`、`frontend/` 与 `backend/` 实际代码
> - **约束**：本文只记录已落地事实，**不新增** US / FR / AC / API / 页面 / 领域对象编号，**不改变**任何切片结论（切片状态由 `ai_context.md` 维护）
> - **配套产出**：[test_report.md](test_report.md)

## 1. 范围

Stage 11 交付 M0–M3 共 32 个切片（`S-M0-01`…`S-M3-04`）的实现代码与联调验证。切片状态以 `docs/10_ai_context/ai_context.md` §4 为准：31 个「完成」+ `S-M0-01`「部分完成」；M4（`S-M4-01`）为愿景项，**本阶段未实现且不得当作已启用**。

本阶段**未**引入：Temporal / Redis / MinIO / Vault（ADR 0009 分期口径），Celery/Arq、GraphQL、gRPC、WebSocket、Redux/MobX、Next.js 等禁止项。

## 2. 运行面

| 项 | 实现 |
|---|---|
| 运行时拓扑 | 仅 PostgreSQL + API 进程 + 前端静态产物（M0/M1 口径） |
| 后端框架 | FastAPI + Starlette（显式直接依赖）+ Uvicorn + Pydantic 2 / pydantic-settings |
| 数据访问 | SQLAlchemy 2 async + asyncpg + Alembic |
| 前端 | React 19 + TypeScript 纯 SPA + Vite；TanStack Query（服务端状态）+ Zustand（本地 UI）+ React Router（仅路由与 URL，无 loader/action） |
| 对象存储 | 本地卷 `ARTIFACT_ROOT`，库内只存 `object_key` / checksum / classification；**未启用 MinIO** |
| 并发保障 | 幂等键 + CAS（`aggregate_version`）+ 行锁；M0/M1「重启不重复副作用」的唯一保障 |

后端应用组装：`backend/app/main.py`（`create_app`）+ `backend/app/api/router.py`。

## 3. 后端落地结构

### 3.1 模块与路由挂载

`backend/app/api/router.py` 共 `include_router` 12 次；11 个模块目录，其中 `ai_governance` 挂两个 router（`router.py` + `copilot_router.py`）。所有 router 前缀统一为 `/api/v1`。

| 模块（`backend/app/modules/`） | 主要切片（`ai_context.md` §4/§5） | 关键实现文件 |
|---|---|---|
| `identity_tenancy` | S-M0-01/02/03 | `service.py`（OIDC Auth Code + PKCE、会话）、`repository.py` |
| `approval_policy` | S-M0-04/05 | `policy_gate.py`（副作用四值裁决，无第 24 对象）、`service.py` |
| `ai_governance` | S-M0-06/07/08、S-M1-01、S-M1-03、S-M3-04 | `llm_factory.py`（A1–A8 唯一出口）、`a1_service.py`、`copilot_service.py` / `copilot_router.py` |
| `quota_governance` | S-M0-07/08 | `service.py`（部门预算余量、能力开关） |
| `results_evidence` | S-M0-09、S-M1-03/04、S-M2-06 | `audit_models.py` / `audit_port.py`、`a2_service.py`、`a3_service.py`、`cluster_service.py`、`evidence_service.py`、`artifacts_service.py`、`trajectory_service.py`、`object_store.py` |
| `execution_registry` | S-M0-10 | `service.py`（环境注册、健康检查、Job 发现、params schema） |
| `run_orchestration` | S-M0-13、S-M1-02/05、S-M2-01/05/07、S-M3-01 | `executor.py`、`http_runner.py`、`external_ci_executor.py`、`playwright_worker.py`、`perf_worker.py`、`agent_worker.py`、`report_adapters.py`、`variable_resolver.py`、`job_schema_validator.py`、`ci_settings.py` |
| `integration_hub` | S-M0-12、S-M2-03/04/05、S-M3-03 | `service.py`（HMAC 入站验签）、`jira_write_stub.py` |
| `test_assets` | S-M1-01/06、S-M2-02、S-M3-02 | `source_parser.py`、`locator_health.py`、`perf_baseline_service.py` |
| `quality_gates` | S-M1-07、S-M2-03/08、S-M3-02 | `evaluation_rules.py`、`evaluation_service.py`、`check_run_stub.py` |
| `release_orchestration` | S-M3-03 | `service.py`（Release Task 六态 + Readiness；Release 侧为 stub） |

> `ai_context.md` §5 模块对照表未单列 `release_orchestration`，`S-M3-03` 落在该目录。

### 3.2 共享内核

`backend/app/core/`：`config.py`（pydantic-settings，仅从仓库根 `.env` 注入）、`db.py`、`errors.py`（`ErrorEnvelope`）、`logging.py`、`middleware.py`；`backend/app/api/deps.py`（会话与租户依赖）。

### 3.3 迁移链（Alembic）

`backend/alembic/versions/` 共 25 个 revision，`0001`→`0025` 线性递进：

| revision | 归属模块 / 切片 |
|---|---|
| `0001_m0_identity` | `identity_tenancy` / S-M0-01、02 |
| `0002_approval_policy` | `approval_policy` / S-M0-05 |
| `0003_action_previews` | `approval_policy` / S-M0-04 |
| `0004_ai_governance` | `ai_governance` / S-M0-06 |
| `0005_quota_governance` | `quota_governance` / S-M0-07 |
| `0006_siem_export` | `identity_tenancy` / S-M0-09 |
| `0007_execution_registry` | `execution_registry` / S-M0-10 |
| `0008_run_orchestration` | `run_orchestration` / S-M0-13 |
| `0009_integration_hub` | `integration_hub` / S-M0-12 |
| `0010_api_tokens` | `integration_hub` / S-M0-03 |
| `0011_test_assets` | `test_assets` / S-M1-01 |
| `0012_a1_generations` | `ai_governance` / S-M1-01 |
| `0013_run_results_receipts` | `run_orchestration` / S-M1-02 |
| `0014_failure_clusters` | `results_evidence` / S-M1-03 |
| `0015_evidence_objects_idempotency` | `results_evidence` / S-M1-04 |
| `0016_test_plans` | `test_assets` / S-M1-06 |
| `0017_quality_gate_policies` | `quality_gates` / S-M1-07 |
| `0018_artifacts` | `results_evidence` / S-M2-01、05、06 |
| `0019_gate_evaluations` | `quality_gates` / S-M2-03、08 |
| `0020_ci_trigger_bindings` | `integration_hub` / S-M2-05（API-167） |
| `0021_case_result_chunk_unique` | `run_orchestration` / S-M2-05 |
| `0022_artifact_export_receipt` | `results_evidence` / S-M2-06 |
| `0023_perf_baselines` | `test_assets` / S-M3-01、02 |
| `0024_release_orchestration` | `release_orchestration` / S-M3-03 |
| `0025_copilot_sessions` | `ai_governance` / S-M3-04 |

> 归属按迁移文件名与模块 schema 整理；数据模型权威见 `docs/07_backend_design/data_model.md`，迁移不得作为模型事实源。

### 3.4 本地脚本

`backend/scripts/`：`mock_idp.py`（本地 mock IdP）、`seed_local_identity.py`（种子租户/项目/账号）、`reset_local_data.py`（本地数据复位，`APP_ENV=production` 时拒绝执行）。

## 4. 前端落地结构

### 4.1 页面与路由（P01–P25）

路由定义于 `frontend/src/App.tsx`，全部页面位于 `frontend/src/pages/`，由 `SessionGate` + `AppLayout` 包裹；`*` 落到 `NotFoundPage`。列表筛选/排序/分页走 URL（`useUrlState`）。

| 页面 | 路由 | 组件 |
|---|---|---|
| P01 工作台 | `/` | `WorkbenchPage` |
| P02 项目总览 | `/projects`、`/projects/:projectId/overview` | `ProjectOverviewPage` |
| P03 集成 | `/projects/:projectId/integrations` | `IntegrationPage` |
| P04 项目设置 | `/projects/:projectId/settings` | `ProjectSettingsPage` |
| P05 用例库 | `/projects/:projectId/cases` | `TestCaseListPage` |
| P06 测试计划 | `/projects/:projectId/plans` | `TestPlanPage` |
| P07 生成审阅页 | `/projects/:projectId/cases/generation-review` | `GenerationReviewPage` |
| P08 执行发起页 | `/test-center/kickoff` | `ExecutionLaunchPage` |
| P09 TestRun 列表/详情 | `/test-center/runs`、`/projects/:projectId/runs`、`/test-center/runs/:runId` | `TestRunListPage`、`TestRunDetailPage` |
| P10 审批中心 | `/approvals` | `ApprovalCenterPage` |
| P11 质量门禁策略 | `/gates/policies` | `QualityGatePolicyPage` |
| P12 门禁评估历史 | `/gates/evaluations` | `GateEvalHistoryPage` |
| P13 Web 用例详情 | `/projects/:projectId/cases/:caseId` | `CaseDetailPage` |
| P14 Agent 任务详情 | `/test-center/runs/:runId/agent` | `AgentTaskDetailPage` |
| P15 环境管理 | `/admin/environments`、`/projects/:projectId/environments` | `EnvironmentPage` |
| P16 性能压测 | `/test-center/performance` | `PerformancePage` |
| P17 Release 任务 | `/releases` | `ReleaseTaskPage` |
| P18 Copilot 对话 | `/assistant` | `AssistantPage` |
| P19 技能管理 | `/skills` | `SkillsPage` |
| P20 证据中心 | `/evidence` | `EvidenceCenterPage` |
| P21 AI 成本看板 | `/admin/ai-cost` | `AiCostPage` |
| P22 模型路由配置 | `/admin/model-routes` | `ModelRoutePage` |
| P23 AI 能力开关与降级 | `/admin/ai-switches` | `AiSwitchPage` |
| P24 审计检索 | `/admin/audit` | `AuditSearchPage` |
| P25 集成中心 | `/admin/integrations` | `AdminIntegrationPage` |

### 4.2 关键前端组件

- `components/layout/`：`SessionGate`（会话闸门）、`AppLayout`、`SsoRecoveryPanel`（SSO 失败后经企业 IdP 表单再认证）。
- `components/domain/`：`ApprovalCard`（审批九要素六区顺序）、`RunProgressBar`（10 态进度）、`ClusterCard`、`EvidenceViewer`、`RiskBadge`、`StatusBadge`、`AiDegradeBanner`、`PageState`（七态基线）、`UndevelopedCallout`。
- `api/`：`client.ts`、`errors.ts`（`ErrorEnvelope` 三类错误）、`authFlow.ts`、`session.ts`、`catalog.ts`、`queryKeys.ts`。
- `hooks/`：`useSession`、`useUrlState`；`stores/uiStore.ts`（Zustand）。

「未开发」呈现：`UndevelopedCallout` 出现在 `WorkbenchPage`、`TestCaseListPage`、`CaseDetailPage`、`ProjectSettingsPage`、`AdminIntegrationPage`、`PageState`、`ApprovalCard` 等——已实现端点不标未开发，未实现端点保持「未开发」态，**禁止伪造成功**。

## 5. 联调记录

### 5.1 本地三进程

后端 `backend/README.md` 记录的本地链路：

1. `uv sync` → `uv run alembic upgrade head` → `uv run python scripts/seed_local_identity.py`
2. `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
3. `uv run python scripts/mock_idp.py`（mock IdP）
4. `cd frontend && npm install && npm run dev`（Vite 开发服务器，`/api` 代理到 `http://127.0.0.1:8000`）

配置只从仓库根 `.env` 注入；本地 OIDC 联调需 `SESSION_COOKIE_SECURE=false`、`SESSION_COOKIE_SAMESITE=Lax`、`OIDC_REDIRECT_URI` 指向 Vite 回调、`OIDC_ISSUER` 指向 mock IdP。种子账号口令与 mock IdP 地址见 `backend/README.md`，**不在此复述任何密钥值**。

数据复位：`uv run python scripts/reset_local_data.py --yes`（`APP_ENV=production` 时拒绝执行）。

### 5.2 联调真实性分级

| 链路 | 真实性 |
|---|---|
| OIDC 登录/回调/登出/再认证 | 经 `scripts/mock_idp.py` 真实走 HTTP；token 交换与 `verify_id_token` 在测试中以 double 替换 |
| 项目/成员、ApiToken、审批与 Policy Gate、配额与 kill switch、审计/SIEM 投影、执行环境注册 | 真实走 API + PostgreSQL |
| AI 调用（A1/A2/A3/A4/A7、Copilot） | 真实经 `llm_factory` 唯一出口并写 `AIInvocationLog`；模型侧为 stub，**无真实模型厂商 HTTP** |
| 接口执行（HTTP runner） | 进程内 httpx；测试以 loopback 为目标 |
| Jenkins 触发 / 报告采集 | `external_ci_executor.py` 为真实 httpx 客户端；测试对 mock 服务，**无真实 Jenkins E2E** |
| Playwright / 性能 / Agent 执行 | 独立子进程 worker（`playwright_worker.py` / `perf_worker.py` / `agent_worker.py`）；性能包装 Locust，不自研引擎 |
| Jira 缺陷写入 | `integration_hub/jira_write_stub.py`，**无真实 Jira REST** |
| GitHub Check Run 回写 | `quality_gates/check_run_stub.py`，**无真实 GitHub HTTP** |
| Release 系统准备 | `release_orchestration/service.py` 内 `release_stub`，只准备 release item，**无生产发布** |
| 对象存储 | 本地卷 `ARTIFACT_ROOT`；**未启用 MinIO**，无预签名 URL |

### 5.3 运行面边界复核

- M0/M1 未启用 Temporal / Redis / MinIO / Vault；TestRun 由进程内执行器 + 子进程 worker 驱动。
- 同一步骤单一调度 Owner；`execution_result=unknown` 只对账或人工接管，无盲重试。
- SSE 仅推送展示进度，未作命令通道；`run_orchestration` 未引入 WebSocket。
- Agent Mode 结果不入任何门禁或发布证据（M2 试点口径）。

## 6. 未本地验证清单

以下事项无法在当前本地环境（mock IdP、无真实外部系统）完成端到端验证，按 `project_rules.md` §5.3 在此登记，测试执行方式见 [test_report.md](test_report.md) §5：

| # | 事项 | 现状 | 建议验证方式 | 验证人 |
|---|---|---|---|---|
| 1 | 真实 Jenkins 触发 / 报告采集 E2E | 仅对 mock 服务验证 | 接入测试实例 Jenkins 后按 `tests/test_api_external_ci_jenkins.py` 路径重跑 | 待指定 |
| 2 | 真实 Jira REST 写缺陷 | `jira_write_stub` | 配置测试 Jira 项目与凭证后做补偿与幂等复核 | 待指定 |
| 3 | 真实 GitHub Check Run 回写 | `check_run_stub` | 测试仓库开启 Checks 后验证三段式与 CI exit 影响 | 待指定 |
| 4 | 真实 Release 系统准备 release item | `release_stub` | 对接测试 Release 环境，验证审计与人工确认 | 待指定 |
| 5 | 生产 IdP 替换 mock IdP | `scripts/mock_idp.py` | 按 `S-M0-01` 残留：接入生产 IdP 并回归登录/登出/再认证 | 待指定 |
| 6 | API-222 预签名下载 | 未实现（MinIO 未启用） | MinIO 启用后补下载与权限校验 | 待指定 |
| 7 | 前端视觉效果 | 无高保真原型（`docs/09_figma_highfi/highfi_design.md` 未产出，[GAP] G6） | 原型产出后重跑 Stage 5/6 UX 一致性评审 | 待指定 |

其余已登记残留（缺陷/缺口）见 [test_report.md](test_report.md) §4。
