# Stage 11 · 测试报告与缺陷清单

> - **阶段**：Stage 11（`docs/11_test`）—— 前端/后端实现与联调测试
> - **执行日期**：2026-09-11 22:48–22:51 CST
> - **代码基线**：分支 `main`，HEAD `075ae8b`（工作树仅未跟踪目录 `.zcode/plans/`，无未提交改动）
> - **验证命令来源**：`docs/00_setup/project_rules.md` §5
> - **配套产出**：[implementation_notes.md](implementation_notes.md)
> - **结论**：8 条验证命令**全部通过，零失败**；无阻塞级缺陷；下述 4 条运行观察与既有切片残留不作为本阶段放行阻断项，按 §4 登记待处置

## 1. 环境

| 项 | 实测 | 与技术栈冻结值对比 |
|---|---|---|
| 执行人 | ZCode（AI 编码代理，本次会话） | — |
| Python | 3.14.6（`backend/.python-version` = 3.14） | 一致 |
| uv | 0.11.32 (Homebrew 2026-07-23) | **偏差**：冻结 `uv 0.12.7` |
| Node | v22.23.2 | **偏差**：冻结 Node 24 LTS |
| npm | 10.9.8 | 未在技术栈中锁定小版本 |
| PostgreSQL | `/tmp:5432 - accepting connections`（本地实例） | 本地测试按 14 使用（`backend/README.md`） |
| 测试库 | `postgresql+asyncpg://postgres@127.0.0.1:5432/huntai_test`（`backend/tests/conftest.py` 默认） | — |
| 配置 | 仓库根 `.env` 存在，含 33 个键；仅核对键名，**未读取、未输出任何值**（红线 R1） | — |
| `node_modules` / `.venv` | 均已就绪，无需安装 | — |

> 工具链偏差（uv / Node 大版本）属于**本地执行环境**事实，不是代码缺陷；合入前建议本地对齐冻结版本或在 CI 中显式固定版本后再复核本报告。

## 2. 后端验证结果

**命令**：`uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest`
（在 `backend/` 下按 `project_rules.md` §5.1 逐段执行，各段独立记录退出码）

| # | 命令 | 退出码 | 关键输出 |
|---|---|---|---|
| 1 | `uv run ruff check .` | 0 | `All checks passed!` |
| 2 | `uv run ruff format --check .` | 0 | `196 files already formatted` |
| 3 | `uv run mypy app` | 0 | `Success: no issues found in 116 source files` |
| 4 | `uv run pytest -q` | 0 | `362 passed, 8 skipped, 4 warnings in 131.86s (0:02:11)` |

> 可复现性：`uv run pytest -q` 独立重跑一次，退出码仍为 0，结果为 `362 passed, 8 skipped, 4 warnings in 130.38s (0:02:10)`——两次结果一致，本次未观察到 flake。

**跳过用例说明**：8 个 skip 全部来自 `backend/tests/test_live_smoke.py`（`test_01`…`test_08`）。该套件由 `pytest.mark.skipif(HUNTAI_LIVE != "1")` 守卫，需对**运行中的真实本地栈**执行；常规 `uv run pytest` 下不计入通过数。实跑方式（见该文件文档串）：`HUNTAI_LIVE=1 uv run pytest tests/test_live_smoke.py -q`。

**会话收尾副作用**：`conftest.py` 在 session 结束时重新执行 `seed_local_identity.py`（避免 TRUNCATE 破坏本地登录），输出 `seeded org=local-dev ...`；属预期行为。

**测试后一致性**：用例逐个 TRUNCATE 租户作用域表并逐用例 `dispose_engine()`，未发现跨用例事件循环复用导致的偶发失败；本次 131.86s 内无 flake 重跑。

## 3. 前端验证结果

**命令**：`npm run lint && npx tsc --noEmit && npm run build && npm run test`
（在 `frontend/` 下按 `project_rules.md` §5.2 逐段执行）

| # | 命令 | 退出码 | 关键输出 |
|---|---|---|---|
| 1 | `npm run lint`（= `tsc -b`） | 0 | 无告警 |
| 2 | `npx tsc --noEmit` | 0 | 无输出（零错误） |
| 3 | `npm run build` | 0 | vite 8.2.2，`2042 modules transformed`，`✓ built in 330ms` |
| 4 | `npm run test`（vitest run） | 0 | `Test Files 31 passed (31)` / `Tests 104 passed (104)` / `Duration 16.75s` |

**构建产物**：

| 产物 | 体积 | gzip |
|---|---|---|
| `dist/index.html` | 0.39 kB | 0.27 kB |
| `dist/assets/index-_y2BoQTN.css` | 28.57 kB | 6.47 kB |
| `dist/assets/index-tZh7sYZi.js` | 616.37 kB | 182.53 kB |

前端测试文件（31）构成：页面测试 23 个（覆盖 P01–P18、P20–P25 共 24 个页面；P02 与 P04 合并于 `ProjectPages.test.tsx`）、领域组件 4 个（`ApprovalCard` / `ClusterCard` / `EvidenceViewer` / `RunProgressBar`）、布局 1 个（`SessionGate`）、纯函数与 API 3 个（`utils` / `errors` / `authFlow`）。

## 4. 缺陷与残留清单

> 本节**只记录，不修复**。第 4.1 条为本次实跑新发现；4.2 条为 `context/m0.md`–`m3.md` 已登记残留的汇总（去重、按影响排序）；4.3 条为范围性缺口。处置建议需单开 `fix/` 分支，本次不动代码。

### 4.1 本次运行新发现（4 条告警 + 2 条环境偏差）

| # | 级别 | 现象 | 位置 | 处置建议 |
|---|---|---|---|---|
| W1 | 低 | `AuthlibDeprecationWarning: authlib.jose module is deprecated, please use joserfc instead` | `backend/app/modules/identity_tenancy/service.py:10` | 待 Authlib 2.0 前迁移到 joserfc；当前不影响功能，属上游弃用提醒 |
| W2 | 低 | pytest 收集告警 ×3：把领域模型 `TestRun` / `TestCase` / `TestPlan` 当作测试类收集 | `backend/tests/test_api_050_055_test_plans.py` 间接导入的 `run_orchestration/models.py`、`test_assets/models.py` | 为模型类加 `__test__ = False` 或测试内改用别名导入，消除噪音（纯测试可读性，无功能影响） |
| W3 | 低 | 单 chunk 超过 500 kB：`index-*.js` 616.37 kB | `frontend` 构建 | 按 Vite 提示做动态 `import()` 代码分割；当前不影响功能与验收 |
| W4 | 低 | Vitest stderr：`The current testing environment is not configured to support act(...)` ×2 | `RunProgressBar.test.tsx`、`ApprovalCard.test.tsx` | 在 `src/test/setup.ts` 显式设置 `globalThis.IS_REACT_ACT_ENVIRONMENT = true`，消除告警 |
| O1 | 观察 | 本地 uv 0.11.32 ≠ 冻结 uv 0.12.7 | 本地环境 | 对齐冻结版本后复核；CI 中显式固定 |
| O2 | 观察 | 本地 Node v22.23.2 ≠ 冻结 Node 24 LTS | 本地环境 | 同上 |

### 4.2 已登记切片残留（`context/m0.md`–`m3.md` 汇总）

| # | 级别 | 残留 | 来源切片 | 处置建议 |
|---|---|---|---|---|
| D1 | 中 | **2026-09-11 部分闭环**（详见 §7）。已补：租户边界强制（路由认证一致性测试 + AC-003 跨租户系统级回归 + 无上下文拒绝）、生产 IdP 对接能力（discovery 端点 / `iss`·`aud`·`azp` 与算法白名单 / 生产拒绝 loopback issuer）、API-006 过期提示 UI。**仍残留**：ORM 层租户自动过滤未做（本轮按用户决定只做 API 边界）；生产 IdP 真实凭证与端到端验证未做 | S-M0-01（部分完成） | 前者需单开切片评估收益与回归面；后者待 IdP 选型与凭证就位 |
| D2 | 中 | API-022 通知角标未做（前端缺口 G4）；`is_expiring` 阈值 TBD 故省略；`gate_anomalies` 恒 `[]`（M0 登记理由为「无 GateEvaluation 表」，而迁移 `0019_gate_evaluations` 已在 S-M2-03 落地，**是否已解除未回写待核**） | S-M0-11 | 先核实 `gate_anomalies` 现状再决定是否补；补 TBD 阈值需产品裁决 |
| D3 | 中 | API-165 / API-166 缺失；`waived` 结论的 Check Run 回写语义未定义；p95 / error_rate 在 S-M2-08 时固定 `not_measured` | S-M2-03、S-M2-04、S-M2-08 | S-M3-02 已接 PerfBaseline，需核实 `not_measured` 是否已解除并补 API-165/166 |
| D4 | 中 | 无真实外部系统 E2E：Jenkins / Jira REST / GitHub Check Run / Release 系统（均 stub 或 mock 服务） | S-M1-05、S-M2-03/04/05、S-M3-03 | 见 [implementation_notes.md](implementation_notes.md) §6 未本地验证清单 |
| D5 | 中 | API-222 预签名下载未实现（MinIO 未启用）；保留期 / Legal Hold 策略 TBD 未实现 | S-M2-06 | 待 MinIO 启用（M2+ 前置满足后）；保留期需产品与法务裁决 |
| D6 | 低 | `HT-QUOTA-002` 未实现（签发限流窗口 TBD）；`last_used_at` 未异步更新；无 API-080 | S-M0-03 | TBD 数值须产品裁决，禁止臆造默认值 |
| D7 | 低 | Excel 导入 API-200 / 202 未做；A1 TTL 产品默认未设 | S-M1-01 | Excel 非本阶段承诺范围（只做 OpenAPI/Postman/curl）；TTL 待裁决 |
| D8 | 低 | `${func}` 无目录时恒失败；`CaseResult.outcome` 使用未冻结的 `passed/failed/incomplete` | S-M1-02 | 前者补清晰报错信息；后者需回上游确认枚举口径 |
| D9 | 低 | WAITING_EXTERNAL 超时仅可见 dwell，无超时动作；`TEST_RUN_HEARTBEAT_TIMEOUT_SECONDS` 秒数 TBD | S-M1-05、S-M1-02 | 秒数须裁决；超时动作需设计确认 |
| D10 | 低 | A3 为 factory stub（非真实视觉模型）；health 码为 GET 投影而非冻结枚举 | S-M2-02 | 真实视觉模型接入属后续；health 码枚举需回上游确认 |
| D11 | 低 | Agent Worker：manifest 取自 run params（待 M4 SkillVersion）；工具集仅 `request`；无真实 LLM Agent 运行时（确定性 worker） | S-M2-07 | M4 范围，本阶段不启 |
| D12 | 低 | 性能：真实目标系统 E2E 未做；`run_time>60s` 长时压测未实测；Locust 未用分布式；基线容忍度 API-059 不参与自动判定；压测 `min_pass_rate` 仍按 CaseResult 通过率 | S-M3-01、S-M3-02 | 补长时压测与真实目标演练；容忍度语义待契约确认 |
| D13 | 低 | Copilot：无真实 LLM；工具白名单仅 `query_test_assets`；citations 的 `evidence_ref` 无实值；`copilot_write` / API-194/195 属 M4 | S-M3-04 | M4 范围；M3 只读最小版符合切片口径 |
| D14 | 低 | Release：Readiness 无 yellow 分支（策略 TBD）；`scope.plan_ids` 留空，P06/P25 无新增入口 | S-M3-03 | 策略待裁决 |
| D15 | 低 | S-M2-05：allure 路径须 manifest / collect_config 显式声明；超大报告先全量 parse 再分批入库 | S-M2-05 | 流式解析优化待排期 |
| D16 | — | **[CONFLICT-5]** `gate_waiver` 是否覆盖 Readiness 豁免：C1 与边界规范 §2.7 不一致 | 跨切片 | **禁止自行裁决**；须用户裁决后登记 `change_log` |

### 4.3 范围性缺口

| # | 级别 | 缺口 | 说明 |
|---|---|---|---|
| G4 | 中 | P03 集成页无独立前端测试文件 | 31 个前端测试文件中无 `IntegrationPage.test.tsx`；该页在 M2 有真实交互（CI 触发绑定、webhook），建议补组件交互测试 |
| G6 | 中 | Stage 5/7 产品原型缺位，`docs/09_figma_highfi/highfi_design.md` 未产出 | 页面以 `frontend_design_spec-v1.0.md` 为临时权威；七态呈现、审批九要素分区、等待态滞留等 UX 一致性**无法跨阶段复核**；原型产出后须重跑 Stage 5/6 UX 评审并登记 |
| — | 低 | P19 技能页（`SkillsPage`）无测试 | M4 愿景页面，本阶段不启用，无测试符合预期 |

## 5. 未本地验证事项的验证方式（`project_rules.md` §5.3）

真实外部系统与生产 IdP 无法在本地环境验证，明细与建议验证方式见 [implementation_notes.md](implementation_notes.md) §6。要点：接入测试实例 Jenkins / Jira / GitHub / Release 与生产 IdP 后，按对应既有测试文件路径重跑；API-222 待 MinIO 启用后补下载与权限校验。

**验证人**：执行 ZCode（AI 编码代理，2026-09-11）；**人工复核签署：待指定**。

## 6. 结论与后续

1. **8 条合入前验证命令全部零失败**：后端 `ruff check` / `ruff format --check` / `mypy app` / `pytest`（362 passed, 8 skipped）；前端 `lint` / `tsc --noEmit` / `build` / `test`（31 files, 104 tests passed）。
2. **无阻塞级缺陷**。本次新发现的 4 条均为低级别告警/噪音（W1–W4），2 条为本地工具链版本偏差（O1、O2）。
3. **Stage 11 状态**：代码实现与验证已完整；本报告补齐原缺失的阶段约定产出（`implementation_notes.md` + `test_report.md`）。`S-M0-01` 仍为「部分完成」（残留见 §4.2 D1 与 §7）。
   - **勘误（2026-09-11）**：本报告 §4.2 与本节原先称「S-M0-01 残留阻塞 M1 放行」，与事实源不符。`docs/10_ai_context/ai_context.md` §4.1 明确 M1 放行受 **PRD B.10 Gate**（越权回归全阻断；AI 调用无旁路；任务无永久 running；注册 CI 健康检查与 Job 发现）与**一致性检查 FAIL 项**约束，并明确 S-M0-01 残留**不阻塞**进 M1。此前的表述把 S-M0-01 残留与「一致性检查 FAIL 项」混为一谈，现更正。
   - `[CONFLICT-5]`（`gate_waiver` 是否覆盖 Readiness 豁免）仍待用户裁决，禁止实现中自行选边。
4. **本报告 §1–§6 记录的是 Stage 11 收口时的基线**（HEAD `075ae8b`，后端 362 / 前端 104）。后续 D1 的代码变更与验证结果记在 §7，**未覆盖**上表基线。
5. **下一步**：可进入 Stage 12（`docs/12_deployment/deployment.md`）；`deployment.md` 中原属「无法本地验证」的部署配置项，按 §5.3 继续记录验证方式与验证人。

## 7. D1（`S-M0-01` 残留）验证补充 · 2026-09-11

> 分支 `feat/s-m0-01-residual`；范围经用户确认：租户隔离只做 API 边界强制（不做 SQLAlchemy 自动过滤 / PostgreSQL RLS）、生产 IdP 只做对接能力与生产守卫、API-006 只渲染服务端布尔（不发明 TBD 阈值）、membership 语义不一致仅登记。

### 7.1 验证结果（8 条命令零失败）

| 命令 | 结果 |
|---|---|
| `uv run ruff check .` | 通过 |
| `uv run ruff format --check .` | `200 files already formatted` |
| `uv run mypy app` | `Success: no issues found in 116 source files` |
| `uv run pytest -q` | **`442 passed, 8 skipped, 4 warnings in 151.89s`**（基线 362 → 442，新增 80 条） |
| `npm run lint`（`tsc -b`） | 通过 |
| `npx tsc --noEmit` | 通过 |
| `npm run build` | 2043 modules，`dist/assets/index-*.js` 617.53 kB（gzip 182.91 kB），362ms |
| `npm run test` | **`Test Files 33 passed (33)` / `Tests 112 passed (112)`**（基线 31/104，新增 2 文件 8 用例） |

告警仍为 4 条（authlib `jose` 弃用 + 3 条 `PytestCollectionWarning`），未新增告警类别。

### 7.2 新增测试

| 文件 | 条数 | 覆盖 |
|---|---|---|
| `backend/tests/test_route_auth_conformance.py` | 4 | 每个 `/api/v1` 路由必须声明认证依赖或登记为公开/内联；登记表无失效条目；不重叠；内联认证的 API-062 无凭证时 401 |
| `backend/tests/test_tenant_isolation_regression.py` | 40 | 38 个详情端点以未知 id 访问统一 404 `HT-RES-001`（不泄露存在性）；未认证 401 不伪装 404；他租户 project id 不可枚举 |
| `backend/tests/test_tenant_context_rejection.py` | 12 | 未认证 401；会话租户只来自 `AuthSession`；指向未知 org 的会话解析为 `None`；4 个 membership 门禁端点无 membership → 403 `HT-IAM-001` |
| `backend/tests/test_oidc_hardening.py` | 24 | discovery 取端点/缓存/issuer 不匹配/缺 jwks_uri/非对象文档；`iss`·`aud`·过期·`HS256`·`none`·nonce·`azp` 拒绝；生产守卫（loopback 检测 + 启动即拒） |
| `frontend/src/components/layout/SessionReauthNotice.test.tsx` | 4 | 不需要时为 null；需要时提示与 CTA；CTA 触发既有再认证流；失败回显并恢复可用 |
| `frontend/src/hooks/useSession.test.tsx` | 4 | `HT-AUTH-002` 不再阻断外壳（保持可浏览）；`HT-IAM-001` 仍阻断；`useReauthRequired` 读 API-006 布尔 |

### 7.3 已知偏离与新增登记

| # | 级别 | 内容 | 说明 |
|---|---|---|---|
| N1 | 中 | **无 membership 用户语义不一致**：`/api/v1/projects` 等用 `require_session` → 200 空列表；4 个端点用 `require_session_with_membership` → 403 `HT-IAM-001` | 本次按用户决定**保持现状仅登记**。两者都不跨租户（数据仍限本组织），但同一类调用方在不同端点得到不同语义，需产品/契约裁决 |
| N2 | 中 | 一致性测试只保证「路由不漏鉴权」，**不保证**「每个仓储查询都带 `organization_id`」 | 因为本轮不做 ORM 自动过滤/RLS；该限制已写入 `test_route_auth_conformance.py` 模块文档串，不掩盖 |
| N3 | 中 | `POST /api/v1/test-runs` 采用**内联认证**（bearer 优先、支持 execute scope 的 ApiToken），未用 `Depends(require_*) ` | 行为正确（无凭证 401 已测），但因不走依赖而不被一致性规则直接覆盖，故显式登记为「内联认证路由」并要求伴随行为测试。是否重构为统一依赖待评估 |
| N4 | 低 | `_IncludedRouter` 懒加载结构：`create_app().routes` 不直接展开为 `APIRoute` | 一致性测试用递归穿透 `original_router` 的方式遍历；若升级 FastAPI 改变该结构，该测试会失败（fail-close，属预期） |
| N5 | 低 | W4（Vitest `act(...)` 环境未配置）在本轮新增的两个前端测试文件内已按现有惯例显式设置 `IS_REACT_ACT_ENVIRONMENT`，**全局 setup 仍未设置** | 其余文件的同类告警仍在，未扩大范围 |

### 7.4 未本地验证（沿用 §5 与 implementation_notes §6）

生产 IdP 的真实凭证、端点形态、JWKS 轮换与 client 认证方式**仍无法本地验证**；本轮只证明「对接能力与守卫存在且被测试覆盖」，**不等于**已对真实 IdP 验证。验证人：执行 ZCode（2026-09-11），人工复核签署待指定。

