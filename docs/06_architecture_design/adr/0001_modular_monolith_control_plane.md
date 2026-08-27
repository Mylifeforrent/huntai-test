# ADR 0001: Modular Monolith Control Plane and Independent Workers

- **Status: Proposed**
- **Date: 2026-08-26**

## Context

HuntAI Test 需要同时承载同步治理、长时间等待、异构执行、外部连接器、报告处理和 AI 调用。上游要求治理面与执行面分离，平台执行器还必须独立于 API 进程（`../01_domain_and_service_architecture.md:47`、`../01_domain_and_service_architecture.md:49`）。

当前领域模型包含紧密关联的租户、测试资产、TestRun、审批、门禁、Release、Connector、证据和 AI 治理对象；其写权限需要明确归属，且前端、Worker 与外部系统都不能绕过后端裁决（`../01_domain_and_service_architecture.md:138`、`../01_domain_and_service_architecture.md:151`、`../01_domain_and_service_architecture.md:198`）。

## Decision

1. **Proposed：同步控制面采用模块化单体。** 控制面拥有认证/租户、RBAC、同步命令与查询、Policy Gate、领域状态机、聚合事务、Outbox 和工作台投影；模块以私有写模型和公开命令/查询/事件边界隔离（`../01_domain_and_service_architecture.md:81`、`../01_domain_and_service_architecture.md:83`、`../01_domain_and_service_architecture.md:128`、`../01_domain_and_service_architecture.md:130`）。
2. **Proposed：持久工作流、执行器、连接器、报告和 AI 作为独立 Worker 运行。** Worker 可独立扩展和故障隔离，但不能获得业务状态裁决权（`../01_domain_and_service_architecture.md:84`、`../01_domain_and_service_architecture.md:88`）。
3. Worker 回写控制面的唯一业务路径是已登记命令；跨模块通知使用已登记事件。Worker 禁止直接更新模块私有数据，事件也只能陈述已提交事实（`../01_domain_and_service_architecture.md:90`、`../01_domain_and_service_architecture.md:380`、`../01_domain_and_service_architecture.md:382`）。
4. **Proposed 起步形态**为一个事务数据库集群、模块私有 schema/仓储；共享数据库不表示共享表。跨模块使用 ID、不可变快照、查询端口和事件，不共享 ORM 实体或仓储（`../01_domain_and_service_architecture.md:92`、`../01_domain_and_service_architecture.md:97`、`../01_domain_and_service_architecture.md:198`）。
5. Redis 只可作缓存、限流、短租约或调度提示，不得成为工作流、审批、终止信号或幂等记录的唯一事实源（`../01_domain_and_service_architecture.md:94`、`../01_domain_and_service_architecture.md:95`）。
6. 本 ADR 不决定 Worker 的编排产品、消息产品、进程数量、扩缩容数值或部署拓扑；持久工作流运行时由 ADR 0002 条件评审，当前不存在已选定产品（`../03_security_reliability_and_operations.md:414`、`../03_security_reliability_and_operations.md:416`）。

## Alternatives

1. **全部微服务**：可提供更强独立发布和容量隔离，但会在领域冲突尚未收口时提前引入分布式事务、事件版本和运维成本（`../01_domain_and_service_architecture.md:101`、`../01_domain_and_service_architecture.md:105`）。
2. **单进程单体包含全部任务**：运行单元最少，但执行、轮询、报告和 AI 会争抢 API 资源，且不满足独立执行器与持久恢复要求（`../01_domain_and_service_architecture.md:103`、`../01_domain_and_service_architecture.md:105`）。
3. **立即采用托管持久工作流引擎**：只有 POC 证明可恢复、可升级且团队可运维后才可选择；当前不能把某个引擎当作既定基础设施（`../01_domain_and_service_architecture.md:106`）。

## Consequences

- 优点：聚合事务、租户和策略治理集中；执行、连接器、报告和 AI 可隔离扩缩；架构与当前内部规模相称（`../01_domain_and_service_architecture.md:101`、`../01_domain_and_service_architecture.md:104`）。
- 代价：必须持续防止模块跨仓储写入、循环依赖和“共享数据库即共享所有表”的退化（`../01_domain_and_service_architecture.md:542`、`../01_domain_and_service_architecture.md:547`）。
- 长任务、跨模块事务和外部副作用改为最终一致；正确性依赖幂等命令、Outbox/Inbox、持久检查点和人工接管，而不是跨模块分布式事务（`../01_domain_and_service_architecture.md:97`、`../01_domain_and_service_architecture.md:462`、`../01_domain_and_service_architecture.md:467`）。

## Security and Operations

- 每个请求、消息、Worker 消费和控制面命令都必须携带可信租户上下文并在执行点复核；无租户上下文拒绝（`../03_security_reliability_and_operations.md:106`、`../03_security_reliability_and_operations.md:116`）。
- Worker 使用服务身份和最小权限，不得拥有跨模块通用写权限；控制面数据库不可用时副作用应 fail-close，不得退化为无审计写入（`../03_security_reliability_and_operations.md:320`、`../03_security_reliability_and_operations.md:328`）。
- 关键链路要关联 request、workflow、run、approval、connector 和 trace，但日志与 Trace 不得承载秘密或敏感正文（`../03_security_reliability_and_operations.md:345`、`../03_security_reliability_and_operations.md:355`）。
- 所有实例数、队列容量、心跳、超时、重试和恢复目标均为 TBD，不在本 ADR 中给默认值（`../01_domain_and_service_architecture.md:516`、`../01_domain_and_service_architecture.md:538`）。

## Migration or Follow-up

1. 在后续设计中定义模块依赖规则、公开命令/查询/事件目录和私有仓储边界；不得先生成实现结构再反推边界（`../01_domain_and_service_architecture.md:183`、`../01_domain_and_service_architecture.md:198`）。
2. 通过 ADR 0002 收口持久工作流候选；通过 ADR 0006 收口消息与连接器恢复；通过 ADR 0007 收口 Artifact/Audit 数据边界。
3. 若未来拆微服务，必须以稳定团队边界、独立 SLO/容量和成熟事件治理为前置证据，而不是仅因模块数量增加（`../01_domain_and_service_architecture.md:101`、`../01_domain_and_service_architecture.md:104`）。

## Verification

- 架构依赖测试证明模块不能引用其他模块私有仓储/ORM，Worker 不能直写控制面表（`../01_domain_and_service_architecture.md:642`、`../01_domain_and_service_architecture.md:647`）。
- 重启与重复投递测试证明控制面/Worker 恢复不会重复外部副作用（`../01_domain_and_service_architecture.md:648`、`../03_security_reliability_and_operations.md:535`）。
- 双租户测试覆盖 API、队列、Worker、对象存储、审计和恢复路径（`../03_security_reliability_and_operations.md:524`、`../03_security_reliability_and_operations.md:528`）。
- 大报告和 AI 网关故障测试证明解析/AI 负载不拖垮控制面确定性功能（`../01_domain_and_service_architecture.md:652`、`../01_domain_and_service_architecture.md:653`）。

## Open Questions

1. 模块私有 schema 是否采用数据库级强制边界，以及如何做架构测试，仍需后端与数据库评审。
2. Worker 的队列隔离、优先级、公平性、死信和容量数值均为 TBD（`../03_security_reliability_and_operations.md:307`、`../03_security_reliability_and_operations.md:312`）。
3. 微服务拆分的量化触发条件、团队 Owner 和独立 SLO 尚未确定。
4. 事务数据库高可用、RPO/RTO 和恢复拓扑仍为 TBD（`../03_security_reliability_and_operations.md:332`、`../03_security_reliability_and_operations.md:343`）。

## References

- `../01_domain_and_service_architecture.md:45`
- `../01_domain_and_service_architecture.md:81`
- `../01_domain_and_service_architecture.md:92`
- `../01_domain_and_service_architecture.md:183`
- `../03_security_reliability_and_operations.md:316`
- `../../03_problem_modeling/problem_model.md:95`
