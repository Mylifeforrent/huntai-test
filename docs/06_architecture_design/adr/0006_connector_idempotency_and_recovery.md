# ADR 0006: Connector Idempotency and Recovery

- **Status: Proposed**
- **Date: 2026-08-26**

## Context

Jira、GitHub、CI 和 Release 都是外部权威系统；网络超时、重试、重复 webhook、轮询竞态、状态乱序和平台重启都可能造成重复副作用或状态倒退。上游要求统一 Connector Contract、幂等触发、webhook + 持久轮询双通道和补偿（`../../08_prd/prd.md:128`、`../../08_prd/prd.md:230`）。

Connector 回调只能形成外部观察，不能直接拥有 TestRun、ReleaseTask、GateEvaluation 或其他平台聚合的状态机（`../01_domain_and_service_architecture.md:183`、`../01_domain_and_service_architecture.md:195`）。

## Decision

1. **Proposed：所有 Jira/GitHub/CI/Release 连接器遵循统一 Connector Contract。** 组成包括 Auth、Resource Reader、Action Provider、Webhook Adapter、Health Check、RateLimit-Retry、Data Mapper、Permission Mapper；Action 声明 sideEffectLevel、Preview、Idempotency、Compensation，凭证只存引用，写前比较 ETag/版本（`../../01_market_research/market_research.md:70`、`../../01_market_research/market_research.md:73`、`../../08_prd/prd.md:228`、`../../08_prd/prd.md:231`）。
2. ApprovalRequest 消费事务在行锁内完成当前授权、参数哈希和目标版本复核，并原子创建以 `approval_request_id + bound_hash` 唯一标识的基础设施 execution intent 与同事务 Outbox；重复 consume 返回同一执行引用。该记录不是新领域对象，不使 ApprovalRequest 提前进入 EXECUTED。intent 至少区分 `READY / CLAIMED / DISPATCHING / CONFIRMED_OK / CONFIRMED_FAILED / UNKNOWN / ABANDONED`；本地事务不发远程请求，连接器结果先经 Inbox 去重/归一化，再以目标模块命令推进 ApprovalRequest 与目标聚合。
3. Outbox 至少一次发布；消费者以 event_id 在 Inbox 原子登记，并把消费记录与自身业务写放在同一事务。命令处理器和消费者必须重复安全，不能以“消息只投一次”为正确性前提（`../01_domain_and_service_architecture.md:462`、`../01_domain_and_service_architecture.md:467`）。
4. 受理幂等候选 scope 为 tenant + command/action type + idempotency key，并保存请求哈希和结果引用；同 key 同 hash 返回既有结果，同 key 不同 hash 拒绝冲突（`../01_domain_and_service_architecture.md:448`、`../01_domain_and_service_architecture.md:453`）。
5. Worker 只领取唯一 execution intent，并固定保存 stable idempotency key、external_request_id、目标版本与响应摘要；在网络调用前持久化 DISPATCHING。首次真实调用已发出后，以控制面命令写 `EXECUTED + execution_result=ok/failed/unknown`；READY/CLAIMED 崩溃可重领，DISPATCHING/UNKNOWN 或落账前崩溃先查询外部结果。只有提供方能证明请求不存在且契约允许时才重试；既不支持幂等创建也不能查询时保持 unknown、fail-close 并转人工接管（`../01_domain_and_service_architecture.md:239`、`../03_security_reliability_and_operations.md:264`、`../03_security_reliability_and_operations.md:274`）。
6. webhook 对原始请求字节强制验签并做 tenant/connector/resource 归属校验；delivery id 为首选去重键，无稳定 ID 时使用 connector、event type、resource、revision 和 canonical payload hash（`../01_domain_and_service_architecture.md:469`、`../01_domain_and_service_architecture.md:475`）。
7. webhook 与持久轮询映射为同一 ExternalObservation 语义：先到且版本较新的观察可触发聚合命令，重复/同版本忽略，较晚/较旧观察只对账和审计；轮询游标持久化（`../01_domain_and_service_architecture.md:469`、`../01_domain_and_service_architecture.md:475`、`../02_api_workflow_and_review.md:385`、`../02_api_workflow_and_review.md:394`）。
8. 终态吸收：迟到外部成功不能重开 CANCELLED/TIMEOUT 或已结束 ReleaseTask；可追加标记为 late 的结果、Artifact、Evidence 和 divergence 审计，需要新命令/新 run/重评估才可继续（`../01_domain_and_service_architecture.md:477`、`../01_domain_and_service_architecture.md:487`）。
9. 重试、退避、时钟窗口、去重保留期、熔断和 rate limit 数值均为 TBD；每个 Connector 依据真实能力单独评审（`../03_security_reliability_and_operations.md:246`、`../03_security_reliability_and_operations.md:274`）。

## Alternatives

1. **仅 webhook**：低延迟但丢失时无法恢复；明确需要持久轮询兜底（`../02_api_workflow_and_review.md:385`、`../02_api_workflow_and_review.md:394`）。
2. **仅轮询**：可恢复但延迟和外部负载较高，仍不能消除重复/乱序；放弃 webhook 的实时提示价值。
3. **远程调用放入数据库事务**：会长时间持锁且无法原子提交外部世界，网络未知结果仍无法安全回滚（`../01_domain_and_service_architecture.md:239`、`../01_domain_and_service_architecture.md:460`）。
4. **迟到事件覆盖平台终态**：明确拒绝，会破坏终态吸收和人工取消语义（`../01_domain_and_service_architecture.md:481`、`../01_domain_and_service_architecture.md:489`）。
5. **依赖提供方“恰好一次”**：明确拒绝；平台仍须为重放、重启和未知结果建立自己的幂等与对账事实。

## Consequences

- 可在至少一次投递和双通道观察下避免重复创建/重复触发，并支持重启恢复；代价是保存 Outbox/Inbox、外部 revision、游标和对账数据。
- Connector 与领域状态机解耦；新增连接器需实现统一 contract test，而不是直接写业务表（`../01_domain_and_service_architecture.md:193`、`../01_domain_and_service_architecture.md:196`）。
- 外部 API 若不支持幂等查询、ETag 或 webhook，自动恢复能力会下降并需要更强人工接管；Release API 能力仍为 TBD（`../../08_prd/prd.md:231`）。

## Security and Operations

- HMAC 空 secret、GET、调试模式都不得跳过验签；签名失败、重放和归属不匹配写安全审计（`../03_security_reliability_and_operations.md:244`、`../03_security_reliability_and_operations.md:252`）。
- 出站目标必须来自已注册连接器，保存和调用时校验协议、TLS、DNS/IP、端口和重定向；企业私网使用明确 allowlist，而非任意 URL（`../03_security_reliability_and_operations.md:254`、`../03_security_reliability_and_operations.md:262`）。
- 凭证仅存 Vault 引用，Worker 运行时以最小权限服务身份获取；秘密不得进入队列、Trace、错误或 Artifact（`../03_security_reliability_and_operations.md:132`、`../03_security_reliability_and_operations.md:142`）。
- 熔断按 connector/tenant/action 隔离，并保留查询、取消、审计和人工恢复路径（`../03_security_reliability_and_operations.md:272`、`../03_security_reliability_and_operations.md:274`）。

## Migration or Follow-up

1. 为每个外部系统建立能力清单：幂等创建、按 request id 查询、ETag/revision、webhook delivery id、取消和补偿。
2. 定义 versioned Connector Contract 与 contract test；供应商差异通过适配器显式表达，不在领域模块中分叉。
3. 在实现契约中落实已接受的 execution intent 状态、Outbox/Inbox、ExternalObservation、游标和 divergence 的基础设施数据归属、唯一键、领取租约与恢复协议；本 ADR 不提供 DDL 或迁移。
4. Release、Jira、GitHub、CI Owner 分别批准重试预算、限流和人工对账 runbook。

## Verification

- contract test 覆盖 Preview、幂等、查询后重试、HMAC、revision、ETag、补偿、rate limit 和迟到状态（`../01_domain_and_service_architecture.md:651`）。
- 混沌测试覆盖 Outbox 重发、Inbox 重复、webhook/轮询乱序、API/Worker 重启和网络未知结果，不产生重复副作用（`../01_domain_and_service_architecture.md:648`、`../03_security_reliability_and_operations.md:534`）。
- 崩溃点测试覆盖双 consume、调用前崩溃、调用后响应丢失、结果落账前崩溃和人工重提，证明只存在一个 execution intent；不可判定结果稳定进入 unknown，Approval/Audit 不虚假且不会自动放行。
- 安全测试覆盖 HMAC 绕过、重放、SSRF、DNS rebinding、metadata、TLS 和跨租户归属（`../03_security_reliability_and_operations.md:534`）。
- 迟到事件测试证明终态不重开，外部状态分叉产生 Evidence/Audit 和人工对账入口（`../01_domain_and_service_architecture.md:481`、`../01_domain_and_service_architecture.md:509`）。

## Open Questions

1. 各提供方 delivery ID、revision、查询和幂等能力差异仍待实测（`../01_domain_and_service_architecture.md:635`、`../01_domain_and_service_architecture.md:636`）。
2. Release API 是否支持幂等 prepare、状态查询和 webhook 仍为 TBD（`../../08_prd/prd.md:231`、`../../08_prd/prd.md:361`）。
3. HMAC 时钟窗口、去重/Inbox/Outbox 保留期、重试和熔断数值均为 TBD（`../03_security_reliability_and_operations.md:515`）。
4. 对不支持幂等创建或查询的外部写，是否只能人工执行仍需对应系统 Owner 决策。

## References

- `../../01_market_research/market_research.md:70`
- `../../08_prd/prd.md:128`
- `../../08_prd/prd.md:228`
- `../01_domain_and_service_architecture.md:446`
- `../01_domain_and_service_architecture.md:462`
- `../03_security_reliability_and_operations.md:240`
