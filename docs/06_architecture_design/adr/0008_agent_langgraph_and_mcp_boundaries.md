# ADR 0008: Agent, LangGraph, and MCP Boundaries

- **Status: Proposed**
- **Date: 2026-08-26**

## Context

Agent Mode 允许受限动态执行，但结果不进入门禁；每个动作都必须经过 Tool Router 与 Policy Gate，越权调用要被阻断并保留轨迹（`../../08_prd/prd.md:129`、`../../03_problem_modeling/problem_model.md:98`、`../../03_problem_modeling/problem_model.md:104`）。

LangGraph 适合 Agent/Copilot 的受限推理循环或 interrupt bridge，但不能取代 TestRun、ApprovalRequest 或持久工作流。MCP 一期不对外暴露，M4 才评估（`../../01_market_research/market_research.md:137`、`../../08_prd/prd.md:73`、`../../08_prd/prd.md:303`）。

## Decision

1. **Proposed：LangGraph 仅限 Agent/Copilot 受限推理循环和 interrupt bridge 候选。** 它可以保存可恢复上下文引用并在审批结果后恢复 Agent 节点，但不能决定 ApprovalRequest/TestRun 状态、权限、重试、幂等或业务补偿（`../02_api_workflow_and_review.md:635`、`../02_api_workflow_and_review.md:646`、`../03_security_reliability_and_operations.md:437`、`../03_security_reliability_and_operations.md:447`）。
2. LangGraph checkpoint 不是审批或业务事实源；ApprovalRequest、param_hash、四眼、TTL、当前权限和目标版本全部由后端持久事实裁决，恢复前重新读取和验证（`../02_api_workflow_and_review.md:639`、`../02_api_workflow_and_review.md:655`）。
3. Agent/Copilot 只可调用服务端注册且版本化的工具；每步经过 schema 校验、tenant/RBAC、Tool Router、Policy Gate、数据分级和审计。模型生成的工具名、参数、URL、资源 ID 和“已获批准”声明一律不可信（`../03_security_reliability_and_operations.md:208`、`../03_security_reliability_and_operations.md:214`、`../03_security_reliability_and_operations.md:441`、`../03_security_reliability_and_operations.md:447`）。
4. Agent Mode 内默认工具上限为 L1；L2+ 工具动作单独进入 ADR 0004 的审批路径。超步/总超时主动终止保存 incomplete 轨迹，不自动重试；进程失联由心跳收敛 TIMEOUT（`../../08_prd/prd.md:129`、`../../08_prd/prd.md:154`、`../../08_prd/prd.md:155`）。
5. Agent 输出、轨迹和建议不能直接成为门禁或发布证据结论；只有人工确认后固化为 Script 资产并执行确定性 run，才进入相应门禁链（`../../08_prd/prd.md:129`、`../01_domain_and_service_architecture.md:29`、`../01_domain_and_service_architecture.md:134`）。
6. **Proposed MCP 分期边界：M0、M1、M2、M3 不采用 MCP；M4 只允许只读 POC 候选。** POC 必须限定试点 tenant、只读工具、严格 schema、RBAC/tenant 双重校验、全审计、kill switch 和无外部写（`../02_api_workflow_and_review.md:663`、`../02_api_workflow_and_review.md:680`）。
7. M4 只读 POC 在权限、注入、审计、成本、稳定性、协议/SDK 供应链和退出标准通过前不得实施为正式能力；当前外部 MCP Server/Client 默认禁用（`../03_security_reliability_and_operations.md:449`、`../03_security_reliability_and_operations.md:461`）。
8. MCP transport 不是信任证明；未来任何 server/tool/version/auth/egress/数据等级都需注册和审批，远程描述与结果按不可信内容处理。MCP 不得替代 Connector Contract、Tool Router 或 ApprovalRequest（`../03_security_reliability_and_operations.md:453`、`../03_security_reliability_and_operations.md:461`）。
9. 本 ADR 不声称 LangGraph/MCP POC 已完成，不批准任何 SDK/依赖、协议版本、checkpoint 存储、数值或供应商。

## Alternatives

1. **LangGraph 作为平台工作流引擎**：明确拒绝；普通 TestRun、外部 CI、导入和报告已有领域状态与持久恢复要求，LangGraph 不应成为业务控制面（`../02_api_workflow_and_review.md:648`、`../02_api_workflow_and_review.md:655`）。
2. **LangGraph interrupt 直接作为审批**：明确拒绝；会绕过九要素、四眼、TTL、行锁、租户和审计事实（`../02_api_workflow_and_review.md:650`、`../02_api_workflow_and_review.md:655`）。
3. **M0–M3 提前采用 MCP**：明确拒绝；一期范围明确不做对外暴露，内部 Tool Router/Connector 足以支撑当前能力（`../../08_prd/prd.md:73`、`../02_api_workflow_and_review.md:672`、`../02_api_workflow_and_review.md:678`）。
4. **M4 开放 MCP 写工具**：不在当前候选范围；只读 POC 通过后也需要新的威胁建模和 ADR。
5. **完全不使用 Agent/LangGraph**：可降低风险，但会放弃受限探索执行和 Copilot 候选价值；保留为 POC 失败或运维成本过高时的 fallback。

## Consequences

- Agent 能提供受限动态能力，而状态机、审批、租户和副作用仍由确定性平台掌控；代价是 bridge、checkpoint、工具注册和双层可观测复杂度。
- M0–M3 不采用 MCP 可减少供应链、注入和授权面；M4 只读 POC 推迟生态验证，但避免早期协议能力侵入核心控制面。
- Agent 结果不进门禁会限制短期自动化覆盖，但避免把非确定性探索直接变成发布证据（`../../03_problem_modeling/problem_model.md:104`）。

## Security and Operations

- SkillVersion manifest 必须声明 allowedTools、max_steps、超时、sideEffectLevel 和 modelPolicy，并经版本化发布 Gate；未注册工具默认 DENY（`../03_security_reliability_and_operations.md:441`、`../03_security_reliability_and_operations.md:446`）。
- checkpoint/会话若持久化，继承 tenant、classification、保留、删除和加密策略；不得保存 secret 或 Restricted 原文（`../03_security_reliability_and_operations.md:443`、`../03_security_reliability_and_operations.md:445`）。
- Jira、日志、网页 DOM、MCP description/result 等全部视为不可信数据；任何高风险工具不能因模型文本而放行（`../03_security_reliability_and_operations.md:208`、`../03_security_reliability_and_operations.md:215`）。
- MCP POC 需要 server/tool allowlist、egress 限制、结果大小、超时、并发、递归深度和 kill switch；数值与实现均为 TBD（`../03_security_reliability_and_operations.md:455`、`../03_security_reliability_and_operations.md:461`）。

## Migration or Follow-up

1. Agent/LangGraph 技术评审需定义 checkpoint 存储、加密、恢复、租户清理和故障语义；不改变业务状态机。
2. 建立 Agent 工具注册、SkillVersion 发布、注入测试、轨迹留存和转 Script 人工确认流程。
3. M4 前单独评审 MCP POC 的工具白名单、试点 tenant、退出标准、协议/SDK 审计和数据处理；未批准保持禁用（`../02_api_workflow_and_review.md:768`、`../02_api_workflow_and_review.md:769`）。
4. 若将来需要 MCP 写工具，必须新建决策并依赖 ADR 0004/0006；本 ADR 不预先授权。

## Verification

- Agent 测试证明白名单外工具、越权资源、恶意参数和模型伪造批准均被拒绝；越权副作用必须全部阻断（`../03_security_reliability_and_operations.md:533`）。
- 测试超步、总超时、进程失联和持久终止信号，证明轨迹保存 incomplete 且无自动重试（`../../08_prd/prd.md:129`、`../../08_prd/prd.md:154`）。
- 检查所有 Agent 调用存在 AIInvocationLog、schema/evidence 校验和数据分级；Restricted 路径被拒绝或仅进入经批准本地路由（`../01_domain_and_service_architecture.md:653`、`../03_security_reliability_and_operations.md:532`）。
- M0–M3 配置/能力测试证明 MCP 保持禁用；M4 POC 若获批，须通过恶意 server/tool description、跨租户、递归、egress、审计和 kill switch 测试（`../03_security_reliability_and_operations.md:533`）。
- 状态测试证明 LangGraph checkpoint 丢失/重放不会直接改变 ApprovalRequest 或 TestRun（`../02_api_workflow_and_review.md:648`、`../02_api_workflow_and_review.md:655`）。

## Open Questions

1. 是否采用 LangGraph、checkpoint 存储/加密/清理、恢复 SLO 和成本均未决定（`../02_api_workflow_and_review.md:768`）。
2. Agent 工具白名单、每类任务 max_steps/timeout 和模型路由数值均为 TBD（`../01_domain_and_service_architecture.md:533`、`../01_domain_and_service_architecture.md:534`）。
3. M4 是否实际开展只读 MCP POC、试点 tenant、工具白名单和退出标准均为 TBD（`../02_api_workflow_and_review.md:769`）。
4. MCP SDK、协议版本、供应链、托管方式和运维 Owner 尚未评审（`../03_security_reliability_and_operations.md:461`）。

## References

- `../../01_market_research/market_research.md:134`
- `../../03_problem_modeling/problem_model.md:95`
- `../../08_prd/prd.md:129`
- `../02_api_workflow_and_review.md:635`
- `../02_api_workflow_and_review.md:663`
- `../03_security_reliability_and_operations.md:437`
