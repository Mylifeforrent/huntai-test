# 本地测试环境使用指南（S-M3 后 · 手工功能验证）

> 适用范围：本地（本机）运行 HuntAI Test，用预置的演示账号对系统各功能做手工验证。
> 教程式模块讲解见同目录 `tutorial/`（浏览器打开 `tutorial/index.html`）。
> 本文由环境准备脚本生成于 2026-09-06；Cookie 有效期 30 天。

---

## 1. 环境现状（已为你启动）

| 组件 | 地址 | 说明 |
| --- | --- | --- |
| 后端 API | http://127.0.0.1:8000 | 当前 main 代码（含 M1–M3 全部功能），日志 `/tmp/huntai-backend.log` |
| 前端 Vite | http://127.0.0.1:5173 | 若被占用会顺延 5174（本次两个端口都在跑）；日志 `/tmp/huntai-frontend.log` |
| 数据库 | `postgresql+asyncpg://macbookair@127.0.0.1:5432/huntai_test` | 与 pytest 共用同一个库 |
| 登录方式 | **Cookie 注入**（无真实 IdP） | `huntai_session=<uuid>`，值见 §2 |

启动/停止命令（重启用）：

```bash
# 后端
cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
# 前端
cd frontend && npm run dev
```

---

## 2. 演示账号（Cookie 即登录态）

会话模型没有签名，Cookie 值就是 `auth_sessions.id` 的 UUID。**Cookie 不区分端口**，设一次对 5173/5174 都生效。

| 角色 | 账号（idp_subject） | Cookie 值（huntai_session） | 能做什么 |
| --- | --- | --- | --- |
| owner | demo-owner | `cbbacb6e-9c02-433d-8f7a-8fcb64ac91f9` | 全部功能 + 审批 + 两个项目 |
| admin | demo-admin | `e268226b-fab8-4ed2-86d8-1b617afb19ad` | 同 owner（审批四眼：批准人 ≠ 发起人，用 owner 发起、admin 批准） |
| tester | demo-tester | `338b0fb1-5dfe-495d-a70c-f794cf0dd3ef` | 用例/执行/压测/Release 发起；只能发起审批不能批准 |
| viewer | demo-viewer | `490b849d-c326-4d38-aad5-91c9ff0a7bd8` | 只读；写操作应得到 403 HT-IAM-001 |

> 注：重跑种子脚本会刷新所有 Cookie（旧的立即作废），以脚本末尾打印的值为准。

**注入方法**：浏览器打开 `http://127.0.0.1:5173` → F12 → Application（应用）→ Cookies → `http://127.0.0.1` → 添加一条：名称 `huntai_session`，值上表对应 UUID → 刷新页面即已登录。切换账号 = 改这条 Cookie 的值。

> 重新生成 Cookie：`cd backend && uv run python /tmp/seed_huntai.py`（幂等，末尾打印新 Cookie；完整脚本见附录 A）。

---

## 3. 预置数据（种子脚本写入）

| 数据 | 内容 |
| --- | --- |
| 组织 | HuntAI 演示租户（`huntai-demo`） |
| 项目 | A=电商核心（四角色全员）；B=支付网关（仅 owner/admin）——用于验证跨项目越权 |
| 用例（ACTIVE） | 「GET 宠物列表」（script/api，断言 200）；「下单接口压测场景」（performance） |
| 执行环境 | 「本地平台执行器」（ACTIVE，项目级，可发起执行） |
| 门禁策略 | 项目 A：blocking 模式，阈值 95% / 500ms / 1% |
| 连接器 | 演示 Jira、演示 Release（webhook secret 引用 `env:GITHUB_WEBHOOK_SECRET`） |
| 配额 | token 1000 / 执行 slot 5 / 压测并发 2 |
| ModelRoute | general → stub |

---

## 4. 功能测试走查清单

> 前置：已注入 owner Cookie。每条注明「入口页面 → 操作 → 预期」。

### 4.1 工作台与项目（P01/P02）
- 打开 `http://127.0.0.1:5173` → 工作台聚合、组织配额余量可见。
- 切换 admin Cookie 也能看到「支付网关」；切 tester/viewer 只能看到「电商核心」（B 项目不可见）。

### 4.2 用例库（P05/P13）
- 用例库出现两条 ACTIVE 用例；详情看版本快照（API-037/038）。
- 新建草稿 → 提交评审 → 换 **admin** 账号在 P10 批准 → 变 ACTIVE（FR-05 两步式）。

### 4.3 执行与 TestRun（P08/P09）
- P08 选「本地平台执行器」+「GET 宠物列表」发起（execution_source=script）。
- 目标环境默认不通（127.0.0.1:9 之类），run 会 **FAILED**——这本身就是有效结果：去 P09 看终态、StepRun、失败聚类（A2 会跑规则聚类）。
- 想要 SUCCEEDED：本机起一个返回 200 的服务（如 `python3 -m http.server 18999`），发起时把参数 `TARGET_ENV` 填 `http://127.0.0.1:18999`。
- 取消：RUNNING 中点取消 → 状态先 STOPPING（受理 ≠ 已取消）→ worker 停止后 CANCELLED。

### 4.4 Agent 轨迹（P14）
- P08 用 execution_source=agent + agent 用例发起（需在参数里声明 `agent_manifest`：`{"allowed_tools":["request"],"max_steps":5,"total_timeout_seconds":30}`，缺失会被 VALIDATING 拒绝）。
- 轨迹在 P14；白名单外工具 → DENY + policy_denials；连续 3 次 DENY 自动终止（AC-085）。
- 「转脚本草稿」按钮：轨迹 completed 时可一键生成 DRAFT 用例。

### 4.5 性能压测（P16）
- P16 填：场景用例=「下单接口压测场景」、目标 `http://127.0.0.1:18999`、白名单含该前缀、并发 2、时长 30s → 发起。
- **白名单外目标 → 403 HT-POL-002，不产生审批**（AC-051）。
- kill switch：点「Kill switch 关停压测模块」→ 进行中的施压 60s 内 CANCELLED（实测 ~6s）。
- 高危：场景参数加 `"side_effect_level": "L2"` → run 进 WAITING_APPROVAL + 自动生成 perf_high_risk 审批 → admin 批准后继续压。
- 基线：压测完成后可创建基线（同场景唯一活跃）。

### 4.6 门禁（P11/P12）
- 项目 A 策略 blocking；run 终态后 P12 出现 GateEvaluation（pass_rate/p95/error_rate 逐项实测）。
- 压测 run 无指标/报告 partial/CANCELLED → 不建评估行，只给 unevaluated_reason。
- 「仅报告 ⇄ 阻断」切换：P11 改 blocking 需勾选确认；历史评估结论不被改写。

### 4.7 审批中心（P10）与四眼
- 用 owner 发起（jira_write / heal_apply / perf_high_risk / release_push），必须换 **admin** 账号批准（owner 自己看不到批准按钮）。
- 审批卡片九要素 + param_hash；批准后状态 EXECUTED，领域对象随之推进。

### 4.8 Release（P17）
- P17 填 Jira 版本号创建 → DRAFT → 自动推进 PENDING_CONFIRM（Readiness 红黄绿、A5 草稿只读、缺失项显式）。
- 「发起 release_push 审批」→ admin 批准 → SUBMITTED（内部 prepare 创建 item，幂等）。
- READY 由 webhook 观察驱动；本地可用 curl 模拟（HMAC 签名，密钥 `test-github-webhook-secret`，见附录 B）。
- 失败重试（API-153）不会重复创建外部 item（AC-067）；取消后迟到 READY 只追加 divergence。

### 4.9 证据中心（P20）
- 证据检索/详情；「导出证据包」选格式 → 受理 → 完成后下载（API-223 代理）。含 Restricted 证据的导出整单 403。

### 4.10 Copilot（P18）
- 新建会话（可填项目锚点）→ 提问「当前项目最近的 TestRun 情况如何？」→ 返回 A6 四键（answer/citations/tool_calls/refused_policies）。
- 越权测试：在问题里粘贴项目 B 的资源 UUID → `refused_policies` 出现 `cross_project_reference:*` 且绝无该数据（AC-068）。
- kill switch：P23 或 API-199 关停 `copilot` 模块 → 再提问直接 403（AC-069，命令真实失败）。
- 配额：token 花完后提问 → 429 HT-QUOTA-001。

### 4.11 AI 开关与降级（P23）
- 单能力（A1–A8）/模块（copilot/performance…）/全局 四级关停即时生效；恢复必须走 kill_switch_restore 审批。

---

## 5. curl 快速验证（无需浏览器）

```bash
OWNER="Cookie: huntai_session=9eb26c2f-7cae-4688-ab3a-f558703319a6"
ADMIN="Cookie: huntai_session=99d0105e-f955-4a20-bc12-92ee18ec0681"

curl -s http://127.0.0.1:8000/api/v1/me -H "$OWNER" | head -c 300
curl -s http://127.0.0.1:8000/api/v1/test-cases?project_id=<A的id> -H "$OWNER"
curl -s http://127.0.0.1:8000/api/v1/copilot-sessions -H "$OWNER"
```

## 6. 注意事项 / 常见问题

1. **跑 pytest 会清库**（conftest TRUNCATE 全表）。跑完测试后重新执行 `uv run python /tmp/seed_huntai.py` 即可恢复演示数据与 Cookie（脚本幂等）。
2. 后端是本地卷存制品（`ARTIFACT_ROOT=./artifacts`），无 MinIO；删除 artifacts 目录不影响元数据，但制品内容会 409。
3. 外部系统（Jira/Release）是 stub：连接器存在即可走通流程，无真实 HTTP。
4. Cookie 过期/失效 → 重新跑种子脚本取新 Cookie。
5. 8000/5173 端口被占 → `lsof -i :8000 -sTCP:LISTEN` 找 PID 杀掉后重启。
6. 本文档与种子数据仅用于**本地手工验证**，请勿将演示账号用于任何共享环境。
7. **L4 动作（release_push）要求 15 分钟内 step-up 认证**：本地无真实 IdP，重跑种子脚本即可把 `last_reauth_at` 刷新到当前（详见 §7）。

---

## 7. 自动化冒烟测试脚本（`backend/tests/test_live_smoke.py`）

针对**运行中的本地实例**（http://127.0.0.1:8000）的端到端冒烟套件，7 条用例覆盖各模块核心链路。**默认跳过**（常规 `uv run pytest` 不受影响），需显式开启：

```bash
# 前置：刷新会话（同时满足 L4 的 15 分钟 step-up 窗口；也会同步冒烟脚本的默认 Cookie 说明见下）
cd backend && uv run python /tmp/seed_huntai.py

# 运行冒烟
HUNTAI_LIVE=1 uv run pytest tests/test_live_smoke.py -q
```

### 7.1 用例清单与对应功能

| 用例 | 功能点 | 验证内容 |
| --- | --- | --- |
| test_01_health_and_rbac | 认证/RBAC | 四角色 /me 可读；viewer 创建会话 403 HT-IAM-001 |
| test_02_seeded_assets_visible | 种子资产 | ACTIVE 用例 ×2、ACTIVE 环境、blocking 门禁策略 |
| test_03_run_lifecycle_script_api | 执行+门禁 | 受理≠完成（202 回执）→ SUCCEEDED → blocking 门禁 pass 评估 + Check Run success |
| test_04_perf_whitelist_denied | AC-051 | 压测白名单外 403 HT-POL-002 且不建审批 |
| test_05_copilot_answer_and_cross_project_refusal | AC-068 | A6 四键；跨项目引用 100% 剥离记 refused_policies；messages 持久化 |
| test_06_release_task_full_flow | FR-15 | 圈定→PENDING_CONFIRM（A5/Readiness）→ step-up → release_push 审批 → SUBMITTED+item → HMAC webhook → READY |
| test_07_evidence_export_and_proxy_download | AC-096 | 导出受理 202 → 完成后 API-223 代理下载（attachment + JSON 可解析） |

### 7.2 操作步骤

1. 确认后端在 8000 端口运行（当前 main 代码）。
2. `cd backend && uv run python /tmp/seed_huntai.py` —— 刷新演示数据与全部 Cookie（**必须在冒烟前 15 分钟内执行**，否则 test_06 的 L4 动作会返回 HT-AUTH-002）。
3. `HUNTAI_LIVE=1 uv run pytest tests/test_live_smoke.py -q` —— 预期 `7 passed`。
4. 冒烟会在演示库留下：1 个 SUCCEEDED run + 门禁评估、1 个 READY Release 任务、1 个导出包、若干 Copilot 会话——可在前端直接查看这些真实数据。

### 7.3 行为说明

- conftest 已加护栏：`HUNTAI_LIVE=1` 时 pytest 不清空数据库（普通测试仍照常清库）。
- Cookie 值写在脚本顶部 `COOKIES` 常量，可用环境变量 `HUNTAI_OWNER/ADMIN/TESTER/VIEWER` 覆盖。
- test_07 直接向演示库插入一条 EvidenceObject（证据创建本身由后端测试覆盖），用于驱动导出链路。

---

## 附录 A：种子脚本（`/tmp/seed_huntai.py`）

完整脚本约 460 行，核心逻辑（幂等可重复执行）：

1. 建/复用组织 `huntai-demo` → 建 4 个用户（`demo-owner/admin/tester/viewer`，created_by 自指）→ 建 2 个项目（created_by=owner）→ 建成员关系（A 全员四角色；owner/admin 兼 B）。
2. 建 OrgQuota / ModelRoute（general→stub）/ jira+release 连接器 / blocking 门禁策略 / ACTIVE 平台执行器 / 两条 ACTIVE 用例（api + performance）。
3. 为每个用户创建 `AuthSession`（30 天），打印 `huntai_session=<uuid>`。

从 `backend/` 目录执行：

```bash
uv run alembic upgrade head
uv run python /tmp/seed_huntai.py
```

> 若 `/tmp` 已清空，可向维护者索取脚本，或按上面 3 步自行重建；脚本本身不入库（docs/ 不放可执行代码）。

## 附录 B：模拟 Release webhook（READY 观察回传）

```bash
# 前置：release 连接器已建（webhook_secret_ref=env:GITHUB_WEBHOOK_SECRET，
# 本地 .env 中 GITHUB_WEBHOOK_SECRET=test-github-webhook-secret）
BODY='{"release_task_id":"<task_id>","external_item_id":"RI-DEMO","status":"ready"}'
SIG="sha256=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac 'test-github-webhook-secret' -r | cut -d' ' -f1)"
curl -s -X POST "http://127.0.0.1:8000/api/v1/inbound-webhooks/<release_connector_id>" \
  -H "content-type: application/json" -H "x-hub-signature-256: $SIG" \
  -H "x-github-delivery: demo-$(date +%s)" -H "x-github-event: release_item_ready" \
  -d "$BODY"
# SUBMITTED 的任务将迁到 READY；CANCELLED 的任务只追加 divergence
```
