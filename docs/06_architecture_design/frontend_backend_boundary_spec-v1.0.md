# 前后端功能边界规范（frontend_backend_boundary_spec · v1.0）

> - **Status: Draft**
> - **日期**：2026-08-25 · **版本**：v1.0
> - **流程定位**：Stage 6（系统架构设计）**前后端边界分册**——收口「前端职责 / 后端职责 / 数据与逻辑归属 / API 调用与错误边界」；与同目录 [frontend_design_spec-v1.0.md](frontend_design_spec-v1.0.md)（前端分册：页面 / 组件 / 状态呈现）、[architecture.md](architecture.md)（后端架构骨架）共同构成 Stage 6 产出
> - **上游输入**：[problem_model.md](../03_problem_modeling/problem_model.md)（下称 **05**：§1.1 领域对象 23 个 / §2 状态机全集 / §3 FR×对象 CRUD 矩阵 / §4.2 25 页 IA / §5 A1–A8——唯一建模事实源）· [interaction_flows.md](../04_interaction_design/interaction_flows.md) 及 [chains/](../04_interaction_design/chains/)（下称 **06 / C1–C4**：页面流 / 分支异常 / 审批与副作用点 / 证据落点）· [frontend_design_spec-v1.0.md](frontend_design_spec-v1.0.md)（P01–P25 编号 / §1 职责边界 / §5 本地交互清单）
> - **下游消费者**：[07_backend_design](../07_backend_design/README.md)（API 契约设计的直接输入——本文 §2 输入/输出语义 + §7 错误类别）· Stage 10 AI 上下文 · Stage 11 前端实现 · Stage 12 后端实施
> - **收口纪律**：功能/操作 ⊆ 05 §3 CRUD 矩阵 + C1–C4 已定义交互；页面 ⊆ P01–P25；状态与跳转 ⊆ 05 §2；领域对象 ⊆ 05 §1.1（**23 个**）；**不新增功能、页面、状态、对象、字段**；上游缺口只登记（§9），不自行发明
> - **不做什么**：不定义 API 路由 / 错误码 schema / 分页与过滤协议 / SSE 帧格式（归 07_backend_design API 契约）；不重复 frontend_design_spec 的组件级设计（其 §1 职责边界与本文 §1 判定原则互为引用）；不含任何代码
> - **术语约定**：「05」「06 / C1–C4」「12-PRD」「README」以各文档文首版本头为唯一事实源；页面编号 P01–P25 沿用 frontend_design_spec §2

---

## 1. 总则：边界判定七原则

| # | 原则 | 说明 | 依据 |
| --- | --- | --- | --- |
| 1 | **状态机唯一裁决在后端** | TestRun / ApprovalRequest / ReleaseTask / ExecutionEnvironment / TestCase 五类状态机的全部迁移由服务端触发与判定；前端只发起用户动作请求、渲染服务端下发状态，**不推演迁移结果** | 05 §2 · frontend_design_spec §1.1 |
| 2 | **权限与安全边界唯一在后端** | 认证 / RBAC / 租户过滤（tenant_id）每请求强制；前端的角色置灰与只读呈现仅为 UX，不可作为安全边界；跨租户引用一律 404 不泄露存在性 | FR-01 · 12-PRD §2.3 |
| 3 | **副作用与外部系统访问必经后端** | Jira / GitHub / CI / Release / 模型网关的调用一律经后端连接器（凭证只存 Vault 引用）；**前端不直连任何外部系统、不持有任何外部凭证** | README 9.16 · 05 §2.5 |
| 4 | **AI 调用唯一出口在后端** | A1–A8 全部能力经后端 LLM 工厂调用并记 AIInvocationLog（无旁路）；前端不直接调用任何模型 | FR-02 · README 7.12 |
| 5 | **前端本地逻辑仅限呈现与提示性校验** | 表单即时校验、联动置灰为提示性；最终校验（Job Schema / 双层变量 / 存在性 / 配额 / 白名单）与裁决（Policy Gate 四值）以后端为准 | FR-17/18 · C3 ②2 |
| 6 | **成功 / 失败以后端结果为准** | 按钮反馈 ≠ 业务成功；前端在收到后端确认前只可呈现「受理 / 提交中」乐观态，不得将 UI 推进为「已完成」；网络中断后结果未决时以服务端查询为准，不得假定成功或失败 | §6 / §7 · C1–C4 ④ |
| 7 | **本文定义语义契约，不定协议** | §2 的「输入 / 输出」为数据语义（领域对象与关键字段）；路由、错误码 schema、分页协议、SSE 帧格式归 07_backend_design | architecture.md 输出结构 · frontend_design_spec 缺口 G3 同源 |

---

## 2. 功能边界总表（按模块）

> **列口径**：
> - **功能/操作**：附 FR / 链路 / 页面溯源（P 编号沿用 frontend_design_spec §2）；
> - **用户动作**：「无（系统触发）」行为为系统侧动作的显式登记（其后端职责同样入表）；
> - **输入 / 输出**：API **语义契约要点**（非最终 schema，协议归 07_backend_design）；
> - **状态变化**：状态迁移只引用 05 §2 已定义状态；对象创建 / 更新沿用 05 §3「对象:操作」记法；「—」= 无状态迁移。
> - 里程碑（M0–M4）随页面归属（05 §4.2）；M3+ / M4 模块边界同样冻结，实现延后。

### 2.1 认证与租户（FR-01 · 全局）

| 功能/操作 | 用户动作 | 前端职责 | 后端职责 | 输入 | 输出 | 状态变化 |
| --- | --- | --- | --- | --- | --- | --- |
| SSO 登录与会话维持（FR-01） | 经企业 SSO 登录；会话过期重新登录 | 跳转 SSO；401 统一拦截并引导重登；REQUIRE_REAUTH 时引导再认证 | SSO 对接、会话签发与校验；再认证窗口判定（L3+ 动作触发，FR-17）；无租户上下文一律拒绝 | SSO 凭证 / 回调 | 会话上下文（用户、租户、项目角色） | —（会话态，非领域对象） |
| 角色与只读呈现（FR-01 · C2 ①1.1） | 以 viewer 等角色浏览 | 按角色渲染入口：viewer 全局只读、无发起 / 审批入口；权限不足按钮置灰 + 无权限态页面 | 每请求 RBAC 判定（owner/admin/tester/viewer）+ ORM 强制 tenant_id 过滤；越权尝试拒绝并留痕 | — | 权限判定结果（随每个响应） | — |

### 2.2 用例生成与审阅入库（FR-05 · C1 E1–E2 · P05/P07/P13 · M1）

| 功能/操作 | 用户动作 | 前端职责 | 后端职责 | 输入 | 输出 | 状态变化 |
| --- | --- | --- | --- | --- | --- | --- |
| 导入发起 AI 生成（A1 · P07） | 上传 OpenAPI / Postman / curl 并发起生成 | 文件选择 / 内容粘贴；按后端降级与预算状态置灰 A1 入口（导入本身不受降级影响）；发起请求并展示生成中 / 失败态 | 数据分级校验（≤Confidential）；OrgQuota 预算校验（超限拒新调用并通知 Owner）；A1 分批调用（失败同参数重试 1 次，temperature 0）；AIInvocationLog 记录 | 导入源（类型 + 内容）、项目上下文 | 结构化草稿（A1 Schema）+ failed_items（partial 显式、禁止静默丢弃）；生成失败显式告警 | —（默认不落库）；AIInvocationLog:C、OrgQuota:U |
| 草稿审阅编辑（P07 本地） | 逐条采纳 / 编辑 / 弃用草稿 | 左右分栏（原文 vs 草稿）；**本地编辑未保存草稿**；partial 失败列表展示（endpoint + reason） | 生成结果暂存与回取（不落库；暂存契约见 §9-G1） | （本地操作，无提交） | — | — |
| 保存草稿（FR-05） | 点击保存采纳 / 编辑结果 | 提交草稿集；展示保存结果并回 P05 | 创建 TestCase(DRAFT) + TestCaseVersion（版本化全量快照）；打 `ai-generated` 标签；入库审计 | 编辑后草稿集（A1 结构） | TestCase 列表（id、版本、ai-generated 标签） | TestCase：[*]→DRAFT（05 §2.1） |
| 提交评审（FR-05） | 提交评审 | 操作入口（角色渲染）；提交 | DRAFT→PENDING_REVIEW 迁移 + 审计；ai-generated 用例禁止直写 ACTIVE | case_id | 更新后状态 | TestCase：DRAFT→PENDING_REVIEW |
| 评审确认（FR-05） | 人工评审：通过 / 驳回 | 操作入口与意见输入；状态回显 | PENDING_REVIEW→ACTIVE（人工确认；可关联 jira_story_key）或 →DRAFT（驳回）+ 审计 | case_id、决定、（jira_story_key） | 更新后状态 | TestCase：PENDING_REVIEW→ACTIVE / →DRAFT |
| 用例废弃 / 弃用（05 §2.1） | 废弃 ACTIVE 用例 / 弃用 DRAFT | 确认对话；提交 | ACTIVE→DEPRECATED / DRAFT→DEPRECATED + 审计 | case_id | 更新后状态 | TestCase：→DEPRECATED |
| 用例失效标记（系统 · 05 §2.1 validity） | 无（系统：引用型用例绑定 Job 被外部删除 / 改名，执行前校验失败） | 渲染失效标识（不可执行）；通知呈现 | 置 validity=invalid + invalid_reason / invalidated_at；通知 Owner；Job 恢复可回 valid（可逆） | — | 失效用例标识 / 通知 | TestCase:U（validity 字段，状态机不变） |
| Web 用例详情（P13 · M2） | 步骤编辑；查看证据三件套、定位器主备与健康度 | 步骤编辑器；证据三件套查看；定位器健康呈现；定位器自愈建议入口（heal_apply，见 2.6） | 步骤编辑落库（TestCaseVersion 版本化）；证据与定位器健康度数据供给 | case_id、编辑内容 | 用例详情 / 版本数据 | TestCaseVersion:C/U |
| 用例库浏览 / 筛选 / 版本历史 / Excel 导入导出（P05） | 列表筛选（含 ai-generated 标签）、查看版本历史、导入 / 导出 Excel | 列表 UI（筛选 / 排序 / 分页进 URL）；导入上传 / 导出下载触发 | 列表与版本查询；Excel 解析入库与文件生成（导入初始状态见 §9-G2） | 查询条件（筛选 / 分页）；导入文件 | 用例列表、版本历史、导出文件 | 导入：TestCase 创建 |

### 2.3 执行发起（FR-08/18/19 · C3 · P08 · M1）

| 功能/操作 | 用户动作 | 前端职责 | 后端职责 | 输入 | 输出 | 状态变化 |
| --- | --- | --- | --- | --- | --- | --- |
| 三层配置（模式 × 环境 × 参数） | 选模式（Script / Agent）、选环境、填参数 / 定时配置 | 三层顺序冻结渲染（05 §4.3 约束 3）；联动置灰（Agent × 外部 CI 一期不可用；非 ACTIVE 环境不可选并显示原因）；按 params_schema_ref 动态生成表单 + 本地即时校验（提示性）；Agent 受限说明 | 供给可选环境列表（仅 ACTIVE + health_status + 容量 / 配额）；供给 Job 参数 Schema（params_schema_ref）；供给用例可选性（ACTIVE、validity） | （读取）项目 / 计划上下文 | 可选环境列表、Job 参数 Schema、用例可选性数据 | — |
| 发起执行（manual / schedule 配置） | 点击「发起执行」 | 提交配置；成功跳 P09；失败展示具体原因（不静默） | 前置校验（用例 ACTIVE / validity、环境 ACTIVE、执行资源配额、压测白名单与 perf_high_risk、Skill 生产版本）；创建 TestRun(PENDING) 并**冻结 snapshot**（用例版本 / 环境 / 参数）；external_ci 写 idempotency_key；转 VALIDATING 校验（Job Schema / 双层变量 / Job 存在性），失败即拒绝不进执行队列 | 用例集、execution_mode、env_id、参数集、定时配置 | TestRun（id、状态、snapshot 引用）或结构化拒绝原因 | TestRun：[*]→PENDING→VALIDATING→RUNNING / FAILED（05 §2.2） |
| 系统触发入口（ci_webhook / api_token / schedule 到点） | 无（系统触发） | —（无前端交互；结果在 P09 可见） | webhook HMAC 验签（无例外）；ApiToken scopes / project_ids / 有效期校验；定时调度；与手动触发同一状态机受理 | webhook 事件 / Token 调用 / 调度信号 | TestRun（同上） | TestRun：[*]→PENDING→…（trigger_type 四值之一，05 §2.2） |

### 2.4 执行监控与控制（FR-08/09/19 · C3 · P09/P14 · M1/M2）

| 功能/操作 | 用户动作 | 前端职责 | 后端职责 | 输入 | 输出 | 状态变化 |
| --- | --- | --- | --- | --- | --- | --- |
| TestRun 列表 / 详情查看 | 浏览列表、打开详情、筛选（状态 / execution_source） | 列表（URL 状态）；页头 10 态进度条（WAITING_APPROVAL 高亮跳审批）；聚类报告区；用例结果表下钻；证据查看器（截图 / 视频 / Trace 切换 + 回放，展示脱敏后内容）；execution_source 徽标（agent 型「不进门禁」提示、external_ci 归一化标识） | 列表 / 详情查询（CaseResult / StepRun / Artifact 引用）；SSE 推送（执行进度、报告生成进度、超大报告解析进度）；脱敏管道先于落库 | 查询条件、run_id | run 列表 / 详情、SSE 事件流 | —（只读） |
| 取消 / 终止（含 Agent 终止按钮） | 点击取消 / 终止 | 发起请求；立即显示「信号已持久化送达」（**受理反馈，非终止完成**）；STOPPING→CANCELLED 照常渲染；已采集部分结果照常可见 | 状态机裁决：PENDING→CANCELLED；RUNNING→STOPPING→CANCELLED；WAITING_APPROVAL 人工取消→CANCELLED；外部 Job 幂等取消（已产生构建记录照常采集入库）；终止信号服务端持久化（多 worker 可停） | run_id | 受理确认 + 后续状态 | TestRun：→CANCELLED（05 §2.2）；AuditEvent:C |
| Agent 任务详情查看（P14 · M2） | 查看轨迹时间线 | 轨迹时间线渲染（每步动作 + 截图 + 工具调用，A8 结构）；incomplete 标记；拒止记录可见 | 轨迹数据供给（Artifact + CaseResult 存储）；Policy Gate 裁决日志与安全事件 | run_id | A8 轨迹（steps / assertion_results / token_usage） | —（只读） |
| Agent 转脚本草稿（FR-19） | 一键转草稿并确认 | 入口 + 确认对话；跳 P05 评审流 | 轨迹→脚本产物 schema 校验；创建新 TestCase(DRAFT) | run_id（轨迹引用） | 新 TestCase（DRAFT，含脚本草稿） | 新 TestCase：[*]→DRAFT；原 run 状态不变 |
| 外部 CI 执行链路（系统 · FR-18） | 无（系统） | —（过程状态在 P09 可见：WAITING_EXTERNAL 徽标 + 滞留时长） | 幂等触发外部 Job（idempotency_key）；轮询 + webhook 双通道（先到者）；日志分片拉取；报告适配器解析（分片流式；超大报告已完成部分入库 + 显式失败标记，不静默截断）；归一化为统一 TestRun 模型 | — | CaseResult / StepRun / Artifact（归一化产物） | TestRun：RUNNING→WAITING_EXTERNAL→RUNNING→终态（05 §2.2） |

### 2.5 审批（FR-04/17 · C2 · P10 · M0）

| 功能/操作 | 用户动作 | 前端职责 | 后端职责 | 输入 | 输出 | 状态变化 |
| --- | --- | --- | --- | --- | --- | --- |
| 审批队列与卡片渲染 | 浏览待审批列表 / 批量队列 | 九要素卡片分区渲染（顺序冻结，05 §4.3 约束 1）；批量队列 UI；超时升级提示；发起人本人「批准」置灰（四眼**呈现**）；参数失效红色警示条 | 队列查询；card_payload 九要素组装（动作 / 资源 / diff / 数据来源与模型 Skill 版本 / 风险等级 / 成本估计 / 回滚能力 / 参数哈希）；四眼校验（服务端强制） | 查询条件（含审批人视角） | ApprovalRequest 列表 + card_payload | —（只读） |
| 批准 / 拒绝 / 修改后重新提交 | 三键操作（拒绝附理由；重新提交携带修改参数） | 操作区三键；理由输入；重新提交表单；结果回显（EXECUTED / REJECTED / EXPIRED） | PENDING→APPROVED / REJECTED 迁移 + 审计；重新提交 = **新** ApprovalRequest（新 param_hash、initiator_id=重新提交人、保留 origin_request_id 归因链）；四眼违例拒绝并留痕 | request_id、决定、理由 / 修改参数 | ApprovalRequest 状态 + execution_result | ApprovalRequest：PENDING→APPROVED / REJECTED（05 §2.3） |
| 执行前复核与执行（系统） | 无（系统：批准后自动） | —（结果回显于发起页） | anti-TOCTOU：Execute 参数哈希重算 + 权限重校验；consume 行锁事务原子创建唯一基础设施 execution intent + Outbox，不提前写 EXECUTED；重复 consume 返回同一执行引用；Worker 以稳定幂等键执行，调用前崩溃重领同一意图，调用后结果未知先按 external_request_id 查询；首次真实尝试后写 EXECUTED + execution_result；失败需重新发起审批 | — | 执行引用；外部写结果 {status, resource_refs, evidence, external_request_id, warnings} | ApprovalRequest：APPROVED→EXECUTED；按 action_ref 联动：perf_high_risk / agent_tool_action → TestRun：WAITING_APPROVAL→RUNNING；release_push → ReleaseTask：PENDING_CONFIRM→SUBMITTED；env_register → ExecutionEnvironment：PENDING_APPROVAL→ACTIVE；jira_write / heal_apply 无 TestRun 联动（run 已终态） |
| 审批 TTL / 升级 / 失效（系统） | 无（系统；发起人经通知感知） | 临期 / 已过期卡片高亮；「审批已失效」红色警示 | expires_at 独立 TTL；到期升级通知 escalate_to（**不自动放行**）；仍未处理→EXPIRED；撤回 / 上游取消 / 审批后参数变更→EXPIRED + reason（withdrawn / invalidated）+ 审计；关联 TestRun **过期停留 WAITING_APPROVAL**（仅拒绝 / 人工取消走 CANCELLED） | — | 状态与通知 | ApprovalRequest：PENDING→EXPIRED；TestRun 停留 WAITING_APPROVAL（05 §2.2 裁定 5） |

### 2.6 失败分诊（FR-06/07/10 · C4 · P09/P13 · M1/M2）

| 功能/操作 | 用户动作 | 前端职责 | 后端职责 | 输入 | 输出 | 状态变化 |
| --- | --- | --- | --- | --- | --- | --- |
| 聚类报告生成（系统 · A2） | 无（系统：含失败 CaseResult 的终态 run 触发；CANCELLED / TIMEOUT 已入库结果旁路进入） | —（报告就绪后详情页可见；生成中 SSE 进度流） | 归一化（含 external_ci 报告适配器，确定性管道非 AI）；A2 聚类（schema 校验失败重试 1 次→规则聚类 fallback，confidence 0.3、result=degraded）；evidence_refs 服务端校验（只允许输入证据池内 ID，违规整批拒收）；FailureCluster 生成；AIInvocationLog | — | FailureCluster（簇 + unclustered_refs） | FailureCluster:C（随 run 只读生成，无状态机） |
| 聚类报告查看 | 阅读簇卡片、无法判断项、修改历史、历史相似失败对比 | 簇五要素渲染（类别 7 值枚举 / confidence / 阻塞判断 / 证据链接 / 人工修正入口）；unclustered_refs 独立区块逐条可点开；「修改历史」；AI 降级局部横幅（规则聚类来源标注） | 报告数据查询（簇 / 证据引用 / 修正历史 / 相似失败检索） | run_id | 聚类报告数据 | — |
| 人工修正聚类 | 修正类别 / 阻塞判断等并提交 | **本地编辑（提交才调 API）**；原值留痕展示 | correction_history[] 留痕（actor / field / old / new / timestamp）+ AuditEvent | 簇 id、修正字段（old→new） | 更新后簇 + 修正历史 | FailureCluster:U（无状态机，留痕） |
| 建 Jira 缺陷（jira_write · L2 · FR-14） | 从失败簇一键发起（自动附证据附件与复现步骤） | 入口与预览（目标项目 / 描述 / 附件清单）；审批跳转；issue 链接回显 | 创建 jira_write ApprovalRequest（param_hash + 九要素）；审批通过并复核后经连接器创建缺陷 + 链接回写（幂等键 + external_request_id）；EvidenceObject 挂接；外部写失败按连接器重试策略、不重复建缺陷 | 簇 / CaseResult 引用、缺陷描述、证据附件清单 | ApprovalRequest；EXECUTED 后 issue 链接回显 | ApprovalRequest 生命周期；TestRun 不变（终态） |
| 自愈建议查看与应用（heal_apply · L3 · FR-06/10） | 查看 fixes / 定位器建议 diff 预览；confidence ≥0.7 时点击「可应用」 | diff 查看器（field / current / suggested / reason）；「可应用」入口可见性（confidence 门控，**仅呈现**；实际应用必经审批）；审批跳转 | A3 / A4 建议生成（can_auto_apply 恒 false）；heal_apply 审批；应用前快照 snapshot_ref（**快照失败 fail-close 中止**）；审批执行写新 TestCaseVersion 并更新 current_version_id；回滚端点 | 建议 id、确认参数 | ApprovalRequest；应用后版本信息 | ApprovalRequest 生命周期；TestCase:U（current_version_id，生命周期状态不变；05 §2.1） |
| 自愈回滚 | 恢复快照版本 | 版本历史入口 + 确认 | 回滚端点执行（恢复快照版本，回滚后用例可执行）+ 审计 | case_id、目标版本 | 更新后 current_version_id | TestCase:U（版本指针） |

### 2.7 质量门禁（FR-12/13 · C1 E4 · P11/P12 · M1→M2）

| 功能/操作 | 用户动作 | 前端职责 | 后端职责 | 输入 | 输出 | 状态变化 |
| --- | --- | --- | --- | --- | --- | --- |
| 门禁策略配置（P11） | 配置阈值（通过率 / p95 / 错误率）、切换模式 | 表单 + 「仅报告 ⇄ 阻断」**显式开启确认**；三域同模型呈现 | QualityGatePolicy CRUD（版本化）+ 审计；mode 切 blocking 须显式开启（上线初期仅报告）；策略修改**不改写**历史 GateEvaluation | project_id、thresholds、mode、scope | 策略详情（含版本） | QualityGatePolicy:C/U |
| 门禁评估与 Check Run 回写（系统） | 无（系统：execution_source∈{script, external_ci}，且 TestRun∈{SUCCEEDED, FAILED}、归一化完整、策略可评估时触发；agent 型不生成） | —（结果在 P12 可查） | GateEvaluation 生成（评估时策略快照、逐阈值明细、result = pass / fail / waived，不可变）；CANCELLED / TIMEOUT / 阈值缺配 / 报告 partial 当前不创建 GateEvaluation，查询投影必须返回明确 reason，Release fail-close；`not_evaluated + reason` 仍为 Proposed 上游变更；Check Run 三段式回写 + 失败重试 + 告警；TestRun.gate_evaluation_id 挂接 | — | GateEvaluation + check_run_ref；或无评估 reason | GateEvaluation:C；TestRun:U（挂接引用） |
| 评估历史查看（P12 · M2） | 查看评估明细、Check Run 回写状态、豁免记录 | 列表 / 详情渲染（回写状态、豁免记录） | 评估历史查询 | 查询条件 | GateEvaluation 列表 / 明细 | — |
| 门禁豁免（gate_waiver · L3） | owner / Test Lead 发起豁免（附说明） | 入口与豁免说明输入 | gate_waiver 审批（四眼）；豁免记录 + AuditEvent；豁免不改写原评估（不可变，重评估生成新记录） | evaluation / run 引用、豁免说明 | ApprovalRequest；豁免记录 | ApprovalRequest 生命周期；GateEvaluation 不可变（豁免引用挂接） |

### 2.8 Release 编排（FR-15 · C1 E6 · P17 · M3）

| 功能/操作 | 用户动作 | 前端职责 | 后端职责 | 输入 | 输出 | 状态变化 |
| --- | --- | --- | --- | --- | --- | --- |
| 创建任务与版本圈定 | 圈定 Jira fixVersion 创建任务 | 圈定 UI；范围快照冻结提示 | 单向读取范围内 issue；创建 ReleaseTask(DRAFT) + **范围快照冻结**（防 Jira 漂移） | project_id、fixVersion | ReleaseTask（含范围快照） | ReleaseTask：[*]→DRAFT（05 §2.6） |
| Readiness Gate 评估 + A5 草稿（系统） | 无（系统评估与草稿就绪；用户查看） | 红黄绿分区呈现不达标项；证据汇聚面板；A5 草稿只读编辑（missing_inputs 显式列出） | 证据汇聚（计划结果 / 门禁结论 / 基线对比 / 未关闭缺陷）；Readiness Gate 评估；A5 草稿生成（**禁止自动推送**）；DRAFT→PENDING_CONFIRM | — | 评估结果（红黄绿）+ A5 草稿 + 汇聚证据 | ReleaseTask：DRAFT→PENDING_CONFIRM；AIInvocationLog:C |
| 推送预览与确认（release_push · L4 域仅准备） | 预览并确认推送 | 推送预览 UI + 确认；审批跳转 | release_push 审批（param_hash）；审批通过后调用 Release 系统**准备** release item（幂等键防重复创建）；PENDING_CONFIRM→SUBMITTED | task_id、确认参数 | ApprovalRequest；SUBMITTED 状态 | ApprovalRequest 生命周期；ReleaseTask：PENDING_CONFIRM→SUBMITTED |
| 状态回传（系统） | 无（系统：Release 系统 webhook 回传） | —（READY 呈现） | 状态回传接收与落账 | — | 更新后状态 | ReleaseTask：SUBMITTED→READY |
| 重试 / 取消 | 调用失败后人工重试；或取消任务 | 失败原因展示 + 重试 / 取消入口 | FAILED_RETRYABLE→SUBMITTED（人工幂等重试）；PENDING_CONFIRM / FAILED_RETRYABLE→CANCELLED | task_id | 更新后状态 | ReleaseTask：→SUBMITTED / →CANCELLED |

### 2.9 执行环境（FR-18 · C2/C3 · P15 · M0）

| 功能/操作 | 用户动作 | 前端职责 | 后端职责 | 输入 | 输出 | 状态变化 |
| --- | --- | --- | --- | --- | --- | --- |
| 环境注册与审批（env_register · L3） | 发起环境注册（平台执行器 / 外部 CI + Job 契约） | 注册表单（endpoint、Job 契约配置；**凭证不落前端**）；提交后状态呈现 | 创建 ExecutionEnvironment(PENDING_APPROVAL)；凭证存 Vault 引用；env_register 管理员审批；PENDING_APPROVAL→ACTIVE；激活后健康检查与 Job 发现（Job Registry / 参数 Schema 供给 P08 动态表单） | 环境配置（类型、endpoint、Job 契约） | 环境详情（凭证仅引用） | ExecutionEnvironment：[*]→PENDING_APPROVAL→ACTIVE（05 §2.4） |
| 健康检查与状态治理（系统） | 无（系统周期探活；管理员可停用） | 健康状态 / 最近探活时间 / 延迟呈现；发起侧不可选渲染 | 周期健康检查；ACTIVE→DEGRADED（失败）/→DISABLED（停用）；DEGRADED / DISABLED **只影响新发起**，在途 run 不中断 | — | health_status | ExecutionEnvironment：ACTIVE→DEGRADED→DISABLED |

### 2.10 性能压测（FR-11 · C2/C3 · P16 · M3）

| 功能/操作 | 用户动作 | 前端职责 | 后端职责 | 输入 | 输出 | 状态变化 |
| --- | --- | --- | --- | --- | --- | --- |
| 压测场景配置与发起 | 配置场景并发起 | 白名单环境选择 + 护栏提示；场景级互斥排队提示；基线对比图与压力机自监控呈现 | 白名单校验（白名单外目标 100% DENY，**不进审批**）；大并发 / 长时长→perf_high_risk 审批；场景级互斥（第二次请求排队）；OrgQuota 压测并发预算；SLA 熔断与 kill switch（RUNNING→STOPPING）；压测任务**严禁自动重试** | 场景配置、参数 | TestRun（perf 型）或 DENY / 排队提示 | TestRun 状态机；ApprovalRequest（perf_high_risk） |
| 基线管理（PerfBaseline） | 创建 / 停用基线、查看对比 | 基线列表与对比图渲染 | PerfBaseline CRUD；同场景唯一活跃（创建自动停用旧基线）；基线对比数据供给 | scenario、指标快照 | 基线数据与对比结果 | PerfBaseline:C/U（旧基线自动停用） |

### 2.11 集成与 Token（FR-13/14/15/18 · P03/P25 · M0→M2）

| 功能/操作 | 用户动作 | 前端职责 | 后端职责 | 输入 | 输出 | 状态变化 |
| --- | --- | --- | --- | --- | --- | --- |
| 组织级连接器管理（P25） | 注册 / 配置连接器（Jira / GitHub / CI / Release）、查看健康状态 | 配置表单（凭证不落前端）、健康状态呈现 | Connector CRUD；凭证 Vault 引用；动作契约（sideEffectLevel / supportsPreview / Idempotency / Compensation）；HMAC 强制无例外；egress 白名单限定已注册域 | 连接器类型、auth 配置 | 连接器详情与健康状态 | Connector:C/U |
| 项目级触发绑定（P03 · M2） | 配置仓库 / 分支 ↔ 测试计划触发绑定 | 绑定配置 UI | 绑定存储；ci_webhook 事件匹配并触发执行（trigger_type=ci_webhook） | 仓库 / 分支、计划 / 用例集 | 绑定列表 | —（配置数据） |
| ApiToken 签发与吊销（P25） | 签发 Token、吊销、查看列表 | 签发表单（scopes / project_ids / 有效期）、列表呈现 | 签发（细粒度 scopes + 有效期）；吊销即时生效；last_used_at 异步更新；Token 进认证链 | scopes、project_ids、有效期 | Token 信息（签发结果） | ApiToken:C/U（revoked_at） |
| webhook 投递与出站通知渠道（P25） | 查看入站 webhook 接收与投递历史 / 失败重试；配置出站通知渠道 | 历史列表渲染；渠道配置表单 | 接收 / 投递记录查询；失败重试治理；出站通知渠道配置（主备容灾）——**通知的产生与投递一律服务端**，前端只呈现 | 查询条件 | 投递历史 | — |

### 2.12 Copilot 与技能（FR-16 · P18 M3+；README 5.2 · P19 M4）

| 功能/操作 | 用户动作 | 前端职责 | 后端职责 | 输入 | 输出 | 状态变化 |
| --- | --- | --- | --- | --- | --- | --- |
| Copilot 会话（A6 · M3+） | 自然语言查询、选择技能 | 对话 UI；引用（citations）展示；技能选择；AI 降级横幅 | CopilotSession **服务端持久化**；A6 回答（citations 校验、白名单外工具记 refused_policies）；只读技能不改变链路控制流；AIInvocationLog | 会话 id、问题、技能选择 | A6 结构化回答（answer / citations / tool_calls / refused_policies） | CopilotSession:C/U；AIInvocationLog:C |
| 技能管理与三级发布（P19 · M4） | 管理版本、提交 / 审核发布 | 版本列表、审核操作、金标准测试集结果呈现 | SkillVersion 管理（manifest：allowedTools / max_steps / 超时 / 副作用上限）；三级发布（personal→team Owner 审核→org 管理员+安全）；金标准测试执行；未版本化不进生产 | manifest、instructions | 版本与发布状态 | SkillVersion:C/U |

### 2.13 管理与治理（P01/P21–P24 · M0）

| 功能/操作 | 用户动作 | 前端职责 | 后端职责 | 输入 | 输出 | 状态变化 |
| --- | --- | --- | --- | --- | --- | --- |
| 工作台聚合视图（P01） | 查看待审批 / 进行中 run / 门禁异常 / 预算余量；点击跳转 | 卡片渲染；临期 / 已过期审批高亮；等待态（WAITING_APPROVAL / WAITING_EXTERNAL）滞留时长持续展示，**不得因长时间等待隐藏** | 聚合查询（四类数据源：待审批列表、活跃 run、门禁异常、部门预算余量） | 用户 / 租户上下文 | 聚合数据 | —（只读聚合） |
| AI 成本看板（P21） | 查看部门 Token 消耗 / 采纳率 / 降级率 / 每工作流成本 | 图表呈现 | AIInvocationLog 聚合计算（唯一出口数据源） | 时间范围 / 维度 | 聚合指标 | — |
| 模型路由配置（P22） | 配置路由表、数据分级约束、测试连接 | 配置表单；测试连接触发与结果呈现 | ModelRoute CRUD（数据分级约束、成本上限、fallback）；测试连接探测 | 路由配置 | 路由表 + 测试连接结果 | ModelRoute:C/U |
| AI 能力开关与降级（P23） | 切换四级 kill switch（单能力→模块→连接器写入→全局 AI）；发起压测 kill switch 演练 | 开关 UI；当前降级状态与横幅生效范围呈现；压测 kill switch 演练入口 | **关停（收紧）= L1 即时生效、不走审批**（事故响应优先）；**恢复（放开）= L3 kill_switch_restore 审批**；两向均写 AuditEvent；降级状态与横幅范围下发 | 开关目标（能力 / 模块 / 连接器 / 全局）、方向 | 开关状态 + 降级标志（全局横幅数据） | AuditEvent:C（两向留痕）；恢复走 ApprovalRequest（kill_switch_restore） |
| 审计检索（P24） | 全字段检索、配置 SIEM 外发 | 检索 UI、外发配置表单 | AuditEvent 全字段查询（append-only）；SIEM 外发配置 | 检索条件（actor / request_hash / approval.bound_hash 等） | 审计记录 | —（append-only 只读） |
| 证据中心（P20） | 证据检索、证据包导出 | 检索 UI、导出入口（ZIP / MD / JSON） | EvidenceObject 检索；证据包打包导出（访问方式见 §9-G5） | 检索条件、导出范围 | 证据列表 + 导出产物 | —（append-only 只读） |

### 2.14 项目与计划（P02/P04/P06 · M0/M1）

| 功能/操作 | 用户动作 | 前端职责 | 后端职责 | 输入 | 输出 | 状态变化 |
| --- | --- | --- | --- | --- | --- | --- |
| 项目总览（P02） | 查看工具连接状态、Jira 映射、最近活动 | 状态卡片渲染 | Project 查询（项目从 Jira 只读同步，无手工建项目）；Connector 健康状态；最近活动 | project_id | 总览数据 | — |
| 项目设置（P04） | 管理成员与角色、通知订阅、查看项目级配额 | 成员管理 UI、订阅设置 | ProjectMember CRUD（owner / admin / tester / viewer）；通知订阅存储；项目级配额视图（OrgQuota） | 成员 / 角色变更、订阅配置 | 成员列表、订阅状态 | ProjectMember:C/U/D |
| 测试计划管理（P06） | 计划编排（关联 Jira fixVersion）、选择用例集、绑定定时回归、查看执行历史与计划级报告 | 计划编辑 UI、报告呈现 | TestPlan CRUD；计划 ↔ 用例集关联；定时回归绑定；计划级报告聚合（FR-15 证据汇聚输入） | 计划配置 | 计划详情与报告 | TestPlan:C/U |

---

## 3. 数据归属边界

### 3.1 只能由后端提供的数据（前端不得本地生成、推演或作为事实源缓存）

| # | 数据类别 | 内容 | 供给语义 |
| --- | --- | --- | --- |
| 1 | 领域对象数据 | 05 §1.1 全部 23 个对象的列表 / 详情 / 历史 / 检索结果 | 查询接口 |
| 2 | 状态机数据 | 五类状态机当前态、状态时间线（含触发节点与操作者） | 随对象下发 + SSE 推送 |
| 3 | 权限与租户 | 角色、可操作范围、REQUIRE_REAUTH 指令、四眼约束 | 随每个响应 / 裁决返回 |
| 4 | 审批卡片数据 | card_payload 九要素、param_hash、失效标志、TTL / 升级状态 | 审批接口下发 |
| 5 | AI 输出 | A1–A8 全部结构化输出（含 failed_items、unclustered_refs、confidence、降级标注 refused_policies） | AI 能力接口（唯一出口） |
| 6 | 聚合与观测数据 | 工作台四组件、AI 成本指标（Token / 采纳率 / 降级率 / 每工作流成本）、环境健康状态、配额与预算余量 | 聚合接口 |
| 7 | 配置数据 | 门禁策略、模型路由、连接器、环境与 Job 参数 Schema、Skill manifest、超时 / TTL 配置项（数值归 Stage 8 配置项表） | 配置接口 |
| 8 | 降级与开关状态 | AI 降级标志（全局横幅数据）、kill switch 状态与生效范围 | 全局状态接口 |
| 9 | 通知数据 | 审批结果、超时告警、用例失效、Check Run 回写失败告警（产生与投递服务端，前端只呈现） | 通知接口 / 推送（形态见 §9-G4） |
| 10 | 检索结果 | 审计全字段检索、证据检索（含脱敏后内容——脱敏管道先于落库） | 检索接口 |
| 11 | 外部资源引用 | Jira issue 链接、check_run_ref、external_request_id、Artifact 引用与访问方式 | 随对象 / 执行结果下发（访问契约见 §9-G5） |

### 3.2 前端本地数据（不落库、不构成事实源）

1. UI 状态：选中 / 展开 / 折叠 / Tab / 对话框开关；
2. 列表 URL 状态：筛选 / 排序 / 分页（一律进 URL，可分享可回溯）；
3. 未提交表单：三层配置选择、P07 草稿编辑、聚类修正编辑、豁免说明草稿；
4. 查看器状态：diff 滚动、Trace 回放进度、证据三件套切换；
5. SSE 订阅状态与服务端状态缓存（TanStack Query 缓存——**缓存可有时效，冲突一律以后端为准**，失效策略见 frontend_design_spec §6.14）。

### 3.3 前端禁止事项（数据层红线）

1. 禁止推演状态机迁移结果（不得由 SSE 事件自行推导「应该已 SUCCEEDED」，终态只认后端下发）；
2. 禁止以本地权限判定替代后端校验（隐藏入口 ≠ 安全边界，后端每请求强制复核）;
3. 禁止本地计算聚类 / 成本 / 配额 / 门禁等指标（只能渲染后端聚合与评估结果）；
4. 禁止将领域数据持久化为本地事实源；
5. 禁止本地生成 param_hash / 幂等键（一律后端生成与复核）；
6. 禁止直连 Jira / GitHub / CI / Release / 模型网关等任何外部系统。

---

## 4. 逻辑归属边界

### 4.1 只能由后端决定的逻辑（前端只发起请求、渲染结果）

| # | 逻辑 | 依据 |
| --- | --- | --- |
| 1 | 五类状态机全部迁移与终态判定（TestRun 迁移以 problem_model 的 canonical transition registry 为唯一来源，不手写边数；含 STOPPING→TIMEOUT；审批 consume、Release 推送、环境治理、用例评审） | 05 §2 |
| 2 | Policy Gate 裁决（ALLOW / DENY / REQUIRE_APPROVAL / REQUIRE_REAUTH）与副作用分级适用（L0–L4；未声明动作默认拒绝） | FR-17 · README 7.9 |
| 3 | 四眼校验、行锁防双执行、anti-TOCTOU 参数哈希复核 | 05 §2.3 · README 9.12 |
| 4 | 权限与租户判定（RBAC + tenant_id 强制过滤） | FR-01 |
| 5 | 审批 TTL、超时升级、EXPIRED（任何情况不自动放行） | 05 §2.3 · 12-PRD §2.3 |
| 6 | 幂等（idempotency_key、外部写幂等键）与补偿（重试策略、快照恢复） | FR-18 · README 9.14 |
| 7 | 心跳检测与僵尸回收（RUNNING→TIMEOUT）、终止信号持久化与停止流程 | FR-08/19 |
| 8 | 快照冻结（TestRun.snapshot、ReleaseTask 范围快照、heal_apply 应用前快照 fail-close） | 05 §2 · README 9.7 |
| 9 | 门禁评估（阈值判定、策略快照、豁免资格、execution_source 门禁资格——agent 型不进） | FR-12/13 · README 4.0 |
| 10 | AI 调用全链路（模型路由、重试、fallback、降级顺序、usage / cost 计量、脱敏、evidence_refs 校验） | FR-02/03 · 12-PRD §7.2 |
| 11 | 报告归一化（适配器解析、分片流式、部分入库显式标记） | FR-07/18 |
| 12 | 配额与预算判定（超限拒新调用并通知 Owner） | FR-03 |
| 13 | param_hash 计算 | README 9.12 |
| 14 | 存在性与 404 策略（跨租户统一 404 不泄露存在性） | 12-PRD §2.3 |
| 15 | 通知的产生与渠道投递 | P25 集成中心 |
| 16 | 外部系统写入与重试（连接器统一出口，返回 external_request_id） | 05 §2.5 · 12-PRD §4.3 |

### 4.2 属于前端 UI 的逻辑（无服务端状态变更）

1. 渲染：七态基线 + 链路特殊态（frontend_design_spec §5.1）；
2. 表单即时校验（格式 / 必填 / 类型——提示性）；
3. 联动置灰（模式 × 环境组合、非 ACTIVE 环境、角色只读）；
4. 动态表单生成（按 params_schema_ref 渲染控件）；
5. 查看器与控件（diff 查看器、参数哈希折叠、Trace 回放、证据三件套切换）；
6. SSE 订阅与渲染（断线重连策略归 API 契约，§9-G3）；
7. 列表 URL 状态管理（筛选 / 排序 / 分页）；
8. 响应式布局切换（语义不变，仅布局降级）；
9. 入口可见性（confidence ≥0.7 的「可应用」、发起人「批准」置灰、M3+/M4 里程碑入口隐藏——**均仅呈现层**）；
10. 本地编辑暂存（P07 草稿、聚类修正——提交才调 API）。

### 4.3 双层参与的逻辑（前端提示性 · 后端权威性）

| 逻辑 | 前端层（提示） | 后端层（权威） |
| --- | --- | --- |
| 表单校验 | 即时格式 / 必填校验提示 | Job Schema / 双层变量 / 存在性 / 配额权威校验（不过即拒绝，VALIDATING→FAILED） |
| 环境可选性 | 非 ACTIVE 环境置灰 + 原因 | 发起时再校验，非 ACTIVE 拒绝 |
| 权限 | 角色置灰 / 只读呈现 | 每请求 RBAC + 租户过滤强制 |
| 模式 × 环境组合 | Agent × 外部 CI 置灰（一期不支持） | 受理时拒绝非法组合 |
| 自愈「可应用」 | confidence ≥0.7 门控展示入口 | can_auto_apply 恒 false，应用必经 heal_apply 审批 |
| 审批四眼 | 发起人本人「批准」置灰 | 服务端四眼复核，违例拒绝并留痕 |
| 防重复提交 | 按钮 loading / 防抖 | 幂等键 + 行锁权威防重 |

---

## 5. API 调用边界

### 5.1 必须调用 API 的操作（穷举类别，无一例外）

| # | 类别 | 覆盖操作（对照 §2） |
| --- | --- | --- |
| 1 | 全部领域对象读 | 23 个对象的列表 / 详情 / 历史 / 检索（含审计、证据、成本聚合） |
| 2 | 全部写操作与状态迁移 | 保存草稿、提交 / 评审、废弃、发起执行、取消 / 终止、转脚本、审批三键、修正聚类、建缺陷、自愈应用与回滚、策略 / 路由 / 开关 / 环境 / 连接器 / Token / 计划 / 成员配置、Release 全操作 |
| 3 | 全部 L2+ 动作 | Preview 与 Execute 均经后端（param_hash 生成与复核、Policy Gate 裁决无前端旁路） |
| 4 | 全部 AI 能力使用 | A1 生成、A5 草稿、A6 对话等——经后端 LLM 工厂唯一出口 |
| 5 | 导入导出 | OpenAPI / Postman / curl 导入、Excel 导入导出、证据包导出（ZIP / MD / JSON） |
| 6 | 实时通道 | SSE 订阅（执行进度、报告生成进度、解析进度） |
| 7 | 通知数据 | 通知列表 / 角标获取（形态见 §9-G4） |
| 8 | 制品访问 | Artifact（截图 / 视频 / Trace）与导出文件的引用获取（方式见 §9-G5） |

### 5.2 纯前端本地操作（无 API 调用）

即 §4.2 全部条目：本地表单校验、联动置灰、动态表单渲染、查看器控件、URL 状态、响应式、本地编辑暂存（P07 草稿 / 聚类修正提交前）、确认对话与防抖。

---

## 6. 成功判定边界（以后端结果为准）

> 纪律：下表「前端即时反馈」均为受理 / 提交态呈现，**任何一行的权威成功条件都以后端返回或后续状态查询为准**；两段式动作（审批 APPROVED → 执行 EXECUTED）须分别判定。

| # | 操作 | 前端即时反馈（非权威） | 权威成功条件（后端） | 依据 |
| --- | --- | --- | --- | --- |
| 1 | 保存草稿 | 保存成功提示 | TestCase(DRAFT) + Version 创建返回（含 id / 版本） | FR-05 |
| 2 | AI 生成 | 生成中状态结束 | 后端返回草稿 + failed_items；**partial 由后端判定**（失败条目显式呈现） | A1 契约 |
| 3 | 发起执行 | 跳转 P09 | TestRun(PENDING) 创建返回 run_id | FR-08 |
| 4 | 参数校验 | 本地校验通过 | 后端 VALIDATING→RUNNING（本地通过不构成受理保证） | FR-18 |
| 5 | 执行结果 | SSE 进度展示 | 后端终态（SUCCEEDED / FAILED / CANCELLED / TIMEOUT）；前端不得由进度推定终态 | 05 §2.2 |
| 6 | 审批 | 操作回执 | ApprovalRequest=APPROVED；**执行成功另判** EXECUTED + execution_result=ok（两段不同） | 05 §2.3 |
| 7 | 外部写（建缺陷等） | — | 连接器返回 {status, external_request_id}；issue 链接回显 | 12-PRD §4.3 |
| 8 | 终止 / 取消 | 「信号已持久化送达」 | TestRun 到 CANCELLED（经 STOPPING）；已采集结果照常入库 | FR-19 |
| 9 | 门禁结论 | 徽标 / 颜色呈现 | 可评估时为 GateEvaluation.result（pass / fail / waived）+ 逐阈值明细；CANCELLED / TIMEOUT / 缺配 / partial 当前为无 GateEvaluation + 明确 reason，绝不默认通过 | FR-13 |
| 10 | Readiness 结论 | 红黄绿分区呈现 | 后端评估结果数据（前端不自行汇总证据判定） | FR-15 |
| 11 | release_push | 提交回执 | ReleaseTask SUBMITTED→READY（Release 系统 webhook 状态回传） | 05 §2.6 |
| 12 | 自愈应用 | — | 新 TestCaseVersion + current_version_id 更新（EXECUTED + execution_result=ok；快照失败 fail-close = 未成功） | FR-06 |
| 13 | 门禁豁免 | — | gate_waiver 审批 EXECUTED 且豁免记录可查 | FR-13 |
| 14 | 权限 / 资格 | 置灰 / 无权限态 | 后端每请求判定 | FR-01 |
| 15 | 配额 / 预算 | 余量展示 | OrgQuota 后端计算与扣减（超限拒新调用） | FR-03 |
| 16 | Agent 任务结果 | 轨迹呈现 | A8 status + assertion_results（后端判 SUCCEEDED / FAILED；超步 / 超时 = incomplete） | FR-19 |

---

## 7. 错误处理边界

### 7.1 三类错误定义

| 类别 | 定义 | 判定方 |
| --- | --- | --- |
| **网络错误** | 请求未送达 / 超时 / 连接中断 / 5xx / SSE 断连——传输层故障，业务语义未知 | 传输层（前端检测呈现，后端无业务语义） |
| **权限错误** | 401 会话失效 / 需再认证（REQUIRE_REAUTH）；403 角色不足；跨租户引用统一 404 | **后端唯一判定** |
| **业务错误** | 后端语义拒绝：校验失败、前置状态不满足、配额 / 预算超限、Policy Gate DENY、审批失效（param_hash 不匹配）、外部系统调用失败 | 后端判定并结构化返回 |

### 7.2 处理职责表

| 类别 | 后端职责 | 前端职责 | 对状态的影响 | 用户可见反馈 |
| --- | --- | --- | --- | --- |
| 网络错误 | 幂等设计保证重试安全（idempotency_key / 行锁 / 幂等键防重复副作用）；SSE 重连支持（策略归 API 契约，§9-G3） | 可重试提示；自动重试（TanStack Query）；SSE 重连；**结果未决时以服务端查询为准，不得假定成功或失败** | 无业务状态变化（未决动作由后端幂等语义兜底） | 网络异常提示 + 重试入口 |
| 权限错误 | 每请求认证 + RBAC + 租户过滤；跨租户统一 404（不泄露存在性）；四眼违例 / 越权 / DENY 均留痕 AuditEvent | 401 统一拦截跳 SSO / 再认证引导；403 无权限态呈现；404 呈现「资源不存在」（不区分 403 / 404 渲染提示细节）；按钮置灰呈现 | 无 | 无权限态页面 / 「资源不存在」 |
| 业务错误 | 结构化返回（类别 + 原因 + 明细，schema 归 07_backend_design）；**失败也审计**（校验失败 / DENY / 四眼违例 / 僵尸回收留痕）；partial 显式（failed_items、部分入库标记）；外部失败重试 + 告警（Check Run 回写失败、Release FAILED_RETRYABLE、jira_write 连接器重试策略） | 按语义呈现具体原因（表单错误、审批失效红色警示条、DENY 提示、失败条目列表）；重试入口由后端结果驱动（FAILED_RETRYABLE 才出现重试）；**不吞错、不静默** | 按状态机落账（如 VALIDATING→FAILED、ReleaseTask→FAILED_RETRYABLE） | 具体失败原因 + 引导动作 |

### 7.3 错误呈现纪律（对齐 C1–C4 ④ 与验收口径）

1. **失败不静默**：A1 failed_items 必显式、归一化部分入库带显式失败标记、生成失败显式告警（禁止静默返回空）；
2. **失败也审计**：DENY、四眼违例、校验失败、僵尸回收均写 AuditEvent；
3. **未决不假定**：网络中断后以查询结果为准，前端不得本地回滚或推进状态；
4. **404 统一**：跨租户 / 不存在资源一律「资源不存在」，不泄露存在性；
5. **降级不静默**：任一层 AI 降级必须全局 / 局部横幅提示；降级顺序（先保平台、再保证据、最后保 AI 增强）由服务端决定，前端只渲染降级状态。

---

## 8. 一致性检查

| 检查项 | 结果 |
| --- | --- |
| 功能/操作 ⊆ 05 §3 CRUD 矩阵 + C1–C4 已定义交互 | PASS：§2 逐行标注 FR / 链路 / 页面溯源，无链路外操作 |
| 状态变化 ⊆ 05 §2 | PASS：五类状态机迁移引用 problem_model 的 canonical transition registry，不维护固定边数；含 STOPPING→TIMEOUT，审批过期不迁移 TestRun；无新增状态 / 边 |
| 页面 ⊆ P01–P25 | PASS：全部引用 frontend_design_spec §2 编号，无新页面 |
| 领域对象 ⊆ 05 §1.1（23 个） | PASS：仅出现清单内对象，无新对象 / 新字段 |
| 与 frontend_design_spec 一致 | PASS：§1 判定原则 ↔ 其 §1 职责边界；§4.2 ↔ 其 §5.3 本地交互；§5 ↔ 其 §6 服务端边界标注 |
| 不定义 API 协议 / 无代码 / 无新依赖 | PASS：输入输出仅为语义契约；协议细节显式移交 07_backend_design |

## 9. 缺口上报（不自行发明，建议归属如下）

| # | 缺口描述 | 建议归属 |
| --- | --- | --- |
| G1 | AI 生成草稿（默认不落库）的暂存与获取契约：同步返回还是任务轮询、暂存生命周期（TTL）、多端续审是否支持，上游均未定义 | 07_backend_design（API 契约） |
| G2 | Excel 导入的格式契约与导入用例的初始状态（DRAFT 还是 PENDING_REVIEW）、是否复用两步式审阅流，未定义 | 05 §2.1 或 12-PRD FR-05 补充 |
| G3 | SSE 断线重连、降级轮询、无 SSE 页面的自动刷新策略（与 frontend_design_spec 缺口 G3 同源） | 07_backend_design（推送契约） |
| G4 | 通知的前端呈现形态与获取方式（站内通知中心 / 角标 / 列表页；与 frontend_design_spec 缺口 G4 同源） | 05 §4.2 组件列或原型阶段确认 |
| G5 | Artifact（截图 / 视频 / Trace）与证据包 / Excel 导出的访问方式（直链 / 预签名 URL / 代理下载）未定义 | 07_backend_design（API 契约） |
| G6 | （登记引用，非本文新增）审批 TTL / 心跳周期 / 僵尸回收阈值 / 排队超时告警阈值 / Agent 单步与总超时等数值——已由 C2 / C3 缺口回写移交 Stage 8「超时与 TTL 配置项表」 | architecture.md（生成时收口） |

## 10. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1.0 | 2026-08-25 | 首版：基于 05 v1.3（23 对象 / 五状态机 / 25 页 / CRUD 矩阵）、06 v1.1 + C1–C4（页面流 / 分支异常 / 审批与副作用点）、frontend_design_spec v1.0（P01–P25）收口——边界判定七原则、14 模块功能边界总表（七列口径）、数据归属（后端供给 11 类 / 前端本地 / 六条红线）、逻辑归属（后端专属 16 项 / 前端 10 项 / 双层 7 项）、API 调用边界（必调 8 类 / 纯本地清单）、成功判定 16 项（以后端为准）、三类错误边界与呈现纪律；缺口 6 项上报 |
