# ADR 0004: Side-effect Approval and Pre-authorization

- **Status: Proposed**
- **Date: 2026-08-26**

## Context

平台要求所有工具、Skill 和 Connector Action 声明 L0–L4 副作用等级，由 Policy Gate 输出 ALLOW、DENY、REQUIRE_APPROVAL 或 REQUIRE_REAUTH；未声明等级的动作默认拒绝（`../../08_prd/prd.md:101`、`../../08_prd/prd.md:111`）。等级语义为 L0 只读、L1 平台内草稿、L2 外部系统非生产写、L3 正式测试或变更、L4 生产发布/邮件/删除域（`../../README.md:335`）。

当前冲突集中在 Release prepare 的 L3/L4 表述，以及 CI trigger、Check Run 等系统动作如何既保持自动化又不绕过 L2/L3 审批原则（`../01_domain_and_service_architecture.md:569`、`../01_domain_and_service_architecture.md:587`）。

## Decision

1. **Proposed：所有动作必须注册 sideEffectLevel 和动作契约。** 未声明动作或白名单外目标直接 DENY；审批不能把禁止动作变成允许动作（`../02_api_workflow_and_review.md:282`、`../02_api_workflow_and_review.md:287`）。
2. **Proposed 裁决基线**：L0 默认可允许；L1 可允许但必须可追溯；L2/L3 默认进入审批；L3+ 在会话超过再认证窗口或资源要求强认证时先 REQUIRE_REAUTH；L4 实际生产发布/删除等动作保持 DENY 或只生成草稿（`../../README.md:335`、`../../08_prd/prd.md:111`）。具体再认证窗口为 TBD（`../03_security_reliability_and_operations.md:78`、`../03_security_reliability_and_operations.md:82`）。
3. **Release prepare 保持 Proposed 的 L4 风险域兼容口径。** `release_push` 沿用问题模型中的 L4 标记，但平台只允许“prepare item”；Policy Gate 要求再认证、四眼、参数哈希和幂等。实际生产发布执行不存在或恒 DENY，不能因 L4 标签推导平台具有发布权（`../../03_problem_modeling/problem_model.md:220`、`../01_domain_and_service_architecture.md:569`、`../01_domain_and_service_architecture.md:575`）。
4. **Proposed：系统自动 L2 动作使用作用域化持续授权，而非静默豁免。** 注册审批可形成版本化的预授权/持续授权元数据；至少绑定 tenant、project、connector action、目标资源、触发来源、最大等级、配置版本、有效期和撤销状态。每次动作仍通过 Policy Gate，并关联原审批和当前授权版本写审计（`../01_domain_and_service_architecture.md:585`、`../01_domain_and_service_architecture.md:591`）。
5. 持续授权不是永久授权：入口、队列消费、工作流恢复、审批 consume、Connector 调用和 Tool 调用都必须复核当前成员、职能资格、目标、参数、有效期、撤销和 kill switch（`../03_security_reliability_and_operations.md:84`、`../03_security_reliability_and_operations.md:96`）。
6. 单次 ApprovalRequest 绑定服务端 Preview 的完整参数哈希、九要素、发起人和目标版本；四眼、权限、哈希和目标版本在批准与消费时重校验，批准只可消费一次（`../../03_problem_modeling/problem_model.md:193`、`../../03_problem_modeling/problem_model.md:199`、`../02_api_workflow_and_review.md:500`、`../02_api_workflow_and_review.md:514`）。
7. `APPROVED` 只表示人已批准。消费事务必须在行锁内原子创建以 `approval_request_id + bound_hash` 唯一标识的基础设施执行意图与 Outbox；重复消费返回同一执行引用，不创建第二个意图，也不提前写 EXECUTED。该意图不是新领域对象。
8. execution intent 至少区分 `READY / CLAIMED / DISPATCHING / CONFIRMED_OK / CONFIRMED_FAILED / UNKNOWN / ABANDONED`。Worker 在网络调用前持久化 DISPATCHING，使用稳定外部幂等键调用；首次真实调用已发出后，由控制面写 `EXECUTED + execution_result=ok/failed/unknown`。READY/CLAIMED 崩溃可重领；DISPATCHING/UNKNOWN 或落账前崩溃先查询 external_request_id/幂等结果；unknown 不得按失败盲重试或按成功放行（`../02_api_workflow_and_review.md:226`、`../02_api_workflow_and_review.md:235`、`../02_api_workflow_and_review.md:553`、`../02_api_workflow_and_review.md:560`）。
9. 本 ADR 不批准持续授权的有效期、再认证窗口、自动动作清单或新领域对象；这些均保持 TBD/Proposed，且不得将预授权实现成绕过 ApprovalRequest 的隐藏通道（`../01_domain_and_service_architecture.md:522`、`../01_domain_and_service_architecture.md:524`）。

## Alternatives

1. **所有 L2 动作逐次审批**：语义最严格，但会阻塞无人值守 CI、扩大审批队列并增加延迟（`../01_domain_and_service_architecture.md:589`、`../01_domain_and_service_architecture.md:591`）。
2. **自动系统动作永久豁免 Policy Gate**：明确拒绝；配置、成员和风险变化后仍可继续写外部系统，无法满足持续授权复核。
3. **把 Release prepare 降为 L3**：规则更简单，但需先统一修改上游冻结等级，并容易混淆 prepare 与 execute（`../01_domain_and_service_architecture.md:573`、`../01_domain_and_service_architecture.md:575`）。
4. **把 APPROVED 当执行成功**：明确拒绝；审批与副作用结果是不同事实（`../02_api_workflow_and_review.md:228`、`../02_api_workflow_and_review.md:235`）。

## Consequences

- 自动 CI 可在受控 scope 内运行，同时保留撤销、版本、归因和每次 Policy Gate；代价是需要授权生命周期、对账和告警。
- Release prepare 的 L4 风险域口径较保守，可能增加操作摩擦，但避免平台越界执行生产发布（`../03_security_reliability_and_operations.md:98`、`../03_security_reliability_and_operations.md:104`）。
- 审批、再认证、持续授权、幂等键和 ETag 各解决不同问题，不能互相替代（`../02_api_workflow_and_review.md:183`、`../02_api_workflow_and_review.md:193`）。

## Security and Operations

- 四眼原则在候选人路由、审批提交和执行前复核三处强制；重新提交以新提交人为 initiator，并保留原归因链（`../02_api_workflow_and_review.md:518`、`../02_api_workflow_and_review.md:524`、`../02_api_workflow_and_review.md:545`、`../02_api_workflow_and_review.md:551`）。
- 参数、权限、目标版本、持续授权版本或 kill switch 变化一律 fail-close，使旧批准失效（`../03_security_reliability_and_operations.md:98`、`../03_security_reliability_and_operations.md:103`）。
- 关停是收紧控制，可即时生效；恢复属于 L3 审批，避免事故响应被审批阻塞（`../../03_problem_modeling/problem_model.md:218`、`../../08_prd/prd.md:347`）。
- AuditEvent 至少记录 actor/delegated_agent、tenant/project、动作、等级、Policy 决策、审批与 bound hash、持续授权版本、external_request_id、结果和 Evidence 引用（`../../01_market_research/market_research.md:120`、`../../01_market_research/market_research.md:123`）。

## Migration or Follow-up

1. 将持续授权关系提交上游评审，决定作为 Connector/ExecutionEnvironment 版本化治理元数据还是新增对象；未获批准前不得暗增第 24 个领域对象（`../01_domain_and_service_architecture.md:589`）。
2. 收口动作注册表：级别、Preview、审批/再认证、幂等、补偿、目标白名单和持续授权资格。
3. 统一 Release prepare 命名和文案，避免出现“平台执行发布”的含义；若要改为 L3，必须走上游变更。
4. 由安全、集成 Owner 定义 scope、有效期、撤销传播和复核周期；所有数值保持 TBD（`../01_domain_and_service_architecture.md:631`）。
5. 由审批与集成 Owner 在实现契约中冻结已接受的 execution intent 状态、唯一键、领取租约、调用前/后崩溃恢复和人工接管协议；若需要新增其他业务字段或状态，先走上游变更。

## Verification

- 策略表测试覆盖 L0–L4、未声明动作、白名单外目标、L3+ 再认证和 L4 实际发布 DENY（`../../08_prd/prd.md:111`、`../03_security_reliability_and_operations.md:529`）。
- 并发与崩溃点测试证明 ApprovalRequest 双 consume 只产生一个 execution intent；调用前/后崩溃、响应丢失、Outbox/Activity 重投和人工重提不会产生第二个外部效果；无法确认时稳定收敛为 unknown 并阻断自动放行，参数/权限/版本变化使审批失效。
- 撤销/过期测试证明旧持续授权在队列恢复和 Connector 调用前被拒绝（`../03_security_reliability_and_operations.md:528`）。
- Release 测试证明只能 prepare、可幂等对账，任何实际生产发布请求均被拒绝（`../03_security_reliability_and_operations.md:533`、`../03_security_reliability_and_operations.md:534`）。
- 审计测试证明拒绝、审批、消费成功/失败和自动授权动作均可追溯（`../02_api_workflow_and_review.md:700`、`../02_api_workflow_and_review.md:713`）。

## Open Questions

1. 持续授权是现有对象元数据还是独立领域对象，尚未决定。
2. 哪些 L2 系统动作有资格使用持续授权，以及 scope、有效期和撤销时效均为 TBD（`../01_domain_and_service_architecture.md:631`）。
3. Release prepare 的上游 L3/L4 冲突尚未正式消除，本 ADR 只给 Proposed 兼容口径。
4. Approval TTL、升级、再认证窗口和执行失败后的 TestRun 收敛均为 TBD（`../02_api_workflow_and_review.md:761`、`../02_api_workflow_and_review.md:762`）。

## References

- `../../README.md:335`
- `../../03_problem_modeling/problem_model.md:188`
- `../../03_problem_modeling/problem_model.md:209`
- `../../08_prd/prd.md:107`
- `../01_domain_and_service_architecture.md:569`
- `../01_domain_and_service_architecture.md:585`
