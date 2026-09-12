# 程序员教程：UI 操作 → 底层模块 → 对应测试

> **这篇是给谁看的**：要读 / 改 HuntAI Test 代码的人（第一次接手本仓库的后端、前端、测试同学）。
> **前置**：已经按 [`local-testing-guide.md`](./local-testing-guide.md) 把栈起起来；建议先照着 [`user-ui-guide.md`](./user-ui-guide.md) 在 UI 里亲手点一遍——**先有现象，再看代码**，比直接读源码快得多。
> **本文的写法**：从「用户点了什么」出发，一路向下到「哪段代码 / 哪张表 / 哪条测试」。文中所有 `文件:行号` 与 `测试文件::用例名` 都取自当前仓库代码，逐一 grep 校验过，不是示意。

**路径约定**：除特别说明外，所有路径相对**仓库根**（例如 `backend/app/modules/...`）。命令行若在 `backend/` 下执行会特别标注。

---

## §0 三栏读法：把 UI 现象翻译成代码

每一个 UI 动作，都能翻译成同一套三段式：

| 栏位 | 你要问的问题 | 去哪找 |
|---|---|---|
| **① 触发** | 点这个按钮，发的是哪个 `API-NNN`？ | 页面文件 + `frontend/src/api/catalog.ts` |
| **② 裁决** | 服务端哪个函数决定「能不能做」？ | `backend/app/modules/<module>/router.py` → `service.py` |
| **③ 证据** | 怎么证明它真的这么做了？ | `backend/tests/<test_file>::<test_name>` |

本文 §2 就是这张翻译表，§3 讲横切原理，§4 是测试锚点。**读代码时请始终带着「这条路径有测试吗」的问题。**

---

## §1 读代码前必须建立的 6 条心智模型

这 6 条是 `AGENTS.md` §3 / §4 的工程化落地；不理解它们，你会把「前端置灰」当成安全边界，或者把「调用返回 200」当成业务成功。

### 1. 前端只呈现，后端裁决

五类状态机（TestRun / ApprovalRequest / ReleaseTask / ExecutionEnvironment / TestCase）**只在后端流转**。前端请求状态、渲染状态，**禁止推演迁移**：

- P09 页头明写「状态由服务端下发，前端不推演迁移」。
- 前端置灰只是提示；`backend/app/modules/*/service.py` 里的角色校验才是边界（例如 `test_assets/service.py:81 _require_project_role`）。

> 反例：不要在前端根据 `PENDING_REVIEW` 自己算出「下一步该是 ACTIVE」。后端给什么就画什么。

### 2. 受理 ≠ 完成

写命令被接受，不等于业务已完成。HTTP 状态因端点而异，**以权威 GET 为准**：

- `POST /api/v1/test-runs`（API-062）当前实现返回 **200** + 回执，TestRun 初始是 `PENDING`；真实终态靠 `GET /api/v1/test-runs/{id}`（API-061）轮询。
- A1 生成（API-180）返回 **202** + `accepted`，草稿要另查 API-182。
- **禁止**收到 200/202 就显示「执行成功」。前端只能显示「受理中」，直到 GET 到终态。

### 3. 写命令 = 幂等键 + 请求哈希

所有命令都带 `Idempotency-Key` 头。服务端按 `(command_type, idempotency_key)` 查记录：

- 查不到 → 执行，落一条记录（存 `request_hash` + `response_ref`）。
- 查到且 `request_hash` **相同** → 直接回放原响应，**不重复产生副作用**。
- 查到但 `request_hash` **不同** → `ValueError("idempotency_conflict")` → `409 HT-IDEM-001`。

代码锚点：

| 环节 | 位置 |
|---|---|
| 前端生成 UUID | `frontend/src/api/client.ts`（导出 `newIdempotencyKey`，随请求写 `Idempotency-Key` 头） |
| 头部校验 | `backend/app/modules/identity_tenancy/service.py` `require_idempotency_key` |
| 请求哈希 | 每个模块私有：`backend/app/modules/<module>/repository.py` `hash_request_body` |
| 记录表 | `<私有schema>.command_idempotency_records`（每个写模块各有一张） |

> 网络未决（超时 / 5xx）时**不要换新幂等键**——先 GET 对账。换键就等于放弃了「重启不重复副作用」这道唯一保障（M0/M1 没有 Temporal）。

### 4. 可变聚合 = `expected_version` CAS

改已有对象（改策略、禁用环境、审批决定）要带 `expected_version`；后端乐观锁比对，版本不符返回 `HT-VER-001`。

- 典型实现：`backend/app/modules/execution_registry/service.py:628 disable_execution_environment`、`backend/app/modules/quality_gates/service.py:237 patch_policy_for_caller`。
- 前端拿到老版本号时，正确做法是**刷新拿新版本再操作**，而不是本地自增。

### 5. 错误信封链路（`ValueError` → `AppError` → JSON）

service 层**不构造 HTTP 响应**，只抛 `ValueError("<短码>")`；router 把它翻译成带类型、带 HTTP 状态的 `AppError`；再由统一异常处理器序列化成 `ErrorEnvelope`。

```
service 抛 ValueError("state")
   → router._map_write_error / _map_read_error   （把短码映射成 AppError）
   → app/core/errors.py 里的构造函数（precondition_failed / version_conflict / ...）
   → app_error_response → {"error": {code, class, subclass, message, retryable, trace_id}}
```

`backend/app/modules/execution_registry/router.py:92 _map_write_error` 的映射表就是这份契约的实现（工厂在 `app/core/errors.py`）：

| service 短码 | HTTP / code |
|---|---|
| `forbidden` | 403 `HT-IAM-001` |
| `not_found` | 404 `HT-RES-001` |
| `validation` | 400 `HT-VAL-001` |
| `policy_deny` / `policy_undeclared` | 403 `HT-POL-001` / `HT-POL-002` |
| `require_reauth` | 401 `HT-AUTH-002` |
| `state` | 409 `HT-STATE-001` |
| `version` | 409 `HT-VER-001` |
| `idempotency_conflict` | 409 `HT-IDEM-001` |
| `four_eyes` | 403 `HT-IAM-002`（审批 router 另映射；环境注册走审批模块） |

`run_orchestration/router.py:98` 在此基础上多了 `token_project` / `schema` / `perf_policy` 三条。审批决定另有 `HT-STATE-002`（已消费）、`HT-APPR-001`（`param_hash` 失效）。

> **调试含义**：在 service 里 grep 短码字符串，能立刻定位「这个报错从哪来」。完整码表见 `docs/07_backend_design/api_spec.md` §4.3。不要把 `HT-IDEM-001` / `HT-VER-001` 记成 `HT-STATE-001`。

### 6. 副作用等级由代码冻结，不是配置

`backend/app/modules/approval_policy/policy_gate.py` 是硬编码白名单，**不允许**通过数据库或界面改等级：

```python
FROZEN_ACTION_LEVELS = {
    "jira_write": "L2", "env_register": "L3", "heal_apply": "L3",
    "perf_high_risk": "L3", "gate_waiver": "L3", "kill_switch_restore": "L3",
    "release_push": "L4", "agent_tool_action": None, "copilot_write": "DISABLED",
}
```

`evaluate_policy_gate` 的判定顺序：未知动作 → `DENY("undeclared")`；`copilot_write` → `DENY("state")`；`perf_high_risk` → `DENY("undeclared")`；L0/L1 → `ALLOW`；其余 L2+ → `REQUIRE_APPROVAL`；若 `reauth_required=True` → `REQUIRE_REAUTH`。

> 这解释了 UI 教程里那些「为什么」：为什么注册环境必然进审批（`env_register` 冻结为 L3）、为什么阈值超时窗会要重新认证（`REQUIRE_REAUTH`）、为什么未声明等级的动作一律拒绝（`undeclared` DENY）。

---

## §2 UI → 代码全链路映射表

按 UI 教程的执行顺序排列。`API-NNN` 编号取自 `frontend/src/api/catalog.ts` 的 `PAGE_APIS`（P01–P25）。

### 2.1 登录与项目（P01 / P02）

| UI 操作 | 页面文件 | 路由 | API | router | service | 主要表 | 关键错误码 |
|---|---|---|---|---|---|---|---|
| 打开站点自动登录 | `frontend/src/components/layout/SessionGate.tsx` | 任意 | API-001 / API-002 | `identity_tenancy/router.py:163,187` | `identity_tenancy/service.py` | `auth_sessions`、`users` | `HT-AUTH-001` |
| 工作台 | `pages/WorkbenchPage.tsx` | `/` | API-020 | `identity_tenancy/router.py:313` | `.../service.py` | — | — |
| 项目总览 | `pages/ProjectOverviewPage.tsx` | `/projects/:projectId/overview` | API-011 / API-012 | `identity_tenancy/router.py:347,364` | `.../service.py` | `projects`、`project_members` | `HT-RES-001` |
| 再认证（step-up） | 由 401 拦截触发 | — | API-004 | `identity_tenancy/router.py:270` | `.../service.py` | `auth_sessions` | `HT-AUTH-002` |

> 会话是 **HttpOnly Cookie**，前端不持有 IdP token 明文；`frontend/src/api/client.ts` 固定 `credentials: "include"`。禁止把它挪进 `localStorage`。

### 2.2 建门禁策略（P11）

| UI 操作 | 页面文件 | 路由 | API | router | service | 主要表 | 关键错误码 |
|---|---|---|---|---|---|---|---|
| 列策略 / 创建 / 改策略 | `pages/QualityGatePolicyPage.tsx` | `/gates/policies` | API-140 / API-142 / API-143 | `quality_gates/router.py:102,144,183` | `quality_gates/service.py:166 create_policy_for_caller`、`:237 patch_policy_for_caller` | `quality_gate_policies` | `HT-VER-001`、`HT-IDEM-001`、`HT-IAM-001` |

要点：

- `report_only` 与 `blocking` 的差别体现在**创建/切换阻塞模式需要二次确认**（前端 `confirm` + 后端校验）；语义上「记录 fail」≠「阻断发布」。
- 阈值合法性在 `quality_gates/service.py:38 _validate_thresholds`：三个键必须都在且为数字，缺键即 `validation`。前端空输入会 `Number("") === 0` 再提交，不是「留空就不设限」。
- 改策略**不会重写历史评估**：`gate_evaluations` 是 append-only，策略版本与历史评估解耦（有测试保护，见 §4）。

### 2.3 生成并采纳用例（P07 → P05）

| UI 操作 | 页面文件 | 路由 | API | router | service | 主要表 | 关键错误码 |
|---|---|---|---|---|---|---|---|
| 发起 A1 生成 | `pages/GenerationReviewPage.tsx` | `/projects/:projectId/cases/generation-review` | API-180 | `ai_governance/router.py:291` | `ai_governance/a1_service.py:137 create_generation_for_caller` | `a1_generations`、`ai_invocation_logs` | `HT-POL-001`、`HT-QUOTA-001` |
| 轮询生成状态 / 取草稿 | 同上 | 同上 | API-181 / API-182 / API-211(SSE) | `ai_governance/router.py:336,352,443` | `a1_service.py:234 run_generation_background`、`:424 get_generation_drafts_for_caller` | 同上 | — |
| 采纳成用例 | 同上 → `TestCaseListPage.tsx` | → `/projects/:projectId/cases` | API-032 | `test_assets/router.py:302` | `test_assets/service.py:527 create_test_case_draft_for_caller` | `test_cases`、`test_case_versions` | `HT-IAM-001` |

要点：

- **A1 在本仓库是本地确定性 stub**：`ai_governance/llm_factory.py` 的 `invoke`（`llm_factory.py:119`）不调用任何厂商 API，因此本地不需要模型 Key、也不需要外网。`InvokeInput`/`InvokeOutput` 在 `llm_factory.py:24,38`。
- **必须写 `AIInvocationLog`**：`a1_service.py` 生成后会落 `ai_invocation_logs`，这是「AI 不得绕过日志」红线的实现。工单号 `run_generation_background`。
- **数据源类型**：`a1_service.py:29 VALID_SOURCE_TYPES = {"openapi", "postman", "curl"}`；`test_assets/service.py:46` 有同名常量。
- **YAML 前缀一律被拒**：`a1_service.py:93 _reject_non_json_spec` 先检查原文是否以 `---` / `openapi:` / `swagger:` 开头（含 `curl`）；随后仅 `openapi`/`postman` 再强制 `json.loads`。所以 `curl` 不受「必须是 JSON 对象」限制，但 YAML 外观的原文仍会被拒。解析器 `_CURL_URL_RE` 在 `test_assets/source_parser.py:136`。
- **采纳 ≠ 落库生效**：API-032 建的是 `DRAFT`；`API-032` 之前生成草稿**不会**自动建用例（有测试保护）。
- **kill switch**：AI 总开关关闭时 API-180 被拦、API-205（登记原文）不被拦——见 `a1_service.py:83 _kill_switch_blocks`。

### 2.4 用例生命周期（P05 / P04）

| UI 操作 | 页面文件 | 路由 | API | router | service | 主要表 | 关键错误码 |
|---|---|---|---|---|---|---|---|
| 提审 | `pages/TestCaseListPage.tsx` | `/projects/:projectId/cases` | API-034 | `test_assets/router.py:383` | `test_assets/service.py:794 submit_review_for_caller` | `test_cases` | `HT-STATE-001` |
| 审核通过 / 驳回 | 同上 | 同上 | API-035 | `test_assets/router.py:414` | `test_assets/service.py:846 review_test_case_for_caller` | `test_cases` | `HT-IAM-001`、`HT-STATE-001` |
| 改草稿 | `pages/CaseDetailPage.tsx` | `/projects/:projectId/cases/:caseId` | API-033 | `test_assets/router.py:343` | `service.py:685 patch_test_case_draft_for_caller` | `test_cases`、`test_case_versions` | `HT-STATE-001` |
| 回滚版本 | 同上 | 同上 | API-039 | `test_assets/router.py:448` | `service.py:922 rollback_test_case_for_caller` | `test_case_versions` | `HT-STATE-001` |

**这一节最重要的纠正**：**用例评审（API-035）服务端不强制四眼**，发起人可以把自己的用例改 `ACTIVE`。四眼强制**只作用在 API-112 审批决定上**。UI 教程因此建议「换第二个账号审核」是习惯而非硬约束——不要在学习代码时把两者混为一谈。

### 2.5 执行环境注册与审批（P15 → P10）

| UI 操作 | 页面文件 | 路由 | API | router | service | 主要表 | 关键错误码 |
|---|---|---|---|---|---|---|---|
| 注册环境 | `pages/EnvironmentPage.tsx` | `/projects/:projectId/environments` | API-102 | `execution_registry/router.py:158` | `service.py:391 register_execution_environment` | `execution_environments`、`job_contracts`、`approval_requests` | `HT-POL-001/002`、`HT-AUTH-002`、`HT-IAM-001` |
| 列环境 / 详情 | 同上 | 同上 | API-100 / API-101 | `execution_registry/router.py:116,143` | `service.py:196,274` | `execution_environments` | `HT-RES-001` |
| 参数 Schema | `pages/ExecutionLaunchPage.tsx` | `/test-center/kickoff` | API-070 | `execution_registry/router.py:261` | `service.py:339 get_params_schema_for_caller` | `job_contracts` | — |
| 审批队列 | `pages/ApprovalCenterPage.tsx` | `/approvals` | API-110 / API-111 | `approval_policy/router.py:214,246` | `service.py:935,1036` | `approval_requests` | — |
| 批准 / 拒绝 / 重新提交 | 同上 | 同上 | API-112 / API-113 | `approval_policy/router.py:289,321` | `service.py:1092 submit_approval_decision`、`:1515 resubmit_approval_request` | `approval_requests` | `HT-IAM-002`、`HT-VER-001`、`HT-STATE-002`、`HT-APPR-001` |

**环境注册的完整链路**（`execution_registry/service.py:391`，值得精读一遍）：

1. 幂等回放检查：`get_idempotency_record`；命中且哈希一致直接返回。
2. 禁写字段：`FORBIDDEN_REGISTER_KEYS` 命中任一 → `policy_deny`。
3. secret 扫描：`service.py:168 _reject_nested_secrets` 递归拒绝 `secret/token/password/...` 明文；**凭证只存 `credential_ref`**。
4. 角色校验：必须项目 `owner` / `admin`，否则 `forbidden`。
5. 组门禁载荷：`service.py:176 _build_gate_payload`。
6. 再认证判定：`compute_reauth_required(...)`。
7. 门禁裁决：`evaluate_policy_gate(action_type="env_register", ...)`。
   - `DENY("undeclared")` → `policy_undeclared`；`DENY` → `policy_deny`；`REQUIRE_REAUTH` → `require_reauth`；非 `REQUIRE_APPROVAL` → `policy_deny`。
8. 建环境（此时状态是 `PENDING_APPROVAL`）+ 建 job contracts。
9. `approval_command.create_env_register_approval(...)` 建审批单，`initiator_id = 当前用户`。
10. 写 `AuditEvent` + 写幂等记录（存 `response_ref`）。

批准后的激活在 `approval_policy/service.py:1092 submit_approval_decision`：校验 `param_hash` / `expected_version` → 写决定 → 驱动目标对象激活（环境转 `ACTIVE`）。

### 2.6 发起执行与看结果（P08 → P09）

| UI 操作 | 页面文件 | 路由 | API | router | service | 主要表 | 关键错误码 |
|---|---|---|---|---|---|---|---|
| 选项（可选环境/用例） | `pages/ExecutionLaunchPage.tsx` | `/test-center/kickoff` | API-069 | `run_orchestration/router.py:305` | `service.py:765 get_execution_options_for_caller` | `execution_environments`、`test_cases` | — |
| 发起 TestRun | 同上 | 同上 | API-062 | `run_orchestration/router.py:191` | `service.py:407 start_test_run_session` → `:428 _start_test_run_core` | `test_runs`、`command_receipts` | `HT-STATE-001`、`HT-POL-001/002` |
| 列 / 详情 / 轮询 | `pages/TestRunListPage.tsx`、`TestRunDetailPage.tsx` | `/test-center/runs[/:runId]` | API-060 / API-061 | `run_orchestration/router.py:139,176` | `service.py:307,369` | `test_runs` | `HT-RES-001` |
| SSE 进度（**非命令通道**） | 同上 | 同上 | API-210 / API-212 | `run_orchestration/router.py:575,460` | SSE 生成器 | — | — |
| 取消 | `TestRunDetailPage.tsx` | `/test-center/runs/:runId` | API-063 | `run_orchestration/router.py:264` | `service.py:628 cancel_test_run` | `test_runs` | `HT-STATE-001` |
| 用例结果表 | `TestRunDetailPage.tsx` | 同上 | API-064 / API-065 | `results_evidence/router.py:398,427` | `results_evidence/case_results_service.py:75,121` | `case_results` | — |
| StepRun（证据查看器） | 同上 | 同上 | API-066 | `results_evidence/router.py:446` | `case_results_service.py:146` | `step_runs` | — |
| 失败聚类 | 同上 | 同上 | API-130 | `results_evidence/router.py:469` | `.../case_results_service.py` | `failure_clusters` | — |
| 门禁评估 | `TestRunDetailPage.tsx` / `pages/GateEvalHistoryPage.tsx` | 同上 / `/gates/evaluations` | API-146 / API-144 | `quality_gates/router.py:275,227` | `quality_gates/evaluation_service.py:212` | `gate_evaluations`、`check_runs` | — |

要点：

- **调度 Owner 唯一**：`run_orchestration/service.py:746 reclaim_stale_active_runs` 负责回收「进程挂掉后卡住的活跃 run」。**同一业务步骤只允许一个调度 Owner**——本地不要同时起两个 uvicorn 指向同一个库。
- **`TARGET_ENV` 是基地址**：执行器用 `urljoin` 语义把用例 `path` 拼到它后面（`run_orchestration/http_runner.py:28-51 _normalize_base_url`，`executor.py:335` 读 `params_dict["TARGET_ENV"]`）。填成完整 URL 会导致路径翻倍 → 404。
- **`missing_target_env`**：`TARGET_ENV` 为空时 run 直接 `FAILED`，且**不写任何 CaseResult/StepRun**（写结果之前就失败了）。
- **`STOPPING` ≠ `CANCELLED`**：`RUNNING` 中取消只能先到 `STOPPING`，收尾后才是 `CANCELLED`；已经是终态的 run 取消会被 `HT-STATE-001` 拒。
- **SSE 只推展示进度**：API-210 的事件里没有「改状态」的载荷；权威状态永远来自 API-061。

---

## §3 横切原理：三条最容易被误解的链路

### 3.1 幂等键为什么必须是 UUID

前端 `newIdempotencyKey()` 生成规范 UUID。手工用 curl 调试时也必须给规范 UUID——后端 `require_idempotency_key`（`identity_tenancy/service.py`）会做格式校验，非法格式直接 `validation`。

调试模板：

```bash
KEY=$(uuidgen | tr 'A-Z' 'a-z')
curl -s -X POST http://127.0.0.1:8000/api/v1/test-runs \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $KEY" \
  -b cookies.txt -d @body.json | jq
```

**重放同一条命令**：原样再发一次（同 KEY、同 body）→ 应拿回同一个资源 ID。这就是「重启不重复副作用」的可观测证据，也是 `test_api_062_idempotent_start` 断言的东西。

### 3.2 四眼（Four-Eyes）到底拦在哪

```
approval_policy/service.py:1088  _caller_can_decide(caller_id, approval)
        → caller_id == approver_id or caller_id == escalate_to
approval_policy/service.py:1152  if caller_id == approval.initiator_id:
approval_policy/service.py:1166      raise ValueError("four_eyes")
```

同时，**候选审批人列表本身就排除发起人**（`approval_policy/service.py:834 "four_eyes_self": caller_id == approval.initiator_id`、`:885 _can_view_approval`），所以「换个页面点批准」不可能绕开。

前端也做了呈现（按钮置灰 + 「发起人本人不可批准」），但那是提示——**服务端强制**才是边界。绕过前端直接打 API-112，会得到 `403 HT-IAM-002`。

### 3.3 `param_hash`：审批期间目标参数被改怎么办

审批单创建时对目标载荷算 `param_hash`（`approval_policy/service.py:79 compute_param_hash`）。待审期间目标参数若被修改，哈希对不上：

- 卡片顶部出现红色「审批已失效 — 参数已被修改」，批准/拒绝都不可用。
- 正确出路是 **API-113 修改后重新提交**（`approval_policy/service.py:1515 resubmit_approval_request`）：作废原请求、新建一条 `PENDING`。
- **禁止**在原审批上「继续批准」——那等于批准了一个已经不存在的参数集。

---

## §4 对应测试用例：每个 UI 步骤都有锚点

### 4.1 先认识共享夹具（`backend/tests/`）

理解测试的地基是这三个 fixture + 一个 helper：

| 名称 | 位置 | 作用 |
|---|---|---|
| `_truncate_tables` | `tests/conftest.py:128`（**autouse**） | 每个用例前按硬编码表清单 TRUNCATE；`HUNTAI_LIVE=="1"` 时**自动跳过**（保护真实库）。会话结束 `pytest_sessionfinish`（`conftest.py:93`）会重跑 `seed_local_identity.py`，避免本地登录被清空 |
| `seeded_identity` | `tests/conftest.py:198` | 建 1 组织 / 1 用户（`idp_subject="test-subject-001"`）/ 1 项目 / 角色 `owner`；返回 `{org_id, user_id, project_id, idp_subject}` |
| `client` | `tests/conftest.py:271` | `create_app()` + `ASGITransport`，`base_url="https://test"` |
| `login_as` | `tests/helpers.py:10` | patch 掉 `exchange_oidc_code` / `verify_id_token`，然后驱动 start→callback 建会话 |
| `_seed_admin_peer` | **`tests/test_api_120_action_previews.py:59`** | 建第二个用户（默认 `idp_subject="admin-peer-120"`）+ 项目 `admin` 成员。**所有四眼测试的前提** |

> `_seed_admin_peer` 不在 `conftest.py` 里，而在 `test_api_120_action_previews.py`，被 `test_api_024_025_040_audit_siem.py` 等文件 import 复用。找它别翻 conftest。

`test_run_helpers.py` 是**辅助函数不是测试**：`activate_platform_executor_env:16`、`create_active_script_case:63`、`activate_external_ci_env:109`、`create_active_referenced_case:173`。它们把「造一个 ACTIVE 环境 / ACTIVE 用例」的样板代码抽出来，读执行类测试前先读它们。

### 4.2 UI 步骤 → 测试锚点

每条都能单跑（命令见 §4.3）。**断言栏写的是「这条测试在保护什么」**，不是照抄测试名。

#### P11 门禁策略

| UI 步骤 | 测试锚点 | 断言什么 |
|---|---|---|
| 创建策略 | `test_api_140_143_quality_gate_policies.py::test_happy_path_crud_and_idempotency` | 创建 200；同幂等键重放返回同一策略 |
| 切到阻塞模式 | `::test_create_blocking_requires_confirm` / `::test_patch_blocking_requires_confirm` | 缺二次确认被拒 |
| 改策略并发 | `::test_patch_cas_stale` | `expected_version` 过期 → `HT-VER-001` |
| 幂等键复用但 body 变了 | `::test_idempotency_conflict` | `request_hash` 不符 → `HT-IDEM-001` |
| 只读角色 | `::test_tester_viewer_read_only` | tester/viewer 不能写 |
| 列表筛选 | `::test_list_mode_filter` | `mode` 过滤生效 |

#### P07 A1 生成 → 采纳

| UI 步骤 | 测试锚点 | 断言什么 |
|---|---|---|
| 发起生成（openapi） | `test_api_180_182_204_205_211_a1.py::test_happy_openapi_succeeded` | 202 受理 → 最终生成成功 |
| 部分成功 | `::test_ac_024_partial_generation` | 部分 item 失败时 `degraded` / `failed_items` 如实反映 |
| 空 paths | `::test_ac_025_empty_paths_failed` | 空规格判 failed，不假装成功 |
| 幂等重放 | `::test_idempotency_replay_180` | 同键同 body 不重复生成 |
| 必须写 AI 日志 | `::test_invoke_log_after_180` | 生成后存在 `AIInvocationLog` |
| YAML 被拒 | `::test_yaml_openapi_rejected_on_205_and_180` | openapi/postman 的 YAML 原文被拒 |
| kill switch | `::test_kill_switch_blocks_180_not_205` | 总开关拦生成、不拦登记原文 |
| 登记原文不建用例 | `::test_api_205_does_not_create_test_cases` | API-205 只登记，不产生 TestCase |
| 生成进度 SSE | `::test_api_211_sse` | 事件流是进度，不是命令 |
| 解析器（纯函数） | `test_api_030_035_test_cases.py::test_source_parser_invalid_json` | 非法 JSON 原文被拒 |
| 采纳成草稿 | `test_api_030_035_test_cases.py::test_ac_022_generation_does_not_create_case_until_save` | 生成不自动建用例；采纳（API-032）才建 |
| 采纳多余字段 | `::test_ac_023_extra_fields_rejected` | 未登记字段被拒 |
| 只读角色采纳 | `::test_viewer_cannot_create` | viewer 403 |

> **诚实标注**：当前测试里**没有**用 `curl` 数据源的用例（`grep -rln curl backend/tests/` 为空）。UI 教程让你用 `curl` 是为了本地可达性；代码路径由 `source_parser` 的 `_CURL_URL_RE`（`backend/app/modules/test_assets/source_parser.py:136`）覆盖，但没有端到端测试。想补的话，这是很合适的第一个 PR。

#### P05 用例生命周期

| UI 步骤 | 测试锚点 | 断言什么 |
|---|---|---|
| 提审 → 审核 → ACTIVE | `test_api_030_035_test_cases.py::test_ac_026_review_lifecycle` | 未提审就审核 → 409 `HT-STATE-001`；提审 200；通过后 `lifecycle_status == "ACTIVE"` |
| 非审核角色 | `::test_tester_cannot_review` | tester 不能审 |
| 跨租户 | `::test_cross_org_not_found` | 返回 404 而非 403（不泄露存在性） |

#### P15 环境注册 → P10 审批

| UI 步骤 | 测试锚点 | 断言什么 |
|---|---|---|
| 注册环境 → 待审批 | `test_api_100_106_env_registry.py::test_api_102_register_pending_approval_with_approval_row` | 状态 `PENDING_APPROVAL`（≠ `ACTIVE`）；返回 `approval_request_id`；恰好 1 条 `action_type=="env_register"` 的 `ApprovalRequest`，状态 `PENDING` |
| 非 owner/admin 注册 | `::test_api_102_tester_register_forbidden` | tester 403 |
| 状态非 ACTIVE 时被策略拒 | `::test_api_102_forbidden_status_active_policy_deny` | 策略 DENY 路径 |
| 校验用 preview 非法 | `::test_api_102_invalid_preview_policy_deny` | 非法 preview → 拒 |
| 不在列表里泄露凭证 | `::test_api_100_list_after_register_no_credential_ref` | 列表不含 `credential_ref` |
| job contracts | `::test_api_104_070_job_contracts_and_unknown_job` | 契约与未知 job 处理 |
| **批准后激活** | `::test_api_112_approve_env_register_activates_environment` | 换 `admin-peer-120` 批准 → 审批 `EXECUTED`；环境转 `ACTIVE` |
| **四眼拦截** | `test_api_110_113_approval_queue.py::test_api_112_initiator_approve_four_eyes` | 发起人批准 → `403 HT-IAM-002`；DB 行仍是 `PENDING` |
| 九要素卡片 | `::test_api_110_111_after_preview_pending_with_nine_card_keys` | 待审详情含九要素键 |
| 参数被改后失效 | `::test_api_112_param_hash_mismatch_invalidates` | `param_hash` 不符 → 不可决定 |
| 版本冲突 | `::test_api_112_expected_version_mismatch` | CAS 失败 |
| 驳回后重提 | `::test_api_113_resubmit_from_rejected_creates_new_pending` | 作废原单、新建 `PENDING` |
| 待审时重提 | `::test_api_113_resubmit_from_pending_withdraws_origin` | 原单撤回 |
| 审批过期 | `::test_api_110_lazy_expire_pending` | 惰性过期 |
| 只读角色不能决定 | `::test_api_112_viewer_cannot_decide` | viewer 403 |
| 带理由驳回 | `::test_api_112_peer_reject_with_reason` | 驳回需理由 |

> **注意文件归属**：「批准后激活」在 `test_api_100_106_env_registry.py:242`，「四眼拦截」在 `test_api_110_113_approval_queue.py:149`——两条容易记混。

#### P08 发起执行 → P09 看结果

| UI 步骤 | 测试锚点 | 断言什么 |
|---|---|---|
| 发起（happy） | `test_api_060_063_test_runs.py::test_api_062_happy_start_pending` | 202 受理，初始 `PENDING` |
| 幂等重放 | `::test_api_062_idempotent_start` | 同键同 body 返回同一 run |
| 环境非 ACTIVE | `::test_api_062_env_not_active` | 拒绝 |
| 只读角色 | `::test_api_062_viewer_forbidden` | viewer 403 |
| 项目级环境错配 | `::test_api_062_project_scoped_env_mismatch_not_found` | 404（不泄露） |
| Agent × external_ci | `::test_api_062_agent_external_ci_validation` | 一期不支持，明确拒绝 |
| 受理 → 校验中 | `test_api_064_066_069_071_080_210_test_runs.py::test_ac_037_accept_pending_then_validating` | 状态机推进 |
| 受理单不是终态 | `::test_ac_038_receipt_not_terminal` | 202 的 receipt 不代表完成 |
| 未解析变量 | `::test_ac_041_unresolved_variable_failed` | 变量未解析 → `FAILED`（不静默通过） |
| 结果表有数据 | `::test_api_064_after_script_run` | 执行后有 CaseResult |
| 只列 ACTIVE 用例 | `::test_api_069_only_active_selectable` | 选项接口只给可执行的 |
| 不重复执行 | `::test_idempotent_start_no_double_execute` | 幂等键防止跑两次 |
| 取消 RUNNING | `::test_ac_040_cancel_running_is_stopping_not_cancelled` | 先 `STOPPING`，后 `CANCELLED` |
| 取消终态 | `test_api_060_063_test_runs.py::test_api_063_cancel_terminal_state` | 终态取消被拒 |
| SSE 非命令通道 | `test_api_064_066_069_071_080_210_test_runs.py::test_api_210_sse_is_not_command_channel` | 事件不含改状态指令 |
| 卡死回收 | `test_api_060_063_test_runs.py::test_reclaim_stale_active_runs` | 陈旧活跃 run 被回收 |
| 等待时长统计 | `::test_api_060_include_waiting_dwell_seconds` | 等待态 dwell 可见（不可隐藏） |
| API Token 执行 | `test_api_064_066_069_071_080_210_test_runs.py::test_api_080_execute_token_happy_path` | `execute` scope 可发起 |

#### 门禁评估与横切

| 关注点 | 测试锚点 | 断言什么 |
|---|---|---|
| 失败 run 产 FAIL 评估 | `test_api_144_146_gate_evaluations.py::test_ac_058_failed_run_creates_fail_evaluation_and_check_run` | 评估与 check run 一并落 |
| report_only 不阻断 | `::test_report_only_fail_records_fail_but_does_not_block` | 记 `fail` 但不拦 |
| Agent 结果不进门禁 | `::test_agent_run_terminal_has_unevaluated_reason_agent_source` | `unevaluated_reason` 标注 agent 来源 |
| 取消 / 无策略跳过 | `::test_ac_061_cancelled_and_no_policy_skip_evaluation` | 明确 skip 而非假装通过 |
| 运行中无终态评估 | `::test_api_146_running_run_xor_not_terminal` | 运行中与终态互斥 |
| 改策略不改历史 | `::test_ac_062_patch_policy_does_not_rewrite_historical_evaluation` | append-only |
| 豁免需审批 | `::test_ac_060_gate_waiver_requires_confirm_and_approval` | `gate_waiver` 走 HITL |
| 副作用等级冻结 | `test_policy_gate.py::test_resolve_side_effect_level_frozen_actions` | 冻结表与代码一致（`env_register` → L3） |
| 门禁判定表 | `test_policy_gate.py::test_evaluate_policy_gate_table` | 表驱动：`env_register` → `REQUIRE_APPROVAL`；+reauth → `REQUIRE_REAUTH`；未知动作 → `DENY("undeclared")` |
| 再认证端点 | `test_api_004_reauth.py::test_api_004_reauth_returns_authorization_url` | API-004 返回授权 URL |

### 4.3 怎么单跑

在 `backend/` 目录下：

```bash
# 单条用例（推荐：改哪就读哪、跑哪）
uv run pytest "tests/test_api_110_113_approval_queue.py::test_api_112_initiator_approve_four_eyes" -q

# 单个文件
uv run pytest tests/test_api_100_106_env_registry.py -q

# 纯函数单测（最快，无需数据库）
uv run pytest tests/test_policy_gate.py -q

# 合入前的完整套件
uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest
```

> **注意**：pytest 的 `_truncate_tables` 是 autouse 的，会**清空本地库**。会话结束会自动重跑 `seed_local_identity.py`（见 `conftest.py:93 pytest_sessionfinish`），两个合成账号能再登录；你在 UI 教程里建的策略 / 用例 / 环境不会回来。要回到干净种子态，用 `uv run python scripts/reset_local_data.py --yes`。`HUNTAI_LIVE=1` 会跳过 TRUNCATE——**只在你确定目标是真实库时才这么设**。

前端侧对应的组件测试在同名 `.test.tsx`：`pages/EnvironmentPage.test.tsx`、`pages/ApprovalCenterPage.test.tsx`、`pages/ExecutionLaunchPage.test.tsx`、`pages/TestRunDetailPage.test.tsx`、`pages/TestCaseListPage.test.tsx`、`pages/QualityGatePolicyPage.test.tsx`、`pages/GenerationReviewPage.test.tsx`。在 `frontend/` 下 `npm run test`。

---

## §5 自己验证与调试

### 5.1 用 `trace_id` 把一次请求从头串到尾

- 中间件 `backend/app/core/middleware.py:15` 取请求头 `x-trace-id`，没有就 `uuid4()`；响应回写 `X-Trace-Id`（`middleware.py:18`）。
- 日志与错误信封都带 `trace_id`（`app/core/logging.py:40 get_trace_id`）。

排查顺序：

1. 浏览器 Network 里找到失败请求，读响应 `X-Trace-Id`（失败响应体里的 `error.trace_id` 是同一个）。
2. 后端终端 grep 这个 id → 拿到请求路径、耗时、日志。
3. 响应里的 `error.code` → 对照 §1.5 的映射表定位到 service 短码 → 在该模块 `service.py` grep 短码字符串。

**手工复现时建议自己带 `x-trace-id`**，这样一次实验的所有请求可以串起来看。

### 5.2 修 bug 先写复现测试

仓库规矩（`AGENTS.md` §6）：「修 bug 先写复现测试」。流程：

1. 在对应 `backend/tests/test_api_*.py` 里加一条**当前会失败**的用例，断言正确行为。
2. 跑它，确认失败原因就是你要修的那个。
3. 改 service / router。
4. 再跑：该用例转绿，且同文件其它用例不回归。
5. 每个 service/domain 新函数至少 1 条正例；含分支或外部调用再加 1 条异常路径。每个 API 端点至少 1 条 httpx happy-path。

### 5.3 合入前的验证命令（不可跳过）

后端（在 `backend/`）：

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest
```

前端（在 `frontend/`）：

```bash
npm run lint && npx tsc --noEmit && npm run build && npm run test
```

四条命令**全部零失败**才允许合入；禁止 `git commit --no-verify`。

### 5.4 切片进度必须回写

若你的改动属于某个 `S-M*` 切片：提交前回写 `docs/10_ai_context/ai_context.md` 的「状态」列（取值只有 `未做` / `部分完成` / `完成`）与 `docs/10_ai_context/context/mN.md` 的对应要点。**未回写视为切片未完成**。部分完成必须写清残留与 M0 边界，禁止把占位实现标成无残留的完成。

（本文档本身是 Stage 0 的教程，不属于 `S-M*` 切片，故不涉及回写。）

### 5.5 读代码时的三条硬边界（照抄自 `AGENTS.md` §7）

- 不要在前端推演状态机、本地计算门禁/配额/聚类/成本、本地生成 `param_hash` 或幂等键。
- 不要让 AI 绕过 `AIInvocationLog`，也不要让业务模块直连模型厂商——A1–A8 只经 `llm_factory`。
- 不要把 Agent Mode 结果写进门禁或发布证据；不要对 `execution_result=unknown` 盲重试或当成功放行。

---

## 附录：代码入口速查（文件 · 方法）

想从「模块」反向找「代码在哪」，用这张表。

| 模块 | router（HTTP 边界） | service（业务裁决） | 表定义 |
|---|---|---|---|
| 身份 / 租户 / 会话 | `identity_tenancy/router.py` | `identity_tenancy/service.py` | `identity_tenancy/models.py` |
| 用例 / 计划 | `test_assets/router.py` | `test_assets/service.py`、`test_assets/source_parser.py`（原文解析纯函数） | `test_assets/models.py` |
| A1 / 模型路由 / 成本 / Copilot | `ai_governance/router.py`、`ai_governance/copilot_router.py` | `ai_governance/a1_service.py`、`service.py`、`llm_factory.py`、`copilot_service.py` | `ai_governance/models.py` |
| 执行环境 / Job 契约 | `execution_registry/router.py` | `execution_registry/service.py` | `execution_registry/models.py` |
| 审批 / Policy Gate | `approval_policy/router.py` | `approval_policy/service.py`、`policy_gate.py` | `approval_policy/models.py` |
| TestRun 编排 | `run_orchestration/router.py` | `run_orchestration/service.py`、`executor.py`、`http_runner.py` | `run_orchestration/models.py` |
| 结果 / 证据 / 审计 | `results_evidence/router.py` | `results_evidence/case_results_service.py`、`service.py` | `results_evidence/models.py` |
| 质量门禁 | `quality_gates/router.py` | `quality_gates/service.py`、`evaluation_service.py` | `quality_gates/models.py` |
| 集成 / 连接器 / Token | `integration_hub/router.py` | `integration_hub/service.py` | `integration_hub/models.py` |
| 发布编排 | `release_orchestration/router.py` | `release_orchestration/service.py` | `release_orchestration/models.py` |
| 配额 | `quota_governance/router.py` | `quota_governance/service.py` | `quota_governance/models.py` |
| 跨模块基础设施 | `app/core/middleware.py`、`app/core/errors.py`、`app/core/logging.py`、`app/api/ops.py`（`/healthz` `/readyz`） | `app/modules/*/repository.py`（含 `hash_request_body`） | 每模块私有 schema |

**前端入口**：

| 关注点 | 文件 |
|---|---|
| 路由表（BrowserRouter + `<Routes>`，无 loader/action） | `frontend/src/App.tsx:53` 起 |
| HTTP 客户端（Cookie 携带、幂等键、错误拦截） | `frontend/src/api/client.ts` |
| `API-NNN` ↔ 路径映射（`PAGE_APIS` P01–P25） | `frontend/src/api/catalog.ts` |
| 会话门 | `frontend/src/components/layout/SessionGate.tsx` |
| 探活（无会话） | `GET /healthz`、`GET /readyz`（`backend/app/api/ops.py`） |

**模块化单体的约定**：每个 `app/modules/<module>/` 自成一个**私有 PostgreSQL schema**，禁止跨模块共享仓储或 ORM 实体。「共享数据库 ≠ 共享仓储」——跨模块只能走对方暴露的 query/command 函数，不能 import 对方的 repository。

**本地 mock 集成（`feat/local-integration-mocks`）**：loopback 进程 `backend/scripts/mock_integrations.py`（默认 `127.0.0.1:8091`）模拟 Jira / GitHub / Jenkins / Release 的 HTTP 前缀；`seed_local_identity.py` 会种四条 Connector，`action_contract.base_url` 指向该地址。产品出站规则：**`base_url` 为 loopback mock 时经 httpx 打到 mock**（如 `jira_write_stub.py` / `check_run_stub.py` / `release_orchestration/service.py` 内的 loopback 分支）；**`base_url` 缺失或非 loopback 时仍走进程内 stub**（fail-close，HTTP 错误走既有 failed/审计路径，不把 mock 当生产）。入站 webhook 可用 mock `POST /dev/emit-webhook` 代签 HMAC。回归测试：`tests/test_jira_write_loopback_mock.py`、`tests/test_check_run_release_loopback_mock.py`、`tests/test_mock_integrations.py`。UI 走查见 [`user-ui-guide.md`](./user-ui-guide.md) §7；启动见 [`local-testing-guide.md`](./local-testing-guide.md) §3 步骤 5 与 [`tutorial/integration-hub.html`](./tutorial/integration-hub.html)。

---

## 附：本文与其它文档的关系

| 文档 | 讲什么 |
|---|---|
| [`local-testing-guide.md`](./local-testing-guide.md) | 环境准备与启动 |
| [`user-ui-guide.md`](./user-ui-guide.md) | 普通用户 UI 全流程（本文的「现象来源」） |
| **本文** | UI → 模块 → 原理 → 测试（程序员的翻译层） |
| [`tutorial/`](./tutorial/index.html) | 按后端模块分篇的代码教程（更细的模块内讲解） |
| `docs/06_architecture_design/architecture.md` | 控制面 / Worker 拓扑（本文 §1 的上游） |
| `docs/07_backend_design/api_spec.md` | API 契约与完整错误码表 |
| `docs/07_backend_design/data_model.md` | 逻辑表与分级 |
| `docs/00_setup/project_rules.md` | 命名 / Git / 验证命令 / 红线细则 |

**下一步**：挑一个 UI 动作，按 §0 的三栏法自己走一遍——找到页面 → 找到 router 函数 → 找到 service 判定 → 跑一遍对应测试。走通一次，这套代码你就有了地图。
