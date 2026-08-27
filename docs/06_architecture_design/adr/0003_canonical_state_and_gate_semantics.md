# ADR 0003: Canonical State and Gate Semantics

- **Status: Proposed**
- **Date: 2026-08-26**

## Context

TestRun 的权威 10 态与四个终态已经在问题模型中定义，前端、Worker、运行时和外部回调都不得自行推演状态（`../../03_problem_modeling/problem_model.md:150`、`../../03_problem_modeling/problem_model.md:173`、`../02_api_workflow_and_review.md:293`、`../02_api_workflow_and_review.md:301`）。

当前仍有三个必须保持 Proposed 的冲突点：审批过期是否取消 TestRun；GateEvaluation 是否新增 `not_evaluated`；CANCELLED/TIMEOUT 是否有门禁评估资格。现有 GateEvaluation.result 只有 pass/fail/waived，而 PRD 要求阈值缺配不能默认通过（`../../03_problem_modeling/problem_model.md:253`、`../../08_prd/prd.md:134`）。

## Decision

1. **权威状态兼容规则：ApprovalRequest 过期只使请求进入 EXPIRED；关联 TestRun 保持 WAITING_APPROVAL。** 系统不得自动放行或自动转 CANCELLED，用户可重新提交审批或人工取消（`../../03_problem_modeling/problem_model.md:178`、`../../03_problem_modeling/problem_model.md:207`、`../02_api_workflow_and_review.md:318`、`../02_api_workflow_and_review.md:325`）。
2. **拒绝和人工取消与过期分开表达。** 只有拒绝/人工取消使用 WAITING_APPROVAL→CANCELLED；等待态不受心跳回收，但必须持续可见、告警并允许人工取消（`../../03_problem_modeling/problem_model.md:164`、`../../03_problem_modeling/problem_model.md:184`）。
3. **现阶段不扩展 GateEvaluation 枚举。** 在上游模型批准 `not_evaluated` 前，无法评估的 run 使用“无 GateEvaluation + 查询投影明确 reason”兼容；任何缺配、partial、CANCELLED 或 TIMEOUT 都不得默认 pass（`../01_domain_and_service_architecture.md:304`、`../01_domain_and_service_architecture.md:313`）。
4. **`not_evaluated` 是 Proposed 上游变更，不是已生效状态。** 候选变更是在后续为 script/external_ci 的 CANCELLED、TIMEOUT、阈值缺配和报告 partial 建不可变评估事实与 reason；获批前不得写入不存在的枚举值（`../01_domain_and_service_architecture.md:577`、`../01_domain_and_service_architecture.md:583`）。
5. **门禁资格与结果/分诊资格分离。** script/external_ci 的 SUCCEEDED/FAILED 且归一化完整、策略可评估时可生成 pass/fail；Agent run 不生成 GateEvaluation。CANCELLED/TIMEOUT 的已入库结果仍可归一化、分诊和追加 Evidence，但在上游变更前不生成 GateEvaluation（`../01_domain_and_service_architecture.md:308`、`../01_domain_and_service_architecture.md:313`、`../01_domain_and_service_architecture.md:435`、`../01_domain_and_service_architecture.md:440`）。
6. GateEvaluation 保持不可变；补到结果或重评估必须新建评估记录，不覆盖历史结论（`../../03_problem_modeling/problem_model.md:252`、`../../03_problem_modeling/problem_model.md:253`、`../01_domain_and_service_architecture.md:485`）。
7. 本 ADR 不新增状态、枚举或状态边；所有涉及上游变化的内容继续保持 Proposed，并须走上游变更流程（`../01_domain_and_service_architecture.md:31`、`../01_domain_and_service_architecture.md:43`）。

## Alternatives

1. **审批过期自动 CANCELLED**：易收敛，但会把“未获审批”误表达为“主动取消”，并改变最高优先级状态语义（`../01_domain_and_service_architecture.md:561`、`../01_domain_and_service_architecture.md:567`）。
2. **永久用 GateEvaluation 缄默缺失表示未评估**：无需模型变更，但无法区分“尚未评估”和“评估后不可判定”，审计与统计较弱（`../01_domain_and_service_architecture.md:581`、`../01_domain_and_service_architecture.md:583`）。
3. **把 CANCELLED/TIMEOUT 记为 fail**：看似 fail-closed，却混淆质量失败、人工取消和执行设施失联，不符合已有终态语义（`../../03_problem_modeling/problem_model.md:173`、`../../03_problem_modeling/problem_model.md:180`）。
4. **把无法评估默认 pass**：明确排除；这会静默放行并违背阈值缺配“未评估”要求（`../../08_prd/prd.md:134`、`../01_domain_and_service_architecture.md:551`）。

## Consequences

- 审批过期任务可能长期停留，因此工作台、列表、告警和人工处置成为强制能力（`../../08_prd/prd.md:148`、`../../08_prd/prd.md:158`）。
- 上游变更前，“无评估 + reason 投影”会增加查询和 Release 汇聚复杂度，但不会污染现有枚举（`../01_domain_and_service_architecture.md:581`、`../01_domain_and_service_architecture.md:583`）。
- CANCELLED/TIMEOUT 仍保留部分结果和证据价值，但不能被误用为质量门禁结论（`../01_domain_and_service_architecture.md:431`、`../01_domain_and_service_architecture.md:437`）。

## Security and Operations

- 前端、SSE、运行时和 Connector 都不能由本地进度或外部状态直接推导终态；GET/领域资源是权威事实（`../02_api_workflow_and_review.md:350`、`../02_api_workflow_and_review.md:357`）。
- 审批 TTL 与 TestRun 心跳分离，任何过期都不自动放行；TTL 和告警阈值数值保持 TBD（`../02_api_workflow_and_review.md:537`、`../02_api_workflow_and_review.md:543`）。
- 迟到结果不得重开终态；可追加 Artifact/Evidence 并标记 late，重新门禁必须通过显式新评估/新 run（`../01_domain_and_service_architecture.md:477`、`../01_domain_and_service_architecture.md:486`）。
- GateEvaluation、豁免和查询投影都需租户/RBAC 过滤并保留策略快照与审计关联（`../../03_problem_modeling/problem_model.md:103`、`../03_security_reliability_and_operations.md:108`）。

## Migration or Follow-up

1. 向问题模型发起 `not_evaluated + reason` 的正式变更提案，明确枚举、资格、Release 汇聚和历史兼容；获批前只使用兼容投影。
2. 清点仍写“审批过期→CANCELLED”的旧交互资料，按变更流程统一，不由本 ADR静默回写（`../01_domain_and_service_architecture.md:561`、`../01_domain_and_service_architecture.md:567`）。
3. Stage 7 契约需区分 TestRun 终态、GateEvaluation 存在性和 not-evaluated reason，但不得擅自新增业务枚举（`../02_api_workflow_and_review.md:774`、`../02_api_workflow_and_review.md:791`）。
4. 门禁 Owner 需决定 CANCELLED/TIMEOUT 在上游变更后的评估事实与 Release 展示口径。

## Verification

- 状态机属性测试覆盖非法边拒绝、终态吸收、审批过期保持 WAITING_APPROVAL、STOPPING→TIMEOUT（`../01_domain_and_service_architecture.md:646`、`../01_domain_and_service_architecture.md:648`）。
- 门禁测试覆盖 Agent 无评估、缺配/partial/CANCELLED/TIMEOUT 不默认通过、历史评估不可变（`../01_domain_and_service_architecture.md:654`）。
- 乱序/迟到测试证明终态不重开、后补结果只追加 Evidence，重评估创建新记录（`../01_domain_and_service_architecture.md:477`、`../01_domain_and_service_architecture.md:489`）。
- UI/SSE 测试证明等待态持续可见、事件与 GET 冲突时以后者为准（`../02_api_workflow_and_review.md:305`、`../02_api_workflow_and_review.md:325`、`../02_api_workflow_and_review.md:356`）。

## Open Questions

1. `not_evaluated` 是否获上游批准、reason 枚举和数据迁移策略均未决定（`../01_domain_and_service_architecture.md:629`、`../01_domain_and_service_architecture.md:631`）。
2. CANCELLED/TIMEOUT 的 partial 结果在 Release Readiness 中如何展示和阻断仍需产品/QA 决策。
3. `agent_tool_action` 或高危压测获批后执行失败，TestRun 如何从 WAITING_APPROVAL 合法收敛仍为 TBD（`../02_api_workflow_and_review.md:591`）。
4. 等待态告警阈值和重评估策略均为 TBD（`../01_domain_and_service_architecture.md:522`、`../01_domain_and_service_architecture.md:535`）。

## References

- `../../03_problem_modeling/problem_model.md:139`
- `../../03_problem_modeling/problem_model.md:175`
- `../../03_problem_modeling/problem_model.md:252`
- `../01_domain_and_service_architecture.md:304`
- `../01_domain_and_service_architecture.md:559`
- `../02_api_workflow_and_review.md:293`
