# 06_architecture_design — 系统架构设计

> - **Status: Draft**（目录整体未全部定稿；[architecture.md](architecture.md) 已于 2026-08-27 定稿，[tech_stack_decision-v1.0.md](tech_stack_decision-v1.0.md) 已于 2026-08-29 冻结）
> - **阶段**：Stage 6 · 系统架构设计
> - **状态纪律**：[architecture.md](architecture.md) 为已定稿集成正文，[tech_stack_decision-v1.0.md](tech_stack_decision-v1.0.md) 为已冻结技术栈分册；00–04 分册与两份前端规范仍为 Draft；ADR 0001/0002/0009 为 Accepted，0003–0008 为 Proposed。Temporal 选型已接受且技术栈已冻结，但生产 Gate、托管方式、部署参数和 TBD 数值不因此自动批准；M2+ 组件（Temporal / Redis / MinIO / Vault）的启用另有硬前置条件，见 ADR 0009。
> - **范围**：登记当前实际存在的前端设计、前后端边界、技术栈冻结、后端研究与专题分册、独立审查、集成架构和 ADR。目录结构、生产 Gate 及 TBD 数值仍需后续评审和验证。

## 当前产出

| 文件 | 状态 | 职责 |
| --- | --- | --- |
| [00_research_and_input_traceability.md](00_research_and_input_traceability.md) | Draft | 登记实际输入、可追溯事实、官方技术结论、输入缺口以及 LangGraph、Temporal、MCP 的采用边界；其 Temporal POC 表述已由 Accepted ADR 0002 收口。 |
| [01_domain_and_service_architecture.md](01_domain_and_service_architecture.md) | Draft | 定义 23 个领域对象的模块归属、控制面与 Worker 边界、聚合事务、命令/事件、幂等、恢复、补偿和迟到事件。 |
| [02_api_workflow_and_review.md](02_api_workflow_and_review.md) | Draft | 定义 API 语义、同步/异步、SSE、ApprovalRequest、外部 CI、Artifact 访问及 LangGraph/MCP 评审边界；作为 Stage 7 契约输入。 |
| [03_security_reliability_and_operations.md](03_security_reliability_and_operations.md) | Draft | 定义信任边界、身份/租户、数据与模型安全、Connector、容量/SLO、备份恢复、可观测、事故响应和运维 Gate。 |
| [04_architecture_review.md](04_architecture_review.md) | Draft | Agent D 的独立 finding-first 架构审查、追溯矩阵、遗漏检查、剩余风险和修订验收；审查意见不构成批准。 |
| [architecture.md](architecture.md) | 已定稿 | 集成上述分册与 ADR 的唯一后端架构推荐，收口模块化单体控制面、Temporal、独立 Activity Worker、状态/门禁、审批、数据和安全边界。修订须走 `docs/13_changes/`。 |
| [architecture_diagram.drawio](architecture_diagram.drawio) | 已生成 | 与 `architecture.md` 对应的可编辑 draw.io 架构图；含“系统上下文”和“概念运行时拓扑”两个页面，不引入新的架构结论。 |
| [architecture_diagram.svg](architecture_diagram.svg) | 已生成 | “系统上下文”页面的 SVG 预览。 |
| [architecture_runtime_topology.svg](architecture_runtime_topology.svg) | 已生成 | “概念运行时拓扑”页面的 SVG 预览。 |
| [frontend_design_spec-v1.0.md](frontend_design_spec-v1.0.md) | Draft | 现有前端设计规范：P01–P25、路由、页面状态、跳转、核心交互和响应式约定；Stage 5 Prototype 当前缺失已显式标注。 |
| [frontend_backend_boundary_spec-v1.0.md](frontend_backend_boundary_spec-v1.0.md) | Draft | 现有前后端功能边界规范：后端权威、功能/数据/逻辑归属、API 调用、成功判定和错误边界；作为 Stage 7 直接输入。 |
| [tech_stack_decision-v1.0.md](tech_stack_decision-v1.0.md) | 已冻结 | 技术栈冻结分册：前端框架 / UI 组件 / 状态管理 / 后端框架 / ORM / API 风格 / 测试框架 / 构建部署八类选型与锁定版本，含 License、维护活跃度、逐版本 CVE 结论、分期启用矩阵、不采纳清单与独立运维自评。承接 `architecture.md` §2.3 声明的依赖/部署缺口。修订须走 `docs/13_changes/`。 |
| [adr/README.md](adr/README.md) | Mixed | ADR 索引、依赖关系和状态规则；0001/0002/0009 Accepted，0003–0008 Proposed。 |

## ADR 目录

`adr/` 当前包含 3 份 Accepted 决策和 6 份 Proposed 决策候选：

1. 模块化单体控制面与独立 Worker；
2. Temporal 持久工作流、Outbox relay 与 Activity 边界；
3. 权威状态与门禁语义；
4. 副作用审批、Release prepare 与持续授权；
5. 身份、租户与 ProjectMember 权威；
6. Connector 幂等与恢复；
7. 数据、Artifact、Evidence 与 Audit 保护；
8. Agent、LangGraph 与 MCP 边界；
9. 技术栈冻结与基础设施分期启用。

ADR 0001/0002/0009 已可指导后续设计；托管方式、部署参数和放量仍须独立 Gate。其余 ADR 的状态提升必须附上评审、验证和上游一致性证据。
