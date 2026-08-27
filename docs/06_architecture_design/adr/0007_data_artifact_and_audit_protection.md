# ADR 0007: Data, Artifact, and Audit Protection

- **Status: Proposed**
- **Date: 2026-08-26**

## Context

平台处理测试脚本、日志、报告、截图、视频、Trace、AI 输入输出、凭证引用、Evidence 和 AuditEvent。上游定义 Public/Internal/Confidential/Restricted 四级分类，Confidential 禁缓存，Restricted 仅本地模型或拒绝处理（`../../08_prd/prd.md:235`、`../03_security_reliability_and_operations.md:185`、`../03_security_reliability_and_operations.md:198`）。

Artifact 访问方式、Vault 产品和策略、保留/删除、Legal Hold、WORM、备份 RPO/RTO 及多数数值仍未定；“90 天”仍待法务确认，不能成为实现默认（`../03_security_reliability_and_operations.md:217`、`../03_security_reliability_and_operations.md:231`）。

## Decision

1. **Proposed：所有数据继承四级分类，并采用最高级别传播。** 输入、证据、历史上下文和工具结果取最高分类；分类缺失按 Confidential fail-close 候选处理，或由安全评审决定直接拒绝（`../03_security_reliability_and_operations.md:187`、`../03_security_reliability_and_operations.md:198`）。
2. **Proposed：凭证只保存 Vault/企业秘密系统引用。** 数据库仅保存 credential_ref、版本和非敏感元数据；Worker 以工作负载身份在执行前获取短期凭证，秘密值不得写入配置表、队列、日志、Trace、Prompt 或 Artifact（`../../03_problem_modeling/problem_model.md:228`、`../03_security_reliability_and_operations.md:132`、`../03_security_reliability_and_operations.md:142`）。Vault 产品、认证方式、lease 和轮换周期均为 TBD。
3. **Proposed：Artifact 正文进入默认私有对象存储，事务记录保存受控稳定引用。** Artifact/Evidence 引用本身不是访问授权；每次访问都重新校验 tenant、project、RBAC、classification、保留和 Legal Hold（`../01_domain_and_service_architecture.md:94`、`../01_domain_and_service_architecture.md:96`、`../03_security_reliability_and_operations.md:166`、`../03_security_reliability_and_operations.md:171`）。
4. **Proposed Artifact 访问候选为混合模式。** 大型普通文件可在后端授权后使用短期、单对象、只读预签名访问；Restricted 或高审计内容使用后端代理、隔离查看或禁止导出。具体方式、TTL、下载次数和 IP 绑定为 TBD（`../02_api_workflow_and_review.md:612`、`../02_api_workflow_and_review.md:629`、`../03_security_reliability_and_operations.md:168`、`../03_security_reliability_and_operations.md:171`）。
5. 所有上传、外部 Artifact、附件、日志和生成脚本都是不可信输入，经过隔离、类型/完整性/大小/结构校验、恶意文件扫描、脱敏和明确准入后才能被解析、模型或用户消费（`../03_security_reliability_and_operations.md:149`、`../03_security_reliability_and_operations.md:164`）。
6. EvidenceObject 保存 claim 到稳定 source_object 的关系，不保存短期预签名 URL；Evidence、AuditEvent、AIInvocationLog、GateEvaluation 等 append-only 事实不原地覆盖（`../../03_problem_modeling/problem_model.md:242`、`../../03_problem_modeling/problem_model.md:244`、`../02_api_workflow_and_review.md:715`、`../02_api_workflow_and_review.md:723`）。
7. AuditEvent 与应用日志、Trace 分开：审计用于归因和不可变业务/安全事实，应用日志用于调试，Trace 用于因果链；三者都禁止秘密和默认敏感正文（`../03_security_reliability_and_operations.md:345`、`../03_security_reliability_and_operations.md:355`）。
8. **所有保留、删除、Legal Hold、WORM 和备份数值/产品保持 TBD。** 90 天仅为上游假设；append-only 不得宣称等同 WORM。WORM 候选需评估对象锁、独立审计存储、哈希链或企业 SIEM 不可变层（`../03_security_reliability_and_operations.md:217`、`../03_security_reliability_and_operations.md:237`）。
9. 删除需覆盖 DB、缓存、对象、搜索、向量、导出暂存和备份恢复后的删除重放；Legal Hold 优先于正常生命周期，但角色、审批和 SLA 均待法务/安全决定（`../03_security_reliability_and_operations.md:233`、`../03_security_reliability_and_operations.md:238`）。

## Alternatives

1. **全部后端代理文件**：授权清晰但大文件占用应用带宽；作为 Restricted 候选保留，不作为所有文件的唯一方案（`../02_api_workflow_and_review.md:614`、`../02_api_workflow_and_review.md:618`）。
2. **全部预签名直传/直下**：吞吐较好，但 URL 是短期 bearer，不适合 Restricted 和高审计内容（`../02_api_workflow_and_review.md:617`、`../02_api_workflow_and_review.md:628`）。
3. **数据库保存二进制正文或预签名 URL**：明确拒绝；会混淆事务数据、稳定引用和临时访问授权。
4. **仅 append-only 数据库即满足 WORM**：明确拒绝；逻辑不可变不能证明防篡改或满足法务保留（`../03_security_reliability_and_operations.md:237`、`../03_security_reliability_and_operations.md:514`）。
5. **把 90 天当默认**：明确拒绝；法务确认尚未闭环（`../03_security_reliability_and_operations.md:219`、`../03_security_reliability_and_operations.md:510`）。

## Consequences

- 数据访问、AI 路由、导出和保留均需分类感知；增加元数据和策略复杂度，但可阻止 Restricted 出站和跨租户制品泄露（`../03_security_reliability_and_operations.md:200`、`../03_security_reliability_and_operations.md:206`）。
- 混合访问模式兼顾吞吐和敏感内容保护，但需要完成回调、checksum、扫描、对象归属和授权审计（`../02_api_workflow_and_review.md:620`、`../02_api_workflow_and_review.md:629`）。
- 保留/Hold/WORM 未定会阻断正式保留策略和生产放量，不应由工程实现自行填值（`../03_security_reliability_and_operations.md:510`、`../03_security_reliability_and_operations.md:540`）。

## Security and Operations

- Restricted 默认不经普通预签名 URL 或模型出站；Confidential 禁缓存、最小化并脱敏（`../03_security_reliability_and_operations.md:191`、`../03_security_reliability_and_operations.md:198`）。
- 对象 key 由服务端生成且带租户 scope；用户文件名只作展示，不作路径，主动内容不得与主站同源直接渲染（`../02_api_workflow_and_review.md:599`、`../02_api_workflow_and_review.md:608`、`../03_security_reliability_and_operations.md:157`、`../03_security_reliability_and_operations.md:164`）。
- Vault 不可用时新凭证相关动作 fail-close；是否允许已持 lease 的在途只读操作继续为 TBD（`../03_security_reliability_and_operations.md:138`、`../03_security_reliability_and_operations.md:140`）。
- 审计访问、Vault 读取、预签名签发、敏感下载、导出、删除和 Hold 操作都需记录，但审计不包含秘密正文（`../03_security_reliability_and_operations.md:142`、`../02_api_workflow_and_review.md:700`、`../02_api_workflow_and_review.md:711`）。

## Migration or Follow-up

1. 法务、安全和数据 Owner 完成逐数据类保留、删除、Hold 和 WORM 评审；所有值在批准前保持 TBD。
2. 安全/SRE 评审 Vault 产品、认证、lease、轮换、撤销、DR 和 break-glass；本 ADR 不选择供应商。
3. Stage 7 收口上传、Artifact、Evidence 和导出授权语义，但不在 ADR 中提供 endpoint/schema。
4. 建立数据盘点、分类覆盖、删除传播、孤儿对象、备份恢复和敏感日志扫描流程。

## Verification

- 文件安全测试覆盖类型伪造、zip bomb、XXE、路径穿越、恶意文件、资源耗尽、网络外带和未扫描入库（`../03_security_reliability_and_operations.md:531`）。
- 数据/AI 测试证明 Restricted 不出站、Confidential 不缓存、Prompt 正文默认不进普通日志（`../03_security_reliability_and_operations.md:532`）。
- 双租户测试覆盖 Artifact/Evidence、预签名、导出、对象 copy、缓存和恢复（`../03_security_reliability_and_operations.md:527`）。
- 保留测试覆盖生命周期、删除全副本传播、Hold 优先、恢复后不复活和 WORM 候选能力（`../03_security_reliability_and_operations.md:540`）。
- Vault 测试证明 DB/日志/Trace/Prompt 无明文，轮换/撤销和故障 fail-close（`../03_security_reliability_and_operations.md:530`）。

## Open Questions

1. 分类 Owner、缺失分类的最终行为和可降级规则尚未批准。
2. Vault 产品、租约、轮换周期、break-glass 和 DR 均为 TBD（`../03_security_reliability_and_operations.md:469`、`../03_security_reliability_and_operations.md:477`）。
3. Artifact 访问方式、预签名 TTL、扫描器、隔离保留和 Restricted 查看方式均为 TBD（`../03_security_reliability_and_operations.md:477`、`../03_security_reliability_and_operations.md:479`）。
4. 各数据类保留、删除 SLA、Legal Hold、WORM 和备份 RPO/RTO 均为 TBD（`../03_security_reliability_and_operations.md:484`、`../03_security_reliability_and_operations.md:496`）。

## References

- `../../03_problem_modeling/problem_model.md:237`
- `../../08_prd/prd.md:218`
- `../../08_prd/prd.md:233`
- `../02_api_workflow_and_review.md:595`
- `../03_security_reliability_and_operations.md:132`
- `../03_security_reliability_and_operations.md:185`
- `../03_security_reliability_and_operations.md:217`
