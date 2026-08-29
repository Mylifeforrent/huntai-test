# API、工作流与评审边界设计

> **Status: Draft**
> **日期：2026-08-26**
> **阶段：阶段二产出（Agent B）**
> **评审属性：候选架构与冲突推荐，不构成批准结论**

## 0. 文档定位、依据与约束

### 0.1 目的

本文收口以下架构语义，供后续 API 契约评审使用：

- API 与前后端职责边界；
- 命令、查询、同步受理与异步任务的语义；
- TestRun、ApprovalRequest、外部 CI、SSE、通知、审计与 Evidence 的联动；
- 上传、Artifact 与导出访问的候选方案；
- LangGraph 与 MCP 的采用边界；
- 尚未批准的冲突推荐和开放问题。

本文**不替代 Stage 7 OpenAPI**，不制定真实 endpoint、HTTP 路径、完整请求/响应 schema、分页协议、SSE 帧 schema 或数据库结构。后续 OpenAPI 应消费本文的语义约束，而不是反向改写业务状态机。

### 0.2 事实源优先级

本次评审采用以下优先级：

1. `../03_problem_modeling/problem_model.md`：最高事实源，领域对象、字段语义和状态机以此为准；
2. `../04_interaction_design/interaction_flows.md` 与 `../04_interaction_design/chains/c1_north_star_quality_loop.md` 至 `c4_failure_triage.md`：交互链与异常路径；
3. `frontend_backend_boundary_spec-v1.0.md`：前后端职责、成功判定和错误边界；
4. `../08_prd/prd.md`：需求、验收与分期；
5. `../README.md`：产品原则、路线和安全约束。

出现冲突时，本文给出 **Draft 推荐**，但不将其写成已批准结论。关键上游纪律为：状态机与安全裁决在后端，前端只发起动作并渲染服务端事实；本文只定义语义、不定义协议（`frontend_backend_boundary_spec-v1.0.md:13-23`）。

### 0.3 非目标

本文明确不做：

1. 不设计真实 API endpoint、URL 命名或版本前缀；
2. 不提供完整 OpenAPI schema、错误对象 schema 或 SSE 帧 schema；
3. 不新增领域对象、业务页面或业务状态；
4. 不把 Redis、消息队列、LangGraph 或 SSE 当作业务事实源；
5. 不替代 Jira、GitHub、CI、Release 系统，也不设计双向全量同步；该非目标来自 `../08_prd/prd.md:66-73`；
6. 不把普通上传、普通导入、普通后台任务或普通确定性 TestRun 默认升级为 HITL；
7. 不把任何 Draft/TBD 推荐表述为批准项。

---

## 1. API 与前后端边界

### 1.1 后端权威边界

后端必须是下列事实和裁决的唯一来源：

- 认证会话、tenant 上下文、RBAC 与资源存在性遮蔽；
- TestRun、ApprovalRequest、ReleaseTask、ExecutionEnvironment、TestCase 的状态迁移；
- Policy Gate 的 `ALLOW / DENY / REQUIRE_APPROVAL / REQUIRE_REAUTH` 裁决；
- 幂等键、`param_hash`、ETag/资源版本比较与行锁消费；
- Job Schema、双层变量、配额、白名单、环境健康、Job 存在性等权威校验；
- 外部系统访问、AI 调用、报告归一化、证据校验、通知投递；
- 任务完成、部分成功、失败、取消和超时的最终判定。

依据：前端不得推演状态、不得把本地权限当安全边界、不得本地生成 `param_hash` 或幂等键，也不得直连外部系统（`frontend_backend_boundary_spec-v1.0.md:191-198`）；后端专属逻辑清单见 `frontend_backend_boundary_spec-v1.0.md:202-223`。

### 1.2 前端职责

前端只负责：

- 展示服务端状态、权限和可操作动作；
- 本地表单必填、格式、类型校验与联动置灰，但不把本地通过视为服务端通过；
- 提交命令，展示“已受理 / 提交中 / 结果未决”；
- 订阅 SSE 并展示进度；断线或事件缺口后通过 GET 对账；
- 将筛选、排序、分页保持在 URL，将未提交草稿保持在本地；
- 展示结构化错误、部分成功、降级、滞留和重试入口；
- 仅在服务端返回允许动作时展示相应 CTA，仍不得依赖 CTA 隐藏实现授权。

前端即时反馈不是业务成功；网络中断时不得自行推进或回滚状态（`frontend_backend_boundary_spec-v1.0.md:273-294`）。

### 1.3 API 资源边界与非目标

API 面向既有领域对象与用例，不引入“万能工作流对象”替代领域模型。对于 TestRun、ApprovalRequest、ReleaseTask、ExecutionEnvironment 等已有生命周期，应直接查询其领域状态；对于 AI 生成、Excel 导入、报告解析和导出等后台处理，可在 Stage 7 设计“操作回执 / 任务句柄”语义，但当前不新增领域对象，也不冻结其 schema。

**Draft 推荐 A-01**：采用“领域资源为事实源 + 异步操作回执为传输协调”的模式，不上升为事件溯源或完整 CQRS。是否需要持久化通用异步任务记录为 **TBD**；如需新增领域对象，必须先回到 problem_model 变更流程。

---

## 2. 命令与查询原则

### 2.1 查询（Query）

查询必须满足：

1. 只读，不触发外部写、副作用或隐式状态迁移；
2. 每次查询均执行认证、tenant 过滤与 RBAC；
3. 返回服务端当前快照以及可用于并发控制/缓存对账的版本语义；
4. 列表、详情、历史、聚合、审计、Evidence 检索均由后端计算；
5. 缓存可提升性能，但缓存冲突时以后端最新读取为准；
6. 查询失败不得被前端解释为“空数据”，尤其是网络失败、权限失败与真实空集必须可区分。

### 2.2 命令（Command）

命令表达“请求改变状态或产生副作用”，必须满足：

1. 服务端重新校验认证、tenant、RBAC、对象当前态和业务前置条件；
2. 命令受理与命令完成分离；
3. 可重试命令必须有服务端权威幂等语义；
4. 对已有资源的并发修改使用版本前置条件；
5. L2+ 动作先经 Policy Gate，根据裁决进入拒绝、再认证或 ApprovalRequest；
6. 命令结果必须携带足够的关联语义，供前端随后 GET 对账；
7. 失败和拒绝同样写审计，不以“没有发生副作用”为由省略留痕。

### 2.3 不采用的模式

- 不把“点击按钮成功”视为命令完成；
- 不由前端串联多个写请求来模拟事务状态机；
- 不让 SSE 事件直接执行前端状态迁移；
- 不让模型或 LangGraph决定重试、幂等、权限或 TestRun 状态；产品原则明确“AI 提议、策略裁决、工作流执行”（`../README.md:42-49`）；
- 不因任务是异步的就默认要求人工审批。

---

## 3. 认证、tenant、RBAC 与 404

### 3.1 认证

- Web 用户走企业 SSO 会话；会话失效统一进入重新登录。
- L3+ 且会话超过再认证窗口，或目标资源要求强认证时，Policy Gate 可返回 `REQUIRE_REAUTH`；触发条件来自 `../08_prd/prd.md:107-111`，具体窗口数值仍为 TBD。
- 外部集成使用 ApiToken 时，服务端必须校验 scopes、project 白名单、有效期与吊销状态；触发方式约束见 `../04_interaction_design/chains/c3_execution_kickoff.md:15-24`。
- SSE、上传、下载、webhook 管理查询等同样属于受保护 API，不能因为是流式或文件通道而绕过认证。

### 3.2 tenant 强制隔离

- tenant 上下文缺失时拒绝，不使用“默认租户”或跨租户回退；
- 所有核心对象读写、审计查询、Evidence、Artifact 授权、异步任务查询均应用 tenant 过滤；
- Tool Router、连接器回调关联与后台 worker 也必须携带并复核 tenant，不能只依赖入口层；
- tenant 过滤是 ORM/中间件与工具层强约束，不是 endpoint 手工约定。最高事实源要求所有核心表带 `tenant_id`，无组织上下文即拒绝（`../03_problem_modeling/problem_model.md:95-104`）。

### 3.3 RBAC

角色统一使用 `owner / admin / tester / viewer`：

- viewer 只读，不可发起执行、审批或 L2+ 动作；
- 发起、审批、环境激活、门禁豁免、管理配置等动作按业务角色进一步收敛；
- 前端置灰仅为 UX；服务端每个命令、每次审批执行前均重新校验；
- ApprovalRequest 候选审批人和实际审批提交均强制四眼规则。

### 3.4 404 遮蔽策略

**Draft 推荐 A-02**：

- 已认证用户访问不存在资源与无权感知的跨 tenant 资源，统一返回“资源不存在”语义，不泄露资源是否存在；
- 角色可见但无动作权限的同 tenant 资源，可返回权限不足语义，以支持正确 UX；
- 未认证仍按认证错误处理，不能伪装为 404；
- 前端不得通过 403/404 差异探测跨 tenant 对象。

跨租户引用返回 404 而非 403 是明确需求（`../08_prd/prd.md:141-158`；`frontend_backend_boundary_spec-v1.0.md:300-306`）。具体 HTTP 映射留给 Stage 7 OpenAPI。

---

## 4. 幂等、ETag 与并发控制

### 4.1 幂等原则

幂等分三层：

1. **受理幂等**：相同业务请求重放，不重复创建领域对象或重复派发工作；
2. **执行幂等**：worker 重启、消息重复投递不重复执行同一副作用；
3. **外部写幂等**：连接器携带稳定幂等标识并记录 `external_request_id`，重试不得重复创建外部对象。

UI 前端不得自行生成业务幂等键；可以保留并重放服务端返回的不可解释回执。Webhook 应优先使用外部稳定事件 ID 结合 tenant/connector 形成去重依据；ApiToken 调用方必须提供可稳定重放的调用标识或由服务端按受理语义生成。具体字段与时效留给 Stage 7。

外部 CI 明确要求幂等触发、平台重启不重复执行 Job（`../08_prd/prd.md:128-129`、`../08_prd/prd.md:141-158`）；外部写还必须具备幂等键、external request id、响应快照与补偿（`../README.md:367-376`）。

### 4.2 重试边界

- 网络结果未决时，前端先 GET 对账，再决定是否重放同一命令；
- 自动重试必须复用同一幂等语义，不能生成“看起来新”的命令；
- 功能回归可在队列内部按策略重试，但不引入新 TestRun 状态；
- 压测和 Agent 任务禁止自动重试（`../04_interaction_design/chains/c3_execution_kickoff.md:275-289`）；
- 已最终记录为 ApprovalRequest 执行失败后，不得自动新建审批或静默重放，须重新发起；
- 参数、目标资源或权限上下文变化后，旧幂等语义和旧审批均不能授权新动作。

### 4.3 ETag / 资源版本

上游明确要求连接器写前使用 ETag/版本防并发覆盖（`../08_prd/prd.md:228-231`；`../03_problem_modeling/problem_model.md:249-253`）。

**Draft 推荐 A-03**：

- 对连接器外部写，必须执行目标版本/ETag 前置比较；不匹配时返回并发冲突，不自动覆盖；
- 对 TestCase 编辑、门禁策略、项目成员、连接器配置等人工可编辑资源，候选采用 ETag 或等价版本前置条件；
- 对 append-only 对象（AuditEvent、EvidenceObject、GateEvaluation）不提供覆盖式更新；
- `param_hash` 解决“审批参数是否被改变”，ETag 解决“资源是否被别人并发改变”，二者不可互相替代；
- ApprovalRequest consume 的行锁解决“同一批准是否被消费两次”，也不可由 ETag 替代。

人工可编辑资源的 ETag 覆盖范围尚未在上游冻结，标记 **TBD**。

---

## 5. 统一错误模型与成功判定

### 5.1 错误类别

Stage 7 应基于统一错误外壳表达以下语义类别，但本文不冻结完整 schema：

| 类别 | 典型语义 | 是否通常可重试 | 前端原则 |
| --- | --- | --- | --- |
| 网络/传输未决 | 超时、断连、网关/服务暂不可用 | 条件可重试 | 先 GET 对账，不假定成功或失败 |
| 未认证/需再认证 | 会话失效、`REQUIRE_REAUTH` | 完成认证后 | 跳 SSO 或再认证流程 |
| 权限不足 | RBAC、四眼违例、Token scope 不足 | 否，除非权限变化 | 无权限态；不得本地绕过 |
| 不存在/不可感知 | 真不存在或跨 tenant 遮蔽 | 否 | 统一“资源不存在” |
| 校验错误 | 字段、Job Schema、变量解析、Job 存在性 | 修正后可重提 | 具体字段/原因可见 |
| 前置状态冲突 | 当前态不允许命令、审批已消费 | 对账后决定 | 刷新服务端状态 |
| 版本/ETag 冲突 | 并发覆盖风险 | 拉取新版本后人工处理 | 不自动覆盖 |
| 幂等冲突 | 同一键参数不一致，或重复受理已有结果 | 不以新参数重试旧键 | 展示已有操作或要求新请求 |
| Policy Gate 拒绝 | `DENY`、未声明 sideEffectLevel、白名单外目标 | 否 | 显示政策原因并留痕 |
| 配额/预算/限流 | AI 预算、执行资源或调用频率超限 | 条件可重试 | 展示额度与恢复条件 |
| 审批失效 | `param_hash` 不一致、撤回、上游取消、TTL 过期 | 新审批可重提 | 红色失效提示，不执行 |
| 外部依赖失败 | Jira/GitHub/CI/Release 调用失败 | 按连接器策略 | 显示外部关联与重试状态 |
| 异步任务失败/部分成功 | 解析失败、AI fallback、部分入库 | 按任务语义 | 不把 partial 当完整成功 |
| 内部错误 | 未分类服务端错误 | 条件可重试 | 关联追踪 ID，避免泄露内部细节 |

最低概念信息应包括稳定错误类别/代码、用户可理解说明、是否可重试、必要的字段明细与关联追踪标识；这只是语义要求，不是完整 schema。

上游三大类边界为网络、权限、业务错误（`frontend_backend_boundary_spec-v1.0.md:298-322`）；上表是在不改变三大类的前提下细化业务子类，标记为 **Draft 推荐 A-04**。

### 5.2 成功判定

| 场景 | 不能视为成功 | 权威成功条件 |
| --- | --- | --- |
| 查询 | 页面渲染出缓存 | 服务端返回当前有权快照；必要时带版本语义 |
| 命令受理 | 按钮完成、收到受理回执 | 仅代表请求被接受；完成以领域状态或任务结果为准 |
| 发起 TestRun | 跳转详情页 | TestRun 已创建并返回可查询身份；执行成功仍须等终态 |
| 执行 | SSE 到达 100% | 服务端 TestRun 进入四个终态之一 |
| 审批 | ApprovalRequest=`APPROVED` | 审批通过；副作用成功另看 `EXECUTED + execution_result=ok` |
| 外部写 | 本地提交成功 | 外部连接器返回可对账引用，并完成服务端落账与审计 |
| 上传 | 字节传输结束 | 完整性、类型/大小、安全校验完成并形成授权引用；后续解析另判 |
| 报告解析 | 已有部分 CaseResult | 任务明确 complete；partial 必须显式标记 |
| AI | 模型返回文本 | schema 与 evidence_refs 校验通过，或明确进入 degraded fallback |
| 导出 | 已受理打包 | 导出 Artifact 已生成且当前用户可授权获取 |
| 取消/终止 | “信号已送达” | TestRun 到 CANCELLED；STOPPING 卡死可最终到 TIMEOUT |
| Release | 推送命令受理 | ReleaseTask 经外部状态回传达到 READY；失败进入可见状态 |

审批、执行、终止、门禁等权威成功条件已有明确边界（`frontend_backend_boundary_spec-v1.0.md:273-294`）。

---

## 6. 同步受理与异步任务矩阵

### 6.1 判定原则

- 可在短事务内完成、无长外部依赖、无需持续进度的操作可同步完成；
- 涉及模型、队列、外部 CI、报告解析、大文件、导出打包、长连接器调用的操作采用“同步受理 + 异步完成”；
- 同步受理必须先完成认证、tenant、RBAC、基本参数、幂等与当前态校验；
- 异步 worker 在真正执行前再次校验任务快照、权限/审批绑定和资源版本；
- 任务进度是观察信息，领域状态是业务事实。

### 6.2 矩阵

| 场景 | API 交互建议 | 权威完成依据 | 进度/对账 | 默认 HITL |
| --- | --- | --- | --- | --- |
| 列表、详情、历史、聚合查询 | 同步查询 | 当前服务端快照 | GET | 否 |
| 小型配置读取与提示性校验 | 同步查询 | 校验结果 | 必要时重新 GET | 否 |
| TestCase 保存/提交评审 | 短命令，可同步完成事务 | TestCase/Version 状态已持久化 | GET | 否 |
| 发起 TestRun | 同步受理，执行异步 | TestRun 终态 | SSE 展示 + GET 对账 | 普通执行否；运行中 L2+ 动作才进入审批 |
| 取消/终止 | 同步受理信号，停止异步 | CANCELLED 或兜底 TIMEOUT | SSE + GET | 否 |
| A1 用例生成 | 同步受理，AI 异步 | 草稿或显式 partial/failed | SSE/轮询 + GET | 否，保存评审是后续人工流程但不是 L2+ 审批 |
| A2 报告聚类/A3/A4 建议 | 系统触发异步 | 结构化结果或 degraded fallback | SSE/轮询 + GET | 生成建议否；应用建议是 L3 审批 |
| 外部 CI Job | 同步受理，触发/等待/采集异步 | TestRun 终态及归一化结果 | 双通道状态采集；SSE + GET | 单次普通触发不逐次审批；环境注册已治理 |
| 超大报告解析 | 异步、分片 | complete 或显式 partial | SSE + GET | 否 |
| Excel 导入 | 上传后异步解析/校验/入库 | 导入结果与失败明细 | SSE/轮询 + GET | 否；导入后的初始状态仍 TBD |
| Excel 导出 | 异步生成文件 | 导出 Artifact 可授权访问 | 轮询/SSE + GET | 否 |
| Evidence 包导出 | 异步打包 | 导出 Artifact 可授权访问 | 轮询/SSE + GET | 否 |
| Artifact 上传 | 字节上传与登记分离；大文件异步校验/处理 | 授权引用与校验结果 | GET/任务进度 | 否 |
| ApprovalRequest 决策 | 决策命令短事务；副作用可异步 | `EXECUTED + execution_result=ok/failed/unknown`；unknown 必须显式对账 | GET/SSE/通知 | 是，仅因对应动作 L2+ |
| Jira/GitHub/Release 外部写 | 审批后异步或短时执行，按连接器能力 | external reference + 审计/Evidence | GET/通知 | 是或系统契约豁免，按冻结表 |
| 通知投递 | 业务事件提交后异步 | 渠道投递结果 | 管理查询/告警 | 否 |

执行类提供 SSE 进度且不要求用户同步等待（`../08_prd/prd.md:280-285`）。Excel 导入被明确建议为异步（`../README.md:111-125`），但 Excel 初始状态仍未冻结（`frontend_backend_boundary_spec-v1.0.md:337-346`）。

### 6.3 普通任务不默认 HITL

**Draft 推荐 A-05**：HITL 的触发条件是 Policy Gate 判定存在 L2+ 副作用，而不是“异步”“耗时”“上传”或“使用 AI”。因此：

- 普通文件上传、Excel 导入/导出、报告解析、AI 草稿生成、普通平台内 Script TestRun 不默认审批；
- 外部 CI 的单次普通触发不逐次审批，风险由 ExecutionEnvironment 注册审批、Job Contract、幂等和参数校验收口；
- Agent/Copilot 中 L2+ 工具动作、Jira 写、自愈应用、高危压测、门禁豁免、环境注册、Release 准备、kill switch 恢复按冻结规则审批；
- 白名单外压测目标与未声明副作用动作直接 DENY，不得通过“申请审批”绕过政策。

普通执行不进入审批链的上游依据见 `../04_interaction_design/chains/c3_execution_kickoff.md:293-303`。

---

## 7. TestRun 10 态与前端映射

### 7.1 权威 10 态

TestRun 状态集合严格采用最高事实源：

`PENDING / VALIDATING / RUNNING / WAITING_EXTERNAL / WAITING_APPROVAL / STOPPING / SUCCEEDED / FAILED / CANCELLED / TIMEOUT`

终态集合为 `SUCCEEDED / FAILED / CANCELLED / TIMEOUT`。完整迁移与等待态/活跃态纪律见 `../03_problem_modeling/problem_model.md:139-186`；README 也声明以该 10 态为唯一事实源（`../README.md:325-339`）。

### 7.2 前端展示映射

| 后端状态 | 前端语义 | 典型展示 | 可用动作原则 | 刷新原则 |
| --- | --- | --- | --- | --- |
| PENDING | 已受理，尚未进入校验 | “排队/已受理” | 可在校验前取消 | SSE 展示，GET 权威 |
| VALIDATING | 服务端校验中 | Job/参数/变量校验 | 不提供独立取消；等待短时收敛 | GET 对账 |
| RUNNING | 正在执行 | 进度、步骤、心跳状态 | 按角色终止；可能进入等待审批/外部等待 | SSE + GET |
| WAITING_EXTERNAL | 等待外部 CI | 外部 Job 队列、滞留时长 | 幂等取消 | SSE + 持久轮询结果 + GET |
| WAITING_APPROVAL | 等待人工审批 | 高亮并跳审批中心、滞留时长 | 人工取消或重新提交审批 | SSE/通知 + GET |
| STOPPING | 停止处理中 | “终止信号已送达，正在停止” | 禁止重复创建新终止动作；允许查看 | SSE + GET |
| SUCCEEDED | 成功终态 | 成功结果与 Evidence | 查看、导出、按权限重跑 | GET |
| FAILED | 失败终态 | 失败原因、partial、分诊入口 | 查看、按规则重跑 | GET |
| CANCELLED | 取消终态 | 操作者/原因、已采集部分结果 | 查看、人工重发 | GET |
| TIMEOUT | 超时终态 | 心跳/停止卡死原因、回收记录 | 查看、人工决定重跑 | GET |

### 7.3 状态纪律

1. PENDING 只做受理与快照冻结；权威校验发生于 VALIDATING；
2. VALIDATING 失败进入 FAILED，不进入执行队列；
3. WAITING_EXTERNAL 与 WAITING_APPROVAL 是等待态，不受心跳僵尸回收；必须持续可见、显示滞留时长、超阈值告警且可人工取消；
4. RUNNING 与 STOPPING 是活跃态；RUNNING 心跳丢失到 TIMEOUT，STOPPING 卡死也到 TIMEOUT；
5. 审批过期后 TestRun **停留 WAITING_APPROVAL**，不自动放行，也不自动迁移到 CANCELLED；拒绝或人工取消才到 CANCELLED；
6. 前端不得由进度百分比、SSE 文本或本地计时推导终态。

### 7.4 冲突推荐

C1/C2/C3 的部分图表或旧行仍出现“审批过期 → CANCELLED”表述，例如 `../04_interaction_design/chains/c3_execution_kickoff.md:150-169`，但其后续正文和回写记录已改为过期停留，最高事实源也明确停留。

**Draft 推荐 A-06**：Stage 7 OpenAPI 与前端实现统一采用 `../03_problem_modeling/problem_model.md:175-186` 的新口径：审批过期不迁移 TestRun；旧图表仅视为历史残留，不作为实现依据。该推荐尚未批准。

---

## 8. SSE：仅展示、GET 对账、事件 ID、重连与降级轮询

### 8.1 定位

SSE 是进度与变化提示通道，不是命令通道、状态机引擎或事实存储。适用场景包括：

- TestRun 执行进度；
- 外部 CI 等待/采集进度；
- 报告解析和聚类生成进度；
- A1 生成进度；
- 导入/导出打包进度；
- 审批、降级和通知的轻量提示。

上游已明确 SSE 用于执行、报告生成与解析进度，但断线重连和轮询是待补契约（`frontend_backend_boundary_spec-v1.0.md:252-265`、`frontend_backend_boundary_spec-v1.0.md:337-346`）。

### 8.2 展示与对账原则

- SSE 事件只携带“发生变化/可展示进度”的语义；最终状态从领域资源 GET 获取；
- 首次进入页面先 GET 快照，再建立订阅；
- 收到状态变化事件后，可合并纯展示进度，但进入关键状态、终态或发现版本跳跃时必须 GET；
- 命令返回结果未决、浏览器从后台恢复、网络恢复、SSE 重连成功后必须 GET；
- SSE 和 GET 冲突时，以 GET 为准；
- SSE 不携带凭证、Restricted 内容或未脱敏 Artifact 正文。

### 8.3 事件 ID

**Draft 推荐 A-07**：

- 每个可恢复事件流提供服务端生成、单调可排序且不可由前端伪造的事件 ID；
- 事件 ID 只用于断线续传和缺口检测，不作为业务对象版本或幂等键；
- 重连时客户端提交最后确认的事件 ID；服务端在保留窗口内补发；
- 若事件 ID 过旧、保留窗口已清理或检测到缺口，服务端明确要求客户端 GET 全量对账，而不是伪造连续事件；
- 事件保留窗口、每租户连接数和每用户订阅上限均为 TBD 配置项。

### 8.4 重连与降级轮询

- 客户端使用指数退避、抖动和上限，避免断网风暴；
- 认证过期时停止自动重连，先完成认证；
- 连续失败达到阈值后进入降级轮询，并显示“实时更新已降级”；
- 轮询频率按状态调整：RUNNING/STOPPING 较频繁，等待态较低频，终态停止自动轮询；具体秒数 TBD；
- 页面不可见时降低频率，恢复可见时立即 GET；
- 轮询恢复稳定或 SSE 可用后可重新建立 SSE，但仍先 GET 对账；
- 不允许因 SSE 断线把 TestRun 标记 FAILED/TIMEOUT，也不允许把 ApprovalRequest 标记 EXPIRED。

### 8.5 安全与容量

SSE endpoint（具体路径由 Stage 7 定义）必须认证、tenant 隔离、授权过滤、限连接数并支持服务端心跳。README 的安全清单明确 SSE 端点必须鉴权（`../README.md:359-364`）。

---

## 9. 外部 CI：webhook + 持久轮询双通道

### 9.1 双通道职责

- **Webhook**：低延迟状态提示；必须 HMAC 验签、tenant/connector/job 归属校验、事件去重和审计；
- **持久轮询**：可靠性兜底；轮询 checkpoint 必须可持久恢复，平台重启后从中断处继续；
- 两通道采用“先到者推动、后到者对账”的原则；任何一方都不能绕过 TestRun 状态机；
- webhook 不可达不应永久阻塞；轮询服务重启也不能重复触发外部 Job。

完整业务链为幂等触发 → 持久轮询 + webhook → 日志分片 → 报告适配器 → 统一 TestRun，见 `../08_prd/prd.md:124-129`；交互时序见 `../04_interaction_design/chains/c3_execution_kickoff.md:171-210`。

### 9.2 并发与乱序

**Draft 推荐 A-08**：

1. 触发外部 Job 与记录其外部引用必须具备原子/可恢复边界；
2. webhook 与轮询都先读取当前 TestRun、外部构建版本和事件去重记录，再尝试合法迁移；
3. 以条件更新/锁保证同一迁移只生效一次；
4. 乱序或重复事件只做对账和审计，不回退状态；
5. 外部构建已开始后，WAITING_EXTERNAL → RUNNING；仅收到“已排队”不得提前进入 RUNNING；
6. 外部 Job 已结束但报告尚未完成归一化时，TestRun 是否继续 RUNNING 以及如何展示“解析中”由现有状态机约束，不新增状态；展示层使用任务进度而非新 TestRun 状态。

### 9.3 取消与滞留

- WAITING_EXTERNAL 排队超时只告警，不自动取消、不自动迁移；
- 用户可发起幂等取消，进入 CANCELLED；已经产生的构建记录继续采集；
- 外部取消无响应时按 STOPPING 活跃态的心跳治理兜底；
- CI 平台本身状态与本平台 TestRun 必须可审计对账。

---

## 10. 报告解析、AI、Excel 与其他异步任务

### 10.1 通用任务纪律

所有异步处理候选均遵守：

- 入口短事务完成身份、tenant、权限、配额、格式、幂等和基础大小校验；
- worker 使用冻结输入引用，不依赖浏览器会话内存；
- 进度可观察，但领域状态不由进度推导；
- 重试按任务类型明示，禁止所有任务使用同一自动重试策略；
- 结果必须是 complete、partial、failed、cancelled 等明确语义之一；本文不新增业务状态枚举，具体任务结果表达留 Stage 7；
- partial 必须列出已完成范围和失败项，禁止静默截断；
- 任务完成后产生通知、AuditEvent、AIInvocationLog 或 EvidenceObject，按场景选择，不要求每种对象都创建。

### 10.2 报告解析

- JUnit/Allure/Playwright/Pytest 等通过确定性适配器解析；
- 超大报告分片流式解析，进度可见；
- 解析超时保留已完成部分并显式失败，不把部分数据包装成完整成功；
- 日志/报告在落库前脱敏；
- 归一化完成后再进入 A2 失败聚类；
- external_ci 和平台原生结果归一化后共用 FailureCluster、Evidence 和门禁，但 `execution_source=agent` 不进门禁。

上游要求超大报告部分入库且显式失败（`../08_prd/prd.md:141-146`），C4 明确报告归一化是确定性管道并要求解析准确率（`../04_interaction_design/chains/c4_failure_triage.md:29-39`）。

### 10.3 AI 任务

- 所有 AI 调用走后端 LLM 工厂与 AIInvocationLog，无旁路；
- 输出先做结构化 schema 校验，再做 evidence_refs 输入证据池校验；
- A1/A2 等按各自契约执行一次受限重试和 fallback；
- AI 降级不得阻断平台执行、报告和门禁；
- AI 生成草稿、归因和建议本身不默认审批；应用建议或执行 L2+ 工具动作才进入 ApprovalRequest；
- AI 任务不得决定 TestRun 的业务重试、幂等、权限或门禁资格。

A2 的失败处理与证据校验见 `../08_prd/prd.md:177-212`；AI 降级总原则见 `../08_prd/prd.md:337-340`。

### 10.4 Excel 导入与导出

- 导入：先上传私有对象存储，后异步解析、格式校验、逐行结果汇总；
- 行级失败必须可下载/查看，批次 partial 不得静默；
- 普通导入不走 HITL；
- 导入 TestCase 的初始状态是 DRAFT 还是 PENDING_REVIEW、是否强制复用两步审阅流仍为 **TBD**，不能由本文件擅自冻结；
- 导出：异步生成、私有保存、短期授权访问；导出内容受 tenant/RBAC 和审计约束；
- 大文件生成不得占用同步 API 请求直到完成。

Excel 初始状态和访问方式均是上游已登记缺口（`frontend_backend_boundary_spec-v1.0.md:337-346`）。

### 10.5 通用任务记录的开放边界

problem_model 未定义通用 AsyncTask 领域对象。**Draft 推荐 A-09**：Stage 7 先定义最小“操作回执 + 查询任务结果”的协议语义，并让业务完成结果回写既有领域对象；是否新增持久通用任务对象必须另行评审，不在本文暗中新增。

---

## 11. ApprovalRequest 全流程

### 11.1 触发与前置

ApprovalRequest 只在 Policy Gate 返回 `REQUIRE_APPROVAL` 时创建。创建前必须满足：

- 动作已声明 sideEffectLevel；
- Preview 参数已冻结并生成服务端 `param_hash`；
- 九要素卡片完整；
- 候选审批人集合排除发起人且非空；
- TTL 与升级对象可解析；
- 对 heal_apply 等需快照的动作，快照前置条件按 fail-close 执行。

统一前置要求见 `../04_interaction_design/chains/c2_approval_chain.md:39-45`。

### 11.2 九要素

卡片必须覆盖：

1. 动作；
2. 目标资源；
3. 前后 diff；
4. 数据来源；
5. 模型与 Skill 版本；
6. 风险等级；
7. 成本估计；
8. 回滚/补偿能力；
9. 参数哈希。

卡片只展示服务端组装数据；前端不得自行补算 `param_hash`。九要素及展示纪律见 `../04_interaction_design/chains/c2_approval_chain.md:72-100`。

### 11.3 六态与动作流程

ApprovalRequest 采用：

`CREATED → PENDING → APPROVED → EXECUTED`，分支为 `REJECTED / EXPIRED`。

语义：

1. `CREATED`：Policy Gate 判定需审批时创建的瞬时态；
2. `PENDING`：进入队列、通知审批人并启动 TTL；
3. `APPROVED`：审批人同意，但尚不代表副作用成功；
4. 执行前重算 `param_hash`、重校验权限/tenant/资源版本；
5. consume 在事务内加行锁，原子创建以 `approval_request_id + bound_hash` 唯一标识的基础设施执行意图与 Outbox；重复 consume 返回同一执行引用，不创建第二个意图，也不提前进入 EXECUTED；
6. execution intent 至少使用 `READY / CLAIMED / DISPATCHING / CONFIRMED_OK / CONFIRMED_FAILED / UNKNOWN / ABANDONED`；Worker 在网络调用前持久化 DISPATCHING，确定响应后确认结果，调用可能已发出但不可判定时进入 UNKNOWN；
7. `EXECUTED`：首次真实调用已发出后才写入，另带 `execution_result=ok/failed/unknown`；unknown 只表示外部效果当前不可判定，不得视为失败重试或成功放行；
8. 拒绝进入 `REJECTED`；到期、撤回、上游取消或参数失效统一进入 `EXPIRED` 并记录原因。

最高事实源见 `../03_problem_modeling/problem_model.md:188-220`。

### 11.4 四眼原则

- `approver_id != initiator_id` 在候选人路由、审批提交、执行前复核三处强制；
- 前端将本人批准按钮置灰只是提示；
- 备审批人同样受四眼约束；
- 修改后重新提交的新请求，以重新提交人为新 initiator，不能沿用原发起人来绕过四眼；
- 四眼违例必须拒绝并写 AuditEvent。

### 11.5 param_hash 与 anti-TOCTOU

- `param_hash` 绑定 Preview 时的完整执行参数和目标语义；
- 执行前重算并比较；
- 参数变化、目标版本变化或权限变化均 fail-close；
- `param_hash` 不等于 ETag，也不等于幂等键；
- 前端不能从可见字段自行复算；
- 审批卡片展示哈希供人工核对，但真正比较在服务端。

README 的安全清单明确参数变化使审批失效且执行前须重校验权限（`../README.md:367-374`）。

### 11.6 TTL、升级与过期

- TTL 属 ApprovalRequest，不与 TestRun 心跳共用；
- 到期先通知 `escalate_to`，仍未处理才 EXPIRED；
- 任意情况下均不自动放行；
- 关联 TestRun 停留 WAITING_APPROVAL，直到重新提交或人工取消；
- TTL 默认值、提前升级时点和升级轮数为 **TBD**，留后续配置项评审。

### 11.7 修改后重新提交

- 生成新的 ApprovalRequest、新的 `param_hash` 和新的 TTL；
- `initiator_id` 是重新提交人；
- 保留 `origin_request_id / original_initiator_id` 归因链；
- 旧请求保持 EXPIRED/原终态，不被“重新打开”；
- 新请求重新执行四眼、权限、资源版本和 Policy Gate 校验。

### 11.8 执行失败与结果不可判定

- `EXECUTED` 表示“已尝试”，不是“成功”；
- 最终失败记录 `execution_result=failed`，写 AuditEvent，并保留连接器错误/Evidence；
- 行锁消费只创建唯一基础设施执行意图，不提前写 EXECUTED；Outbox 重投、Worker 重领和重复 consume 必须复用同一意图；
- READY/CLAIMED 阶段崩溃可重领；DISPATCHING/UNKNOWN 必须先按 external_request_id 或稳定幂等键查询。可确认成功/失败时分别收敛 ok/failed；暂不可判定时记录 `execution_result=unknown` 并持续对账；
- 若提供方既不支持幂等创建也不能按请求标识查询，unknown 必须 fail-close 并转人工接管，禁止自动重发；
- 只有 `execution_result=ok` 可触发目标聚合的成功迁移；failed/unknown 不得自动推进 TestRun、ReleaseTask 或 ExecutionEnvironment，现有状态模型无合法失败边时保持 fail-closed 并等待显式人工命令；
- 连接器内部可在同一次执行尝试中按幂等策略处理短暂错误；一旦记录最终失败，不得静默再次消费同一批准；
- 需要再次执行时重新发起审批；参数或资源变化必定需要新审批；
- heal_apply 快照失败时 fail-close，不写新版本；
- 外部对象不得以自动删除作为默认补偿。

执行失败处置的最高事实源见 `../03_problem_modeling/problem_model.md:201-207`。

### 11.9 动作与级别冲突推荐

problem_model 冻结 `release_push` 为 L4，强调平台仅准备、不执行；C1 有一处将“准备 item”解释为 L3（`../04_interaction_design/chains/c1_north_star_quality_loop.md:260-279`），C2 又称 L4 域动作（`../04_interaction_design/chains/c2_approval_chain.md:201-220`）。

**Draft 推荐 A-10**：采用最高事实源的 `release_push=L4` 标记，同时只允许“准备 release item”的受控审批路径；实际生产发布执行仍为 DENY/不提供。L4 标签不能被解释为平台获得发布执行权。该冲突推荐尚未批准。

---

## 12. ApprovalRequest 与领域状态联动矩阵

| action_ref / 场景 | 发起时领域状态 | 批准且执行成功 | 拒绝 | 过期/失效 | 执行失败 |
| --- | --- | --- | --- | --- | --- |
| agent_tool_action | TestRun RUNNING→WAITING_APPROVAL | ApprovalRequest→EXECUTED(ok)，TestRun→RUNNING | TestRun→CANCELLED | TestRun 停 WAITING_APPROVAL | ApprovalRequest→EXECUTED(failed)；TestRun 不得自动放行，后续处置 TBD/人工取消或重提 |
| perf_high_risk | TestRun RUNNING→WAITING_APPROVAL | TestRun→RUNNING | TestRun→CANCELLED | TestRun 停 WAITING_APPROVAL | 不开始高危阶段；停留等待人工处置 |
| jira_write | TestRun 已终态，不迁移 | Jira 引用回显、Evidence/Audit 落账 | 不创建缺陷 | 不创建缺陷 | TestRun 不变；重新发起审批 |
| heal_apply | TestCase 保持 ACTIVE | 新 TestCaseVersion + current_version_id 更新 | 不应用 | 不应用 | 快照/写入失败 fail-close；原版本保持 |
| env_register | ExecutionEnvironment=PENDING_APPROVAL | →ACTIVE | 保持未激活 | 保持未激活 | 不激活，记录失败后重提 |
| gate_waiver | GateEvaluation 不可变 | 产生可查豁免关联/新评估语义，不改写原记录 | 不豁免 | 不豁免 | 原 GateEvaluation 不变 |
| release_push | ReleaseTask=PENDING_CONFIRM | →SUBMITTED，后续外部回传 READY 或 FAILED_RETRYABLE | 保持 PENDING_CONFIRM，可取消/修改后重提 | 保持 PENDING_CONFIRM | 进入可见失败处置，不重复创建 item |
| kill_switch_restore | 能力处于关停/降级 | 恢复生效并审计 | 保持关停 | 保持关停 | 保持关停，fail-close |

补充约束：

- kill switch **关停**为 L1 即时生效、不走审批；**恢复**为 L3，走 `kill_switch_restore`（`../08_prd/prd.md:345-348`）；
- GateEvaluation 不可变，策略修改和豁免不得重写历史（`../03_problem_modeling/problem_model.md:252-253`）；
- ExecutionEnvironment 降级/停用只阻止新发起，在途 run 不中断（`../03_problem_modeling/problem_model.md:223-235`）。

**TBD**：`agent_tool_action` 或 `perf_high_risk` 获批后执行本身最终失败时，TestRun 在不新增状态的前提下如何从 WAITING_APPROVAL 收敛，需要 Stage 7/后端工作流评审明确；不得默认恢复 RUNNING，也不得误标审批拒绝。

---

## 13. 上传、Artifact 与导出访问候选方案

### 13.1 共同安全要求

无论采用何种访问方式，必须满足：

- 私有存储，禁止公开 bucket；
- 上传/下载前认证、tenant、RBAC 与资源归属校验；
- 文件大小、类型、扩展名与内容嗅探、checksum、安全扫描；
- 对象 key 由服务端生成，客户端不可指定任意路径；
- 元数据与正文均不得泄露跨 tenant 信息；
- 日志/报告落库前脱敏；
- 访问授权短期有效、最小权限、可审计；
- Artifact 保留期和法务要求仍为 TBD；上游登记默认 90 天但待法务确认（`../08_prd/prd.md:216-223`）。

上传端点鉴权、大小/类型校验是明确安全要求（`../README.md:359-370`）。

### 13.2 候选方案

| 方案 | 形态 | 优点 | 代价/风险 | 适用建议 |
| --- | --- | --- | --- | --- |
| A. API 代理上传/下载 | 字节流经过应用后端 | 授权、审计、扫描链路直观 | 大文件占带宽与连接，扩展成本高 | 小型配置、低频敏感文件候选 |
| B. 预签名直传/直下 | 后端授权后客户端直连对象存储 | 适合大报告、视频、Trace、导出 | URL 是短期 bearer；需完成回调、checksum、扫描和对象归属校验 | 大文件主方案候选 |
| C. 混合模式 | 控制面走 API，数据面按大小/敏感度选择代理或预签名 | 平衡安全与吞吐 | 实现与测试面更复杂 | **Draft 推荐** |

### 13.3 Draft 推荐

**Draft 推荐 A-11：混合模式。**

- 浏览器普通上传：先向后端申请受控上传授权；大文件直传私有对象存储，小文件可代理；上传完成后再由后端确认完整性和安全状态；
- worker 生成的截图/视频/Trace/报告：以服务身份直接写私有对象存储，并登记 Artifact 引用；
- 查看 Artifact：普通大文件使用短期预签名只读访问；Restricted/高审计要求文件使用后端代理；
- Excel/Evidence 导出：异步打包为私有 Artifact，完成后发短期访问授权；
- 预签名授权签发与下载行为按能力记录审计；不得把长期 URL 存进 EvidenceObject；Evidence 保存稳定对象引用，访问时再授权；
- 普通上传和导出**不默认 HITL**，只有上传内容将触发 L2+ 外部写时，外部写步骤另行审批。

上游仅确认制品进入 MinIO/S3，访问方式仍未定义（`../08_prd/prd.md:218-223`；`frontend_backend_boundary_spec-v1.0.md:337-346`），因此本节全部仍为 Draft/TBD。

---

## 14. LangGraph 的采用边界

### 14.1 允许用途

LangGraph **只用于 Agent/Copilot 的 interrupt bridge 候选**：

- Agent/Copilot 生成 L2+ 工具调用意图；
- bridge 将意图转换为后端持久化 ApprovalRequest；
- LangGraph interrupt 保存可恢复上下文引用；
- 审批结果由后端状态与事件唤醒 bridge；
- 恢复前再次 GET ApprovalRequest、重校验 `param_hash`、权限和资源版本；
- bridge 只决定 Agent/Copilot 节点是否继续，不决定 ApprovalRequest 或 TestRun 状态。

### 14.2 明确禁止

- 不用 LangGraph 替代 ApprovalRequest；
- 不把 LangGraph checkpoint 当审批事实源；
- 不把内存 interrupt 当持久工作流；
- 不用 LangGraph 承担普通 TestRun、外部 CI 轮询、Excel 导入或报告解析的状态机；
- 不允许 LangGraph 绕过四眼、TTL、行锁、tenant、RBAC、Policy Gate、审计与 Evidence；
- 不因 LangGraph 提供 HITL 组件就改变九要素、`param_hash` 或六态审批模型。

README 曾建议 Copilot Agent 使用 LangGraph 形态（`../README.md:261-280`），但产品原则要求模型不决定业务控制流（`../README.md:42-49`），TestRun 和 ApprovalRequest 又已有持久状态机。因此：

**Draft 推荐 A-12**：LangGraph 限定为 Agent/Copilot interrupt bridge，不作为平台工作流引擎，也不能替代审批。该推荐尚未批准。

---

## 15. MCP 分期结论

上游存在两类表述：

- PRD 明确一期不做 MCP 对外暴露，M4 评估（`../08_prd/prd.md:66-74`）；
- README 描述 MCP 双向生态位，并把其放入 M4 路线（`../README.md:282-294`、`../README.md:343-351`）。

**Draft 推荐 A-13**：

| 里程碑 | 推荐 |
| --- | --- |
| M0 | 不采用 MCP；平台内部使用明确的服务/连接器契约 |
| M1 | 不采用 MCP；优先完成 TestRun、报告、AI 与 Evidence 基线 |
| M2 | 不采用 MCP；Agent 工具继续走内部 Tool Router + Policy Gate |
| M3 | 不采用 MCP；Copilot 最小版只读技能使用内部白名单工具 |
| M4 | 仅将“只读 MCP POC”列为候选；限定试点 tenant、只读工具、严格 schema、RBAC/tenant 双重校验、全审计、kill switch、无外部写 |

M4 POC 通过权限、注入、审计、成本和稳定性评审前，不开放写工具、不作为平台公开承诺，也不把 MCP 当 ApprovalRequest 的替代协议。是否实施 POC 仍为 **TBD**。

---

## 16. 通知、审计与 Evidence

### 16.1 通知

通知由服务端业务事件产生并异步投递，前端只展示。最低覆盖：

- ApprovalRequest 创建、临期、升级、批准、拒绝、过期、执行失败；
- WAITING_EXTERNAL / WAITING_APPROVAL 滞留告警；
- 用例因外部 Job 删除/改名而失效；
- Check Run 回写失败；
- Release/连接器调用失败；
- AI/平台降级、预算超限；
- 导入、导出、报告解析完成或 partial/failed。

渠道配置、主备容灾、失败重试归集成中心；通知产生与投递均在后端（`frontend_backend_boundary_spec-v1.0.md:128-135`）。站内通知中心、角标和列表的具体产品形态仍为 TBD（`frontend_backend_boundary_spec-v1.0.md:337-346`）。

### 16.2 AuditEvent

AuditEvent append-only，至少覆盖：

- 命令受理与状态迁移；
- 校验失败、DENY、越权、四眼违例；
- ApprovalRequest 创建、审批、升级、失效、consume 与执行结果；
- 外部写、重试、补偿、external_request_id；
- webhook 验签失败、重复/乱序事件处置；
- TestRun 僵尸回收和终止；
- Artifact/导出授权签发与敏感访问；
- 人工修正、门禁豁免和 kill switch 操作。

失败操作也必须审计；跨 tenant 审计查询不得泄露。关键字段纪律见 `../04_interaction_design/chains/c2_approval_chain.md:225-238`。

### 16.3 EvidenceObject

EvidenceObject 是 claim 到 source_object 的稳定证据关系，不等于日志附件，也不应保存短期预签名 URL：

- 执行结果、AI 归因、门禁结论、Jira 缺陷、Release 决策均挂稳定 evidence 引用；
- AI 的 evidence_refs 只能引用输入证据池中的 ID；
- Evidence append-only，修订以新记录/关联表达，不覆盖历史；
- Artifact 是证据内容载体之一，Evidence 是“结论为何可信”的关系；
- 访问 Evidence 仍需 tenant/RBAC；
- 关键结论证据覆盖率目标 ≥95%，无据结论率 <2%。

Evidence 一等对象和指标来自 `../README.md:325-339`；C1 的证据流主线见 `../04_interaction_design/chains/c1_north_star_quality_loop.md:285-300`。

---

## 17. 冲突与 Draft 推荐汇总

| 编号 | 冲突/缺口 | Draft 推荐 | 状态 |
| --- | --- | --- | --- |
| A-01 | 是否引入通用工作流/任务对象 | 领域资源为事实源，任务回执只做传输协调；新增对象另走建模变更 | Draft/TBD |
| A-02 | 403 与 404 的资源遮蔽边界 | 跨 tenant/不可感知统一不存在；同 tenant 可见资源的动作权限可表达权限不足 | Draft |
| A-03 | ETag 覆盖范围未冻结 | 外部连接器写强制；人工编辑资源候选采用；append-only 不覆盖 | Draft/TBD |
| A-04 | 三大错误类过粗 | 保留网络/权限/业务三大类，并细化稳定业务子类 | Draft |
| A-05 | 异步任务是否默认 HITL | 否；只由 L2+ Policy Gate 触发 HITL | Draft |
| A-06 | 旧交互图把审批过期指向 CANCELLED | 服从 problem_model：过期停留 WAITING_APPROVAL | Draft，推荐优先 |
| A-07 | SSE 重连协议缺失 | 服务端事件 ID + 缺口 GET 对账 + 降级轮询 | Draft/TBD |
| A-08 | webhook 与轮询竞争/乱序 | 先到者推动、后到者对账，条件更新保证单次迁移 | Draft |
| A-09 | 通用后台任务持久模型缺失 | 先最小操作回执；是否新增对象另评审 | Draft/TBD |
| A-10 | release_push 的 L3/L4 表述冲突 | 按最高事实源标 L4，仅允许准备 item，不提供实际发布 | Draft，推荐优先 |
| A-11 | Artifact/导出访问方式未定义 | 控制面 API + 大文件预签名 + 敏感文件代理的混合模式 | Draft/TBD |
| A-12 | LangGraph 是否承担平台工作流 | 仅 Agent/Copilot interrupt bridge，不替代审批/状态机 | Draft |
| A-13 | MCP 分期表述 | M0-M3 不采用；M4 仅只读 POC 候选 | Draft/TBD |

本表所有内容均未批准。

---

## 18. 开放问题

| # | 开放问题 | 建议归属 | 阻塞点 |
| --- | --- | --- | --- |
| Q1 | 是否需要持久化通用异步任务对象，还是仅提供操作回执 | problem_model 变更评审 + Stage 7 | AI/导入/导出统一查询方式 |
| Q2 | SSE 事件保留窗口、连接数、重连上限与降级轮询频率 | 后端配置项 + Stage 7 | 实时通道容量与 UX |
| Q3 | 事件 ID 是按租户、资源还是订阅流排序；缺口如何明确表达 | Stage 7 | 可恢复订阅协议 |
| Q4 | ETag 应覆盖哪些平台内可编辑资源 | Stage 7 + 数据模型评审 | 乐观并发一致性 |
| Q5 | UI 命令幂等回执的签发、时效和重复参数冲突语义 | Stage 7 | 网络未决安全重放 |
| Q6 | Approval TTL、升级时点/轮次、WAITING 状态告警阈值 | 后端配置项 | 审批与滞留治理 |
| Q7 | agent_tool_action/perf_high_risk 获批后执行失败时 TestRun 如何合法收敛 | problem_model/工作流评审 | 状态联动完整性 |
| Q8 | Excel 导入 TestCase 初始状态与是否强制进入评审流 | PRD/problem_model | 数据迁移安全 |
| Q9 | Artifact 上传大小/类型、病毒扫描、checksum 与失败清理策略 | 安全 + 后端设计 | 上传安全与成本 |
| Q10 | Artifact/Evidence/审计保留期和预签名最长 TTL | 法务 + 安全 | 合规与访问控制 |
| Q11 | Release 系统是否支持幂等创建、ETag 和状态 webhook | 集成 Owner | ReleaseTask 可靠联动 |
| Q12 | 通知的站内形态、订阅规则、渠道优先级与 episode 去重 | 产品/原型 + Stage 7 | 告警噪声与可达性 |
| Q13 | LangGraph checkpoint 的持久化、加密、tenant 清理和恢复 SLO | Agent/Copilot 技术评审 | interrupt bridge 可恢复性 |
| Q14 | M4 只读 MCP POC 的工具白名单、试点 tenant 与退出标准 | M4 专项评审 | 是否进入 POC |
| Q15 | A1 草稿暂存时长、多端续审与完成后访问语义 | Stage 7 | AI 生成异步体验 |

---

## 19. Stage 7 OpenAPI 的输入清单

后续 OpenAPI 设计应消费但不得擅自改变以下语义：

1. 命令与查询分离、受理与完成分离；
2. 每请求认证、tenant、RBAC，跨 tenant 不泄露存在性；
3. 服务端幂等、ETag/版本、`param_hash` 与行锁各自独立；
4. TestRun 10 态及等待态/活跃态纪律；
5. ApprovalRequest 六态、九要素、四眼、TTL、重提与 execution_result；
6. SSE 只展示，GET 为权威，支持事件 ID、重连和轮询降级；
7. 外部 CI webhook + 持久轮询双通道；
8. 所有 partial/failed/degraded 均显式；
9. 普通上传和普通异步任务不默认 HITL；
10. Artifact/导出使用私有、短期、最小权限访问候选；
11. LangGraph 不替代业务状态机或审批；
12. M0-M3 不采用 MCP，M4 只读 POC 仍待评审；
13. 通知、AuditEvent、EvidenceObject 全链路可追溯；
14. 不在 OpenAPI 中新增未获 problem_model 批准的状态或领域对象。

本文保持 **Status: Draft**；所有推荐与 TBD 均待后续评审，不代表批准。
