# Stage 6 独立架构审查

> - **Status: Draft**
> - **日期**：2026-08-26
> - **审查角色**：独立架构审查 Agent D
> - **审查性质**：本审查是 finding-first 的独立审查建议，不构成批准。
> - **决策状态**：`adr/0001` 至 `adr/0008` 仍全部为 **Proposed**；本文不提升任何 Draft、Proposed、TBD、假设或 POC 的成熟度。
> - **写入边界**：本文只记录当前工作树审查结果，不修改被审文档，不恢复 `docs/05_prototype/` 的历史内容。

## 1. 审查结论摘要

初次独立审查共记录 **8 条 finding**：

| 严重度 | 数量 |
| --- | ---: |
| Critical | 0 |
| High | 2 |
| Medium | 5 |
| Low | 1 |

未发现会立即导致数据泄露或越权执行的 Critical 级架构结论。已发现的两项 High 分别影响：

1. ApprovalRequest 单次消费与异步外部副作用之间的原子边界；
2. GateEvaluation 资格在集成架构与 Stage 7 直接输入之间的一致性。

正向结论：

- 23 个最高事实源对象在领域分册与集成架构中均有归属，没有发现漏项或暗增第 24 个领域对象。
- 审批过期后 TestRun 保持 `WAITING_APPROVAL`、Release 只 prepare、不执行生产发布、未评估不默认通过、Agent 不进门禁等当前推荐口径，在 `architecture.md` 中表达正确。
- 模块化单体控制面是当前唯一推荐；微服务仅保留有条件替代，不存在过早拆分。
- Temporal 仍是条件 POC；LangGraph 不承担业务控制面；MCP 在 M0–M3 不采用，均未被写成当前生产依赖。
- L2 自动动作采用作用域化持续授权、ProjectMember 权威拆分、ExecutionEnvironment 恢复边均继续保持 Proposed。
- `heal_apply` 继续采用 CAS/fail-close；etag 不匹配时记录 divergence，不覆盖人工修改。
- tenant、Artifact、向量检索、模型出站、日志、Evidence 与 Audit 的主要泄露面已有显式控制和验证 Gate。

### 1.1 Lead 修订后复核

| Finding | 处置 | 当前证据 | 剩余阻断 |
| --- | --- | --- | --- |
| H-01 | 已修复 | `01_domain_and_service_architecture.md:235-241`、`architecture.md:206-209`、`architecture.md:333-335`、ADR 0004/0006 | 无；实现前仍需以崩溃点测试验证 |
| H-02 | 已修复 | `frontend_backend_boundary_spec-v1.0.md:101`、`:288`、`:332`；`architecture.md:229-239` | 无 |
| M-01 | 已修复 | `frontend_design_spec-v1.0.md:26`、`:276`；`frontend_backend_boundary_spec-v1.0.md:209`、`:332` | 无 |
| M-02 | 已修复 | `00_research_and_input_traceability.md:54-60`；`architecture.md:48-55` | 无 |
| M-03 | 已修复 | `README.md:1-35`；`00_research_and_input_traceability.md:54-60` | 无 |
| M-04 | 已修复 | 00、02、03 与两份前端规范文首均为 `Status: Draft`；阶段措辞已消歧 | 无 |
| M-05 | 已修复 | `frontend_design_spec-v1.0.md:7`、`:164`、`:227`、`:248-264` | Stage 5/6 UX 交叉评审仍待 Prototype Owner 恢复或批准替代输入 |
| L-01 | 延后接受 | 文件名是本任务开始前既有 Stage 6 资产，且本轮要求保留既有边界文件；静默重命名会扩大链接变更面 | Owner：仓库规范 Owner + Stage 6 Lead；下次经变更流程处理，不阻断本轮用户评审 |

修订后未解决的 Critical、High、Medium 为 **0 / 0 / 0**。L-01 的延后不改变架构语义，且已给出接受理由与 Owner。

## 2. Findings

### Critical

无。

### High

#### H-01 [Resolved] ApprovalRequest 消费与异步外部副作用之间缺少无歧义的原子顺序

- **严重度**：High
- **修订后文件与准确行号**：
  - `01_domain_and_service_architecture.md:235-241`
  - `01_domain_and_service_architecture.md:421-423`
  - `architecture.md:206-209`
  - `architecture.md:333-335`
  - `architecture.md:539`
  - `adr/0004_side_effect_approval_and_pre_authorization.md:20-22`
  - `adr/0004_side_effect_approval_and_pre_authorization.md:50-55`
  - `adr/0006_connector_idempotency_and_recovery.md:15-18`
  - `adr/0006_connector_idempotency_and_recovery.md:49-56`
- **审查时问题**：文档同时规定：
  1. `EXECUTED` 表示副作用已经“尝试”，并带 `execution_result=ok/failed`；
  2. ApprovalRequest 在行锁事务内只能落“外部动作意图”，远程调用必须在事务外异步执行；
  3. consume 必须最多一次。

  但当前未定义“唯一执行意图何时创建、ApprovalRequest 何时从 APPROVED 变为 EXECUTED、Worker 崩溃后谁可再次领取、外部成功但本地结果未落账时如何恢复”的唯一顺序。若 consume 事务先写 `EXECUTED`，则远程调用尚未发生时状态已错误表示“尝试过”；若远程调用后才写 `EXECUTED`，则事务提交、消息重投或 Worker 崩溃可能产生第二次领取。稳定幂等键能降低外部重复对象风险，但不能单独消除平台内部的消费状态歧义和错误审计。
- **架构影响**：`jira_write`、GitHub Check Run、外部 CI trigger、Release prepare 等外部写可能出现“已消费但未执行”“已执行但仍显示 APPROVED”或重复调度；AuditEvent、通知和人工重提也可能基于错误状态作出判断。该缺口直接影响故障重启不重复副作用的技术 Gate。
- **明确修订建议**：在不新增业务状态的前提下，补一份候选无关的执行协议：
  1. consume 行锁事务内完成当前权限、`param_hash`、目标版本和 kill switch 复核；
  2. 原子创建以 `approval_request_id + bound_hash` 唯一约束的基础设施级 execution intent，并写同事务 Outbox；
  3. 重复 consume 看到既有 intent 时返回同一执行引用，不再创建第二个意图；
  4. Worker 以 intent 和稳定外部幂等键领取、调用、查询未知结果；
  5. 首次真实尝试后再以命令写 `EXECUTED + execution_result`；
  6. 明确外部成功但响应丢失、Worker 在调用前/后崩溃、Outbox 重投、人工重提的恢复表。

  若上述协议需要新增业务字段或状态，必须先走上游变更流程；否则应明确该 intent 是基础设施记录而非第 24 个领域对象。
- **阻断范围**：阻断 Stage 7 外部写命令契约、Connector Action 执行契约，以及 Jira/CI/GitHub/Release 写路径实现；不阻断只读查询和纯平台内无外部副作用流程的用户评审。
- **修订结果**：已补齐 `consume → 唯一基础设施 execution intent + Outbox → Worker 真实尝试 → EXECUTED` 的候选无关协议，并覆盖双 consume、调用前/后崩溃、响应丢失、Outbox 重投、人工重提和不支持幂等查询时的人工接管。该 finding 的文档阻断已解除。

#### H-02 [Resolved] GateEvaluation 资格在集成推荐与直接下游边界规范中仍相互冲突

- **严重度**：High
- **修订后文件与准确行号**：
  - `frontend_backend_boundary_spec-v1.0.md:101`
  - `frontend_backend_boundary_spec-v1.0.md:288`
  - `frontend_backend_boundary_spec-v1.0.md:332`
  - `01_domain_and_service_architecture.md:309-316`
  - `architecture.md:229-239`
- **审查时问题**：领域分册与集成架构已经正确采用当前兼容口径：仅 `script/external_ci + SUCCEEDED/FAILED + 归一化完整 + 策略可评估` 才生成 pass/fail；CANCELLED、TIMEOUT、缺配和 partial 暂以“无 GateEvaluation + 查询 reason”表达。可是 Stage 7 直接输入原先仍写成“终态 run 且非 agent 即触发 GateEvaluation”，会把 CANCELLED/TIMEOUT 纳入生成范围，且自检未标出被后续 Draft 集成规则收窄。
- **架构影响**：Stage 7 若直接消费该边界规范，可能为 CANCELLED/TIMEOUT 生成 pass/fail/waived，或把 GateEvaluation 缺失误判为尚未处理，进而污染 Check Run、Release Readiness、统计与审计。领域分册虽已登记冲突，但直接下游输入仍没有显式失效标记，因此风险仍可传播。
- **明确修订建议**：在边界规范的门禁行加入完整资格谓词，并在一致性检查中明确：
  - Agent 不生成 GateEvaluation；
  - CANCELLED/TIMEOUT、阈值缺配、报告 partial 当前不创建 GateEvaluation；
  - 查询必须返回明确 reason；
  - Release 必须 fail-close；
  - `not_evaluated + reason` 仍只是 Proposed 上游变更。

  同时在 Stage 7 输入清单中标明 `architecture.md:226-236` 为当前兼容解释，不得仅按“终态”实现。
- **阻断范围**：阻断 GateEvaluation、Check Run、Release Readiness 的 Stage 7 API 契约与实现设计；不阻断 TestRun、审批、Artifact 等其他域的用户评审。
- **修订结果**：直接边界规范已写入完整资格谓词、无评估 reason、Release fail-close 和 Proposed 枚举边界，并更新成功判定与一致性自检。该 finding 的文档阻断已解除。

### Medium

#### M-01 [Resolved] 两份前端相关规范仍保留陈旧的 TestRun 固定边数

- **严重度**：Medium
- **修订后文件与准确行号**：
  - `frontend_design_spec-v1.0.md:26`
  - `frontend_design_spec-v1.0.md:276`
  - `frontend_backend_boundary_spec-v1.0.md:209`
  - `frontend_backend_boundary_spec-v1.0.md:332`
  - `01_domain_and_service_architecture.md:620-626`
  - `architecture.md:189-195`
- **审查时问题**：前端设计和边界规范仍使用陈旧固定边数，可能遗漏 `STOPPING→TIMEOUT`，而集成架构已经明确不再维护手写边数。
- **架构影响**：前端状态时间线、OpenAPI 状态动作、状态机属性测试可能遗漏 `STOPPING→TIMEOUT`，或继续把审批过期误算为取消边。该问题会造成文档生成与测试断言漂移。
- **明确修订建议**：删除两处固定边数，统一引用 `../03_problem_modeling/problem_model.md:152-171` 的迁移契约；后续由机器可校验状态表生成文档与测试。修订后重跑两份规范的一致性自检。
- **阻断范围**：阻断 TestRun 状态动作的 Stage 7 契约冻结和 Stage 11 前端状态时间线验收；不阻断其他架构主题讨论。
- **修订结果**：两份直接消费者均删除固定边数，改为引用 canonical transition registry，并显式保留 STOPPING→TIMEOUT 与审批过期不迁移语义。文档阻断已解除。

#### M-02 [Resolved] 研究与集成追溯没有消费前端设计规范

- **严重度**：Medium
- **修订后文件与准确行号**：
  - `00_research_and_input_traceability.md:50-63`
  - `architecture.md:44-55`
- **审查时问题**：研究分册明确未读取 `frontend_design_spec-v1.0.md`，集成架构的“已消费输入”也未列该文件，因此不能证明整套 Stage 6 前后端架构已交叉核对。
- **架构影响**：集成架构的“唯一集成推荐”无法完整覆盖前端状态与页面约束；前端文档中的陈旧结论不会被正式纳入冲突登记和修订验收。
- **明确修订建议**：研究分册增加“已读取但不作为后端技术事实源”的前端设计输入；`architecture.md` 增加前端设计规范到消费清单，并登记本审查发现的状态、链接和成熟度差异。无需把页面细节复制进后端架构。
- **阻断范围**：阻断“Stage 6 前后端整体一致性已完成”的结论；不阻断后端模块化单体、Temporal POC、LangGraph/MCP 边界本身的用户讨论。
- **修订结果**：研究与集成清单已纳入前端设计规范和独立审查，并明确前端文件不作为后端技术选型事实源。文档阻断已解除。

#### M-03 [Resolved] Stage 6 README 与研究分册仍把已生成的集成架构写成占位，并遗漏新增产出

- **严重度**：Medium
- **修订后文件与准确行号**：
  - `README.md:1-35`
  - `00_research_and_input_traceability.md:50-60`
  - `architecture.md:1-8`
- **审查时问题**：Stage 6 README 只登记两份前端规范和 `architecture.md`，并继续把后者描述为占位；研究分册也沿用该描述，导致当前 00–04 与 8 份 ADR 不可发现。
- **架构影响**：按仓库阶段输出规则，产出登记是阶段完成判定入口。陈旧索引会使评审者漏读 00–04 与 ADR，或误以为 Temporal、目录结构等已经收口。
- **明确修订建议**：更新 Stage 6 README：
  - 登记 00–04、`architecture.md`、两份前端规范和 ADR 索引；
  - 把 `architecture.md` 标为当前 Draft 集成正文；
  - 明确技术选择、目录结构和 POC/TBD 尚未完成的部分；
  - 为每个文件标注用途、状态和下游消费者。
- **阻断范围**：阻断 Stage 6 阶段完成性验收和用户评审包发布；不阻断单份文档的技术讨论。
- **修订结果**：README 已按当前实际文件登记状态、职责与未决边界，研究分册不再把集成正文当占位。文档阻断已解除。

#### M-04 [Resolved] Draft 成熟度标记在分册之间不一致

- **严重度**：Medium
- **修订后文件与准确行号**：
  - `00_research_and_input_traceability.md:3-8`
  - `02_api_workflow_and_review.md:3-6`
  - `03_security_reliability_and_operations.md:3-7`
  - `frontend_design_spec-v1.0.md:1-8`
  - `frontend_backend_boundary_spec-v1.0.md:1-9`
- **审查时问题**：00、02、03 的阶段措辞可能与 Draft 成熟度混淆；两份前端相关规范只有版本号，没有明确 Status。
- **架构影响**：评审者可能把候选方案、POC/TBD 或前端直接输入误当作无需再评审的结论，特别影响 Temporal、Artifact 访问、OIDC、RLS、持续授权和状态冲突的后续处理。
- **明确修订建议**：所有 Stage 6 分册统一在文首使用独立的 `Status` 字段；删除或改写与 Draft 冲突的阶段措辞，例如改为“阶段二产出”；两份前端规范补 `Status: Draft`，并声明后续消费不得绕过冲突清单。
- **阻断范围**：阻断评审包的治理状态确认；不阻断技术内容的内部预审。
- **修订结果**：上述文件均明确 `Status: Draft`，阶段措辞已改为“阶段二产出”或等价描述。文档阻断已解除。

#### M-05 [Resolved] 前端设计规范包含多条指向当前不存在 Prototype 文件的链接

- **严重度**：Medium
- **修订后文件与准确行号**：
  - `frontend_design_spec-v1.0.md:7`
  - `frontend_design_spec-v1.0.md:164`
  - `frontend_design_spec-v1.0.md:227`
  - `frontend_design_spec-v1.0.md:248-264`
  - `00_research_and_input_traceability.md:68-80`
- **审查时问题**：前端设计规范把当前不存在的 Prototype 文件当作可达下游或模板链接，无法通过当前工作树复核。
- **架构影响**：原型验收基线和 Stage 5/6 UX 一致性无法复核；评审者点击链接会得到缺失资源，无法验证审批卡片、等待态、MCP 禁用态和 POC 标识是否已在原型中表达。
- **明确修订建议**：在不恢复历史文件的前提下，将这些链接统一标为“当前不可用的待恢复/替代输入”，并引用研究分册的缺口 ID；由 Prototype Owner 决定恢复、重建或正式替代后再重新做跨阶段 UX 评审。
- **阻断范围**：阻断 Stage 5/6 跨阶段 UX 一致性和原型验收；不阻断后端架构用户预审。
- **修订结果**：不可达 Markdown 链接已改为明确的当前不可用路径说明，并新增 Prototype Owner 的恢复/重建/替代责任。链接缺陷已解除；Stage 5/6 UX 实质复核仍作为公开输入缺口保留。

### Low

#### L-01 [Deferred] 两个既有 docs 文件名不符合仓库要求的全小写 snake_case

- **严重度**：Low
- **被审文件与准确行号**：
  - `README.md:18`
  - `README.md:19`
  - `frontend_design_spec-v1.0.md:1`
  - `frontend_backend_boundary_spec-v1.0.md:1`
  - `../00_setup/project_rules.md:40`
  - `../00_setup/project_rules.md:42`
- **问题**：`frontend_design_spec-v1.0.md` 与 `frontend_backend_boundary_spec-v1.0.md` 含连字符和点号版本片段，不符合 `docs/` 文件名全小写 snake_case 的规则。
- **架构影响**：不改变架构语义，但破坏仓库命名一致性；若后续重命名，会影响当前大量相对链接。
- **明确修订建议**：通过变更流程统一重命名为 snake_case，例如 `frontend_design_spec_v1_0.md` 与 `frontend_backend_boundary_spec_v1_0.md`，并一次性更新全部相对链接；不要在本轮审查中静默改名。
- **阻断范围**：仅阻断仓库规范收口；不阻断架构用户评审。
- **接受理由与 Owner**：这两个文件是任务开始前已存在的 Stage 6 资产，本轮又明确要求保留既有前后端边界文件；直接重命名会扩大当前评审的变更面并影响大量相对链接。由仓库规范 Owner + Stage 6 Lead 在独立变更流程中处理，当前风险接受不改变其 Draft 状态。

## 3. 关键设计追溯覆盖矩阵

| 设计主题 | 最高/上游事实源 | Stage 6 落点 | 结果 |
| --- | --- | --- | --- |
| 23 对象与关系 | `../03_problem_modeling/problem_model.md:14-104` | `01_domain_and_service_architecture.md:138-181`；`architecture.md:164-181` | 覆盖完整 |
| TestRun 10 态 | `../03_problem_modeling/problem_model.md:139-186` | `01_domain_and_service_architecture.md:258-275`；`architecture.md:185-195`；ADR 0003 | 语义正确；前端两规范已删除旧边数 |
| ApprovalRequest 六态/四眼/哈希 | `../03_problem_modeling/problem_model.md:188-220` | `01_domain_and_service_architecture.md:277-288`；`architecture.md:197-209`；ADR 0004 | 覆盖完整；异步执行协议已闭环 |
| ExecutionEnvironment | `../03_problem_modeling/problem_model.md:223-235` | `01_domain_and_service_architecture.md:287-289`；`architecture.md:208-214` | 现行边与 Proposed 恢复边区分正确 |
| ReleaseTask | `../03_problem_modeling/problem_model.md:255-268` | `01_domain_and_service_architecture.md:291-302`；`architecture.md:216-224` | prepare-only 表达正确 |
| GateEvaluation | `../03_problem_modeling/problem_model.md:252-253`；`../08_prd/prd.md:134` | `01_domain_and_service_architecture.md:307-316`；`architecture.md:229-239`；ADR 0003；`frontend_backend_boundary_spec-v1.0.md:101` | 集成推荐与直接边界规范已一致 |
| C1–C4 数据流 | `../04_interaction_design/interaction_flows.md:7-25` 及 chains | `01_domain_and_service_architecture.md:397-444`；`architecture.md:238-264` | 四链均覆盖 |
| 前后端权威边界 | `frontend_backend_boundary_spec-v1.0.md:13-23` | `02_api_workflow_and_review.md:49-83`；`architecture.md:266-294` | 主原则一致 |
| tenant/RBAC/404 | `../03_problem_modeling/problem_model.md:95-104`；`../08_prd/prd.md:151` | `02_api_workflow_and_review.md:122-156`；`03_security_reliability_and_operations.md:106-123`；ADR 0005 | 覆盖完整 |
| 幂等/并发/未知结果 | `../README.md:367-376`；C2/C3 | `01_domain_and_service_architecture.md:449-492`；`architecture.md:315-359`；ADR 0006 | 覆盖完整；Approval consume 与崩溃点顺序已明确 |
| Audit/Evidence | `../03_problem_modeling/problem_model.md:242-253` | `02_api_workflow_and_review.md:684-726`；`03_security_reliability_and_operations.md:345-376`；ADR 0007 | 覆盖完整，WORM/保留仍为 TBD |
| Artifact/对象访问 | PRD 与边界缺口 | `02_api_workflow_and_review.md:595-631`；`03_security_reliability_and_operations.md:149-183`；ADR 0007 | Draft 候选清晰，未伪装为最终方案 |
| 向量检索 | `../08_prd/prd.md:169`、`:221`、`:374` | `03_security_reliability_and_operations.md:118`、`:206`、`:226-238`；`architecture.md:360`、`:377` | tenant/ACL/分类/删除传播均有落点 |
| 模型与日志泄露 | `../08_prd/prd.md:226`、`:235` | `03_security_reliability_and_operations.md:185-215`、`:345-355`；`architecture.md:385-389` | 覆盖完整 |
| Temporal | `../08_prd/prd.md:360` | 研究分册 §5.2/§7.2；安全分册 §13；architecture §15.1；ADR 0002 | 保持条件 POC |
| LangGraph | 市场研究与产品原则 | 研究分册 §5.1/§7.1；API 分册 §14；architecture §15.2；ADR 0008 | 不承担业务控制面 |
| MCP | `../08_prd/prd.md:73`、`:303` | 研究分册 §5.3/§7.3；API 分册 §15；architecture §15.3；ADR 0008 | M0–M3 不采用，M4 只读 POC 候选 |
| 微服务边界 | 内部规模与控制/执行分离 | `01_domain_and_service_architecture.md:99-106`；`architecture.md:70-99`；ADR 0001 | 未过度引入 |

## 4. 23 个对象完整性与一致性矩阵

| # | 最高事实源对象 | 领域分册归属 | 集成架构归属 | 结论 |
| --- | --- | --- | --- | --- |
| 1 | Organization | `01_domain_and_service_architecture.md:159` | `architecture.md:170` | 一致 |
| 2 | User / ProjectMember | `01_domain_and_service_architecture.md:160` | `architecture.md:170` | 一致；权威拆分仍 Proposed |
| 3 | Project | `01_domain_and_service_architecture.md:161` | `architecture.md:170` | 一致 |
| 4 | ExecutionEnvironment | `01_domain_and_service_architecture.md:162` | `architecture.md:172` | 一致；恢复边仍 Proposed |
| 5 | TestCase (+Version) | `01_domain_and_service_architecture.md:163` | `architecture.md:171` | 一致 |
| 6 | TestPlan | `01_domain_and_service_architecture.md:164` | `architecture.md:171` | 一致 |
| 7 | TestRun | `01_domain_and_service_architecture.md:165` | `architecture.md:173` | 一致 |
| 8 | CaseResult / StepRun / Artifact | `01_domain_and_service_architecture.md:166` | `architecture.md:174` | 一致 |
| 9 | FailureCluster | `01_domain_and_service_architecture.md:167` | `architecture.md:174` | 一致 |
| 10 | EvidenceObject | `01_domain_and_service_architecture.md:168` | `architecture.md:174` | 一致 |
| 11 | ApprovalRequest | `01_domain_and_service_architecture.md:169` | `architecture.md:175` | 对象一致；执行协议见 H-01 |
| 12 | AIInvocationLog | `01_domain_and_service_architecture.md:170` | `architecture.md:179` | 一致 |
| 13 | AuditEvent | `01_domain_and_service_architecture.md:171` | `architecture.md:174` | 一致 |
| 14 | Skill (+SkillVersion) | `01_domain_and_service_architecture.md:172` | `architecture.md:179` | 一致 |
| 15 | ModelRoute | `01_domain_and_service_architecture.md:173` | `architecture.md:179` | 一致 |
| 16 | PerfBaseline | `01_domain_and_service_architecture.md:174` | `architecture.md:171` | 一致 |
| 17 | ReleaseTask | `01_domain_and_service_architecture.md:175` | `architecture.md:177` | 一致 |
| 18 | ApiToken | `01_domain_and_service_architecture.md:176` | `architecture.md:178` | 一致 |
| 19 | Connector | `01_domain_and_service_architecture.md:177` | `architecture.md:178` | 一致 |
| 20 | CopilotSession | `01_domain_and_service_architecture.md:178` | `architecture.md:179` | 一致 |
| 21 | OrgQuota | `01_domain_and_service_architecture.md:179` | `architecture.md:170` | 一致 |
| 22 | QualityGatePolicy | `01_domain_and_service_architecture.md:180` | `architecture.md:176` | 一致 |
| 23 | GateEvaluation | `01_domain_and_service_architecture.md:181` | `architecture.md:176` | 对象一致；资格冲突见 H-02 |

结论：**23/23 完整覆盖；没有发现对象漏列、重复计数或暗增业务对象。** ACTION_TARGET、JOB_CONTRACT、PROJECT_MEMBER、TEST_CASE_VERSION、STEP_RUN、ARTIFACT 等仍按从属结构处理，与最高事实源一致。

## 5. 遗漏检查清单

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| 关键设计可追溯性 | PASS | 后端链完整；前端设计与独立审查已进入研究/集成消费清单 |
| 23 个对象完整性 | PASS | 23/23 |
| 状态集合与迁移 | PASS | 集成与前端两规范均引用 canonical transition registry |
| 接口与成功判定 | PASS | Gate 直接输入已统一资格谓词与无评估 reason |
| 权限、四眼、持续鉴权 | PASS | 入口、恢复、consume、Connector/Tool 均有复核点 |
| 数据与模块写边界 | PASS | 私有仓储、命令回写、Worker 禁止直写均明确 |
| 受理幂等 | PASS | key + payload hash + 结果引用 |
| 并发/CAS/行锁 | PASS | Approval 唯一 execution intent 与崩溃恢复顺序已明确 |
| 未知外部结果 | PASS | external_request_id + 查询后重试 |
| 失败恢复与补偿 | PASS | 控制面、Worker、CI、Jira、Release、heal_apply 均有路径 |
| 迟到/乱序事件 | PASS | revision + CAS + 终态吸收 + divergence |
| AuditEvent 泄露与完整性 | PASS | 审计/日志/Trace 分离，秘密与正文限制明确 |
| Evidence 完整性 | PASS | append-only、稳定引用、租户授权与覆盖率均有定义 |
| tenant 全层隔离 | PASS | API、DB、队列、缓存、对象、向量、AI、恢复均覆盖 |
| Artifact 访问 | PASS（Draft） | 私有存储与混合访问候选明确，具体值仍 TBD |
| 向量泄露与删除传播 | PASS | 先授权后召回、再次鉴权、删除/恢复重放均覆盖 |
| 模型出站与日志泄露 | PASS | 四级分类、Restricted 拒绝/本地、Confidential 禁缓存 |
| 微服务过度引入 | PASS | 当前不采用全部微服务 |
| Temporal 过度引入 | PASS | 仅条件 POC，与保底同 Gate |
| LangGraph 越界 | PASS | 仅 Agent/Copilot 受限节点 |
| MCP 越界 | PASS | M0–M3 不采用；M4 只读 POC 候选 |
| 假设/TBD 成熟度 | PASS | 分册与前端规范均明确 Draft；ADR 均 Proposed |
| 三分册、研究、集成与 ADR 一致性 | PASS | H-01/H-02 已闭环 |
| 链接可达性 | PASS | 当前 Markdown 链接均可达；缺失 Prototype 仅以代码路径和公开缺口表示 |
| 相对路径与行号 | PASS（抽查） | 核心引用路径与当前行号可定位；陈旧内容本身已单列 finding |
| snake_case 文件名 | DEFERRED | 两个既有文件名不合规，见 L-01；已给接受理由与 Owner |
| Draft/Proposed 状态 | PASS | 架构正文/分册均 Draft；8 ADR 均 Proposed |

## 6. 剩余风险

1. **外部系统能力风险**：Release、Jira、GitHub、CI 是否支持按 request id 查询、幂等创建、ETag/revision、稳定 delivery id 仍待 contract test；能力不足时自动恢复必须降为人工接管。
2. **工作流选型风险**：Temporal 托管/自托管、Worker 版本、history/visibility、备份恢复、RPO/RTO、成本和值班能力均未实测；未通过 Gate 应使用保底方案。
3. **持续授权风险**：L2 自动动作的合格清单、scope、有效期、撤销传播和承载位置仍 Proposed；任何隐式永久豁免都会破坏 Policy Gate。
4. **身份权威风险**：ProjectMember 权威拆分、IdP claim、禁用传播、职能资格和撤权 SLA 仍 Proposed/TBD。
5. **数据治理风险**：Artifact TTL、扫描器、Restricted 查看方式、Legal Hold、WORM、删除传播和备份恢复策略尚未闭环。
6. **状态模型风险**：`agent_tool_action`/`perf_high_risk` 获批后执行失败时 TestRun 如何从 WAITING_APPROVAL 收敛仍未决定。
7. **跨阶段 UX 风险**：`docs/05_prototype/` 当前无资料，无法验证等待态、审批九要素、MCP 关闭态和技术 POC 标签是否被正确呈现。
8. **命名迁移风险**：两个既有前端相关文件名尚未符合 snake_case；后续变更必须一次性更新全部引用并重新跑链接检查。

## 7. 修订验收表

| Finding | 必须完成的修订 | 验收证据 | 当前状态 |
| --- | --- | --- | --- |
| H-01 | 定义 Approval consume → execution intent → Outbox → Worker attempt → EXECUTED 的唯一协议 | 当前文档协议 + 后续崩溃点/双 consume/响应丢失测试 | 文档修订通过；实现验证待后续阶段 |
| H-02 | 统一 GateEvaluation 资格谓词 | 边界规范、集成架构、Stage 7 输入逐项对照 | 通过 |
| M-01 | 删除固定边数并引用权威迁移契约 | 前端规范与边界规范一致性检查更新 | 通过 |
| M-02 | 把前端设计加入研究与集成输入追溯 | 输入清单和冲突登记 | 通过 |
| M-03 | 更新 Stage 6 README 和研究分册中的产出状态 | README 文件清单与当前工作树一一对应 | 通过 |
| M-04 | 统一文首 Status 与阶段措辞 | 所有分册文首状态抽查 | 通过 |
| M-05 | 清理或显式标记 Prototype 缺失链接 | 链接检查；Prototype Owner 公开缺口 | 链接通过；实质 UX 复核待 Prototype Owner |
| L-01 | 按变更流程重命名并更新引用 | 全仓相对链接检查 | 延后；Owner 与理由见 L-01 |

## 8. 是否建议该 Draft 进入用户评审

**审查建议：修订后的 Draft 可以进入用户评审。**

两项 High 和五项 Medium 的文档修订均已闭环；L-01 已给出不阻断架构语义的接受理由与 Owner。Stage 5 Prototype 缺失仍须作为明确限制随评审包披露；它阻断 Stage 5/6 UX 一致性确认，但不阻断后端架构 Draft 的用户评审。

该结论仅是独立审查建议，不代表架构状态发生变化；所有 ADR 继续保持 Proposed。
