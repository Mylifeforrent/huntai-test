# ADR 0002: Durable Workflow Runtime

- **Status: Accepted**
- **Date: 2026-08-29**

## Context

TestRun 包含长审批、外部 CI 排队与轮询、持久取消信号、心跳和故障恢复；技术 Gate 要求进程重启后不产生永久运行任务或重复副作用（`../../08_prd/prd.md:118`、`../../08_prd/prd.md:148`、`../../08_prd/prd.md:150`）。

研究输入提出 Temporal POC，同时保留 Celery + 自建状态机 + 幂等纪律。用户已完成适配 POC，并于 2026-08-29 确认 Temporal 符合本系统的长等待、Signal 与恢复需求，批准按独立架构复审结果收口选型。该确认支持架构选型，不等于托管/自托管、容量、成本、RPO/RTO、生产部署和运维值班已经批准。

## Decision

1. **采用 Temporal 作为持久工作流运行时。** Temporal Server 保存 workflow history、Timer、Signal 与 Task Queue 调度；Workflow Worker 只执行确定性编排代码，执行器、连接器、报告和 AI 以隔离的 Activity Worker/Task Queue 承载对应负载。
2. **PostgreSQL 领域事实继续唯一权威。** TestRun、ApprovalRequest、ReleaseTask 等业务状态由领域聚合和数据库裁决；Temporal 只编排命令、等待、Signal/观察和补偿，不新增或扭曲业务状态（`../02_api_workflow_and_review.md:79`、`../02_api_workflow_and_review.md:83`、`../03_security_reliability_and_operations.md:418`、`../03_security_reliability_and_operations.md:424`）。
3. **控制面事务不直接启动或 Signal workflow。** 业务事实与 Outbox 同事务提交；relay 以 event_id 和确定性 workflow_id 幂等执行 StartWorkflow/SignalWithStart/Signal。启动、Signal 或 relay 重试不能重复创建业务流程，Temporal 不可用时 Outbox 保留待重放。
4. **回调先落平台事实，再 Signal。** webhook、轮询和外部响应先验签、去重、归属校验并持久化 ExternalObservation/Inbox，再由 Outbox relay 向 workflow 发送仅含稳定引用的 Signal；Signal 本身不能直接修改领域状态。
5. **Workflow 不执行网络或数据库 I/O。** 所有控制面命令、外部调用、Artifact 操作和模型调用均由 Activity 执行；Activity 至少一次可安全执行，使用固定幂等语义、external_request_id、执行前当前权限/参数/目标版本复核，以及未知结果先查询后重试（`../01_domain_and_service_architecture.md:239`、`../01_domain_and_service_architecture.md:450`、`../01_domain_and_service_architecture.md:467`）。
6. **普通提交后任务不强制进入 Temporal。** 单步、可由 Outbox 重建、无需 Timer/Signal/多步恢复的通知或投影可由普通 Outbox Consumer 执行；需要长等待、取消、轮询、多步补偿或在途版本演进的流程必须由 Temporal 编排。同一业务步骤只能有一个调度 Owner，禁止 Outbox Consumer 与 Temporal Activity 双重执行。
7. WAITING_APPROVAL 与 WAITING_EXTERNAL 是持久可见等待，不由心跳回收；RUNNING 与 STOPPING 使用持久心跳和 TIMEOUT 兜底。运行时不得私自改变这些语义（`../../03_problem_modeling/problem_model.md:173`、`../../03_problem_modeling/problem_model.md:184`、`../../03_problem_modeling/problem_model.md:185`）。
8. 选型 Accepted 不等于生产就绪。Activity timeout/retry/heartbeat、history retention、namespace、Task Queue、容量、费用、托管/自托管、RPO/RTO 和值班方案仍须生产 Gate 批准。

## Alternatives

1. **Celery + PostgreSQL 自建持久编排**：团队可能更熟悉，但需自建可靠状态、Timer、Signal、轮询、恢复、历史和可见性；本轮 POC 后未选用，只有 Temporal 无法通过生产 Gate 时才以新 ADR 重评（`../../01_market_research/market_research.md:136`、`../02_api_workflow_and_review.md:249`、`../02_api_workflow_and_review.md:255`）。
2. **Temporal 同时作为业务状态源**：减少一层映射，但会形成运行时状态对领域语义的侵入，并使 API、审计、迁移和退出路径依赖 workflow history；明确拒绝。
3. **同步请求或内存任务**：无法承载长等待、进程重启和人工接管，违反已受理任务可恢复要求（`../01_domain_and_service_architecture.md:493`、`../01_domain_and_service_architecture.md:496`）。

## Consequences

- Temporal 原生表达长等待、Timer、Signal、重放与补偿，减少自建持久编排状态、轮询调度和恢复可见性的成本。
- 领域状态与运行时历史分离会增加 Outbox relay、命令适配和对账工作，但可避免供应商状态替代业务真相，并保留未来替换运行时的边界（`../02_api_workflow_and_review.md:81`、`../03_security_reliability_and_operations.md:420`）。
- 所有副作用必须在运行时重放和 Worker 重启下保持幂等；这会增加 Inbox、external_request_id、检查点和对账成本（`../01_domain_and_service_architecture.md:462`、`../01_domain_and_service_architecture.md:478`）。
- 团队需承担 workflow determinism、Worker Versioning、history retention、Task Queue 隔离、namespace 权限、备份恢复与值班能力。

## Security and Operations

- workflow/activity 传递 tenant、project、actor/reference、request hash 和 classification，但秘密值不得进入工作流历史或队列（`../03_security_reliability_and_operations.md:116`、`../03_security_reliability_and_operations.md:424`）。
- 工作流恢复、审批 consume 和 Connector 调用前必须重校验当前成员、动作资格、目标租户和参数哈希，不沿用旧授权快照直接执行（`../03_security_reliability_and_operations.md:96`）。
- 生产 Gate 必须覆盖备份恢复、Worker Versioning、证书/凭证轮换、积压查询和故障手册；未通过不得生产放量（`../03_security_reliability_and_operations.md:423`、`../03_security_reliability_and_operations.md:427`）。
- 数据库或审计不可用时，副作用 fail-close；不得为了保持队列吞吐绕开控制面（`../03_security_reliability_and_operations.md:324`、`../03_security_reliability_and_operations.md:328`）。

## Migration or Follow-up

1. Stage 7/实现设计定义 workflow_id、run_id、event_id、Signal 去重、Workflow/Activity 接口及路由矩阵。
2. 保存用户已完成 POC 的可复核原始证据；当前 ADR 只登记用户确认与架构选择，不虚构尚未提供的测试数据。
3. 生产放量前完成恢复、版本升级、安全、容量、成本、RPO/RTO 和值班 Gate；失败时停止放量并以新 ADR 重评托管方式或 Celery + PostgreSQL 替代。
4. 建立 Worker Versioning、兼容窗口、history reset/修复限制和回滚 runbook。

## Verification

- 分别重启 API、Worker、Temporal Server 和数据库，证明流程恢复且外部 CI/Jira/Release 不重复副作用（`../03_security_reliability_and_operations.md:420`、`../03_security_reliability_and_operations.md:422`）。
- 重放 Outbox relay，证明同一 event_id 只启动/Signal 目标 workflow；Temporal 暂不可用时事件保留，恢复后可重放。
- 重放、乱序和重复 Signal/Activity，证明状态边合法、审批只消费一次、终态不重开（`../03_security_reliability_and_operations.md:422`、`../01_domain_and_service_architecture.md:477`）。
- 升级和回滚 Worker，证明旧历史/在途任务兼容，不要求清空工作流（`../03_security_reliability_and_operations.md:423`）。
- 扫描 workflow history、队列、日志和 Trace，证明不存在 secret/Restricted 正文（`../03_security_reliability_and_operations.md:424`、`../03_security_reliability_and_operations.md:530`）。
- 验证等待态持续可见、可告警、可人工取消，STOPPING 可收敛 TIMEOUT（`../01_domain_and_service_architecture.md:647`、`../03_security_reliability_and_operations.md:535`）。

## Open Questions

1. Temporal 采用托管还是自托管、运维 Owner、值班技能和费用均未批准（`../03_security_reliability_and_operations.md:427`）。
2. namespace、Task Queue、workflow_id/reuse policy、Worker Versioning 和部署兼容窗口仍需实现设计。
3. 工作流历史、Inbox/Outbox 和幂等记录保留期均为 TBD（`../01_domain_and_service_architecture.md:528`）。
4. RPO/RTO、升级频率、灾备与 namespace/task queue 权限尚未批准（`../03_security_reliability_and_operations.md:426`、`../03_security_reliability_and_operations.md:496`）。

## References

- `../../01_market_research/market_research.md:132`
- `../../08_prd/prd.md:118`
- `../../08_prd/prd.md:360`
- `../03_security_reliability_and_operations.md:414`
- `../03_security_reliability_and_operations.md:429`
- `../01_domain_and_service_architecture.md:491`
