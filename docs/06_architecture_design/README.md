# 06_architecture_design — 系统架构设计

> - **Status: Draft**
> - **阶段**：Stage 6 · 系统架构设计
> - **状态纪律**：本目录所有架构正文与分册均为 Draft，ADR 均为 Proposed；当前没有文件被标记为已批准、已冻结或已定稿。
> - **范围**：登记当前实际存在的前端设计、前后端边界、后端研究与专题分册、独立审查、集成架构和决策候选。具体运行时、依赖、部署、目录结构及 TBD 数值仍需后续评审或 POC。

## 当前产出

| 文件 | 状态 | 职责 |
| --- | --- | --- |
| [00_research_and_input_traceability.md](00_research_and_input_traceability.md) | Draft | 登记实际输入、可追溯事实、官方技术结论、输入缺口以及 LangGraph、Temporal、MCP 的采用边界与 POC Gate。 |
| [01_domain_and_service_architecture.md](01_domain_and_service_architecture.md) | Draft | 定义 23 个领域对象的模块归属、控制面与 Worker 边界、聚合事务、命令/事件、幂等、恢复、补偿和迟到事件。 |
| [02_api_workflow_and_review.md](02_api_workflow_and_review.md) | Draft | 定义 API 语义、同步/异步、SSE、ApprovalRequest、外部 CI、Artifact 访问及 LangGraph/MCP 评审边界；作为 Stage 7 契约输入。 |
| [03_security_reliability_and_operations.md](03_security_reliability_and_operations.md) | Draft | 定义信任边界、身份/租户、数据与模型安全、Connector、容量/SLO、备份恢复、可观测、事故响应和运维 Gate。 |
| [04_architecture_review.md](04_architecture_review.md) | Draft | Agent D 的独立 finding-first 架构审查、追溯矩阵、遗漏检查、剩余风险和修订验收；审查意见不构成批准。 |
| [architecture.md](architecture.md) | Draft | 集成上述分册与 ADR 的唯一后端架构推荐，收口模块化单体控制面、独立 Worker、状态/门禁、审批、数据、安全和技术 POC 边界。 |
| [frontend_design_spec-v1.0.md](frontend_design_spec-v1.0.md) | Draft | 现有前端设计规范：P01–P25、路由、页面状态、跳转、核心交互和响应式约定；Stage 5 Prototype 当前缺失已显式标注。 |
| [frontend_backend_boundary_spec-v1.0.md](frontend_backend_boundary_spec-v1.0.md) | Draft | 现有前后端功能边界规范：后端权威、功能/数据/逻辑归属、API 调用、成功判定和错误边界；作为 Stage 7 直接输入。 |
| [adr/README.md](adr/README.md) | Proposed | ADR 索引、依赖关系和状态规则；[0001–0008](adr/README.md#index) 全部保持 Proposed。 |

## ADR 目录

`adr/` 当前包含 8 份 Proposed 决策候选：

1. 模块化单体控制面与独立 Worker；
2. 持久工作流运行时条件 POC；
3. 权威状态与门禁语义；
4. 副作用审批、Release prepare 与持续授权；
5. 身份、租户与 ProjectMember 权威；
6. Connector 幂等与恢复；
7. 数据、Artifact、Evidence 与 Audit 保护；
8. Agent、LangGraph 与 MCP 边界。

所有 ADR 的状态提升都必须附上评审、验证、POC（适用时）和上游一致性证据；当前不得据此宣称实现选型或生产授权已经完成。
