# ADR 0002: Durable Workflow Runtime

- **Status: Proposed**
- **Date: 2026-08-26**

## Context

TestRun 包含长审批、外部 CI 排队与轮询、持久取消信号、心跳和故障恢复；技术 Gate 要求进程重启后不产生永久运行任务或重复副作用（`../../08_prd/prd.md:118`、`../../08_prd/prd.md:148`、`../../08_prd/prd.md:150`）。

研究输入提出 Temporal POC，同时保留 Celery + 自建状态机 + 幂等纪律；PRD 仍把结论登记为开放问题，因此当前没有完成的 POC 或已选定运行时（`../../01_market_research/market_research.md:134`、`../../01_market_research/market_research.md:136`、`../../08_prd/prd.md:360`）。

## Decision

1. **不在本 ADR 中选定持久工作流产品。** Temporal 仅进入条件 POC；只有恢复、Signal、Activity、版本升级、租户、安全、可观测和运维成本 Gate 全部通过，才可另行提议采用（`../03_security_reliability_and_operations.md:414`、`../03_security_reliability_and_operations.md:427`、`../03_security_reliability_and_operations.md:429`、`../03_security_reliability_and_operations.md:432`）。
2. **保底候选为 Celery + PostgreSQL 权威状态机 + Outbox/Inbox + 幂等键 + 持久轮询/信号 + 心跳/僵尸回收。** Celery 或 Redis 的任务状态不得成为业务事实源，保底方案必须通过与 Temporal 相同的重启、重复、乱序、租户和审计 Gate（`../03_security_reliability_and_operations.md:431`、`../03_security_reliability_and_operations.md:435`）。
3. 无论采用哪个运行时，TestRun、ApprovalRequest、ReleaseTask 等业务状态继续由领域聚合和数据库事实裁决；运行时只编排命令、等待、Signal/观察和补偿，不新增或扭曲业务状态（`../02_api_workflow_and_review.md:79`、`../02_api_workflow_and_review.md:83`、`../03_security_reliability_and_operations.md:418`、`../03_security_reliability_and_operations.md:424`）。
4. Activity/任务必须至少一次可安全执行：固定幂等语义、外部请求标识、执行前当前权限/参数/目标版本复核，以及未知结果先查询后重试（`../01_domain_and_service_architecture.md:239`、`../01_domain_and_service_architecture.md:450`、`../01_domain_and_service_architecture.md:467`）。
5. WAITING_APPROVAL 与 WAITING_EXTERNAL 是持久可见等待，不由心跳回收；RUNNING 与 STOPPING 使用持久心跳和 TIMEOUT 兜底。运行时不得私自改变这些语义（`../../03_problem_modeling/problem_model.md:173`、`../../03_problem_modeling/problem_model.md:184`、`../../03_problem_modeling/problem_model.md:185`）。
6. 所有 Activity timeout、retry、heartbeat、history retention、task queue、容量和费用数值均为 TBD；POC 不等于生产选型或部署批准（`../03_security_reliability_and_operations.md:426`、`../03_security_reliability_and_operations.md:435`）。

## Alternatives

1. **直接定 Temporal**：可原生表达长等待、Signal、重放与补偿，但在升级、历史兼容、秘密治理、备份恢复和值班能力未验证前风险不可接受（`../03_security_reliability_and_operations.md:420`、`../03_security_reliability_and_operations.md:427`）。
2. **直接定 Celery**：团队可能更熟悉，但需自建可靠状态、信号、轮询、恢复和可见性；不能把队列成功等同业务成功（`../../01_market_research/market_research.md:136`、`../02_api_workflow_and_review.md:249`、`../02_api_workflow_and_review.md:255`）。
3. **同步请求或内存任务**：无法承载长等待、进程重启和人工接管，违反已受理任务可恢复要求（`../01_domain_and_service_architecture.md:493`、`../01_domain_and_service_architecture.md:496`）。

## Consequences

- 延后产品锁定，避免把未完成 POC 写成架构事实；短期需要维护统一的语义测试套件和两个候选方案的评估矩阵。
- 领域状态与运行时历史分离会增加适配工作，但可避免供应商状态替代业务真相，并保持保底切换可能性（`../02_api_workflow_and_review.md:81`、`../03_security_reliability_and_operations.md:420`）。
- 所有副作用必须在运行时重放和 Worker 重启下保持幂等；这会增加 Inbox、external_request_id、检查点和对账成本（`../01_domain_and_service_architecture.md:462`、`../01_domain_and_service_architecture.md:478`）。

## Security and Operations

- workflow/activity 传递 tenant、project、actor/reference、request hash 和 classification，但秘密值不得进入工作流历史或队列（`../03_security_reliability_and_operations.md:116`、`../03_security_reliability_and_operations.md:424`）。
- 工作流恢复、审批 consume 和 Connector 调用前必须重校验当前成员、动作资格、目标租户和参数哈希，不沿用旧授权快照直接执行（`../03_security_reliability_and_operations.md:96`）。
- POC 必须覆盖备份恢复、worker 版本兼容、证书/凭证轮换、积压查询和故障手册；未通过不能进入选型提案（`../03_security_reliability_and_operations.md:423`、`../03_security_reliability_and_operations.md:427`）。
- 数据库或审计不可用时，副作用 fail-close；不得为了保持队列吞吐绕开控制面（`../03_security_reliability_and_operations.md:324`、`../03_security_reliability_and_operations.md:328`）。

## Migration or Follow-up

1. 制作同一组候选无关场景：长审批、外部轮询、取消 Signal、重复 webhook、Worker 重启、版本升级、权限撤销、未知外部结果和人工接管。
2. 对 Temporal 执行条件 POC，并保留原始验证证据；本 ADR 不声称 POC 已开始或完成（`../03_security_reliability_and_operations.md:418`、`../03_security_reliability_and_operations.md:431`）。
3. 同时对 Celery + PostgreSQL 保底做等价 Gate，不允许以“保底”为由降低可靠性或安全标准（`../03_security_reliability_and_operations.md:433`、`../03_security_reliability_and_operations.md:435`）。
4. POC 后另建或修订 ADR，记录实测结果、运维 Owner、成本和选择；在此之前保持 Proposed。

## Verification

- 分别重启 API、Worker、运行时和数据库，证明流程恢复且外部 CI/Jira/Release 不重复副作用（`../03_security_reliability_and_operations.md:420`、`../03_security_reliability_and_operations.md:422`）。
- 重放、乱序和重复 Signal/Activity，证明状态边合法、审批只消费一次、终态不重开（`../03_security_reliability_and_operations.md:422`、`../01_domain_and_service_architecture.md:477`）。
- 升级和回滚 Worker，证明旧历史/在途任务兼容，不要求清空工作流（`../03_security_reliability_and_operations.md:423`）。
- 扫描 workflow history、队列、日志和 Trace，证明不存在 secret/Restricted 正文（`../03_security_reliability_and_operations.md:424`、`../03_security_reliability_and_operations.md:530`）。
- 验证等待态持续可见、可告警、可人工取消，STOPPING 可收敛 TIMEOUT（`../01_domain_and_service_architecture.md:647`、`../03_security_reliability_and_operations.md:535`）。

## Open Questions

1. Temporal 采用托管还是自托管、运维 Owner、值班技能和费用均为 TBD（`../03_security_reliability_and_operations.md:427`）。
2. Celery 保底所需调度、信号、可见性和历史模型尚未定稿。
3. 工作流历史、Inbox/Outbox 和幂等记录保留期均为 TBD（`../01_domain_and_service_architecture.md:528`）。
4. RPO/RTO、升级频率、灾备与 namespace/task queue 权限尚未批准（`../03_security_reliability_and_operations.md:426`、`../03_security_reliability_and_operations.md:496`）。

## References

- `../../01_market_research/market_research.md:132`
- `../../08_prd/prd.md:118`
- `../../08_prd/prd.md:360`
- `../03_security_reliability_and_operations.md:414`
- `../03_security_reliability_and_operations.md:429`
- `../01_domain_and_service_architecture.md:491`
