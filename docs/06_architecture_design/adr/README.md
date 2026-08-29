# Architecture Decision Records

- **Scope**: Stage 6 architecture decisions
- **Status: Mixed**（0001/0002 Accepted；0003–0008 Proposed）
- **Date: 2026-08-29**

## Status Guidance

`Accepted` 表示架构决策已经批准，可指导后续设计，但不自动批准依赖、部署、供应商、生产 Gate 或 TBD 数值。`Proposed` 表示候选决策仍需对应 Owner、架构、安全、SRE、法务或上游变更流程评审，**不得指导实现为最终定论**。

状态变更必须保留评审依据、验证证据和上游一致性；涉及已用于指导后续阶段的设计资产时，遵循变更流程（`../../00_setup/project_rules.md:130`、`../../00_setup/project_rules.md:133`）。

## Index

| ADR | 状态 | Subject | Primary dependencies |
| --- | --- | --- | --- |
| [0001](0001_modular_monolith_control_plane.md) | Accepted | 模块化单体控制面与独立 Worker | 0002、0004、0006、0007、0008 |
| [0002](0002_durable_workflow_runtime.md) | Accepted | Temporal 持久工作流、Outbox relay 与 Activity 边界 | 0001、0004、0006、0007 |
| [0003](0003_canonical_state_and_gate_semantics.md) | Proposed | 权威状态、审批过期与门禁资格语义 | 0001、0002、0004、0007 |
| [0004](0004_side_effect_approval_and_pre_authorization.md) | Proposed | L0–L4、副作用审批、Release prepare 与持续授权 | 0001、0003、0005、0006、0007 |
| [0005](0005_identity_tenancy_and_project_membership.md) | Proposed | 身份、租户与 ProjectMember 权威拆分 | 0001、0004、0007 |
| [0006](0006_connector_idempotency_and_recovery.md) | Proposed | Connector Contract、幂等与恢复 | 0001、0002、0004、0005、0007 |
| [0007](0007_data_artifact_and_audit_protection.md) | Proposed | 数据、Artifact、证据与审计保护 | 0001、0004、0005、0006、0008 |
| [0008](0008_agent_langgraph_and_mcp_boundaries.md) | Proposed | Agent、LangGraph 与 MCP 边界 | 0001、0002、0004、0005、0007 |

## Dependency Relationships

1. `0001` 定义运行单元和写入边界；`0002` 已选择 Temporal 并定义 Outbox relay、Workflow/Activity 边界，但不得改变 `0001` 的控制面权威性。
2. `0003` 定义业务状态与门禁的兼容语义；`0002`、`0004` 和 `0006` 只能传递命令、信号和观察，不得自行创造状态边。状态迁移以后端事实为准（`../02_api_workflow_and_review.md:51`、`../02_api_workflow_and_review.md:61`）。
3. `0004` 依赖 `0005` 的当前身份与授权、`0006` 的外部副作用可靠性，以及 `0007` 的审计和证据留痕；长流程恢复时持续复核当前授权（`../03_security_reliability_and_operations.md:84`、`../03_security_reliability_and_operations.md:96`）。
4. `0006` 的事件、回调和外部响应只形成观察或执行结果，最终由目标聚合命令裁决；回调不拥有平台状态机（`../01_domain_and_service_architecture.md:469`、`../01_domain_and_service_architecture.md:475`）。
5. `0008` 受 `0004` 的 Tool Router/Policy Gate 与 `0007` 的数据分级约束；LangGraph 和 MCP 都不得成为审批、授权或业务状态事实源（`../02_api_workflow_and_review.md:648`、`../02_api_workflow_and_review.md:655`、`../03_security_reliability_and_operations.md:449`、`../03_security_reliability_and_operations.md:461`）。

## Reading and Review Rules

- 每份 ADR 固定使用 `Context / Decision / Alternatives / Consequences / Security and Operations / Migration or Follow-up / Verification / Open Questions / References` 结构。
- `Decision` 的约束力由该 ADR 自身状态决定；Accepted 可指导设计但不等于生产授权，Proposed 仍是待评审候选。带冲突或上游枚举变化的事项必须先完成上游变更。
- `TBD` 不得被实现者替换成隐式默认值。新分册明确所有 timeout、retry、retention 与队列数值仍为 TBD（`../03_security_reliability_and_operations.md:429`、`../03_security_reliability_and_operations.md:435`）。
- 本目录不提供代码、DDL、迁移、依赖或部署配置；实现契约由后续阶段在相应决策获得批准后另行产出。
