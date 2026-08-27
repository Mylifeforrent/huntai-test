# ADR 0005: Identity, Tenancy, and Project Membership

- **Status: Proposed**
- **Date: 2026-08-26**

## Context

平台需要企业 SSO、Organization→Project 两级租户、`owner/admin/tester/viewer` 项目角色和全层租户隔离。上游列出 OIDC/LDAP 候选，但 IdP、claim、MFA、会话和禁用传播仍未定稿（`../../08_prd/prd.md:107`、`../03_security_reliability_and_operations.md:55`、`../03_security_reliability_and_operations.md:67`）。

ProjectMember 的权威源存在冲突：部分描述称项目/成员从 Jira 同步，而问题模型把 ProjectMember 作为 CRUD、只明确 Project 从 Jira 同步（`../01_domain_and_service_architecture.md:593`、`../01_domain_and_service_architecture.md:599`）。

## Decision

1. **Proposed：OIDC Authorization Code + PKCE 作为主认证候选。** 平台服务端完成回调和 Token 校验，浏览器不保存 IdP Token；LDAP 仅在企业无 OIDC 能力时作为兼容候选，优先经企业身份代理转换（`../03_security_reliability_and_operations.md:57`、`../03_security_reliability_and_operations.md:65`）。这不是 IdP 或协议产品的最终选定。
2. **Proposed 权威拆分**：IdP/目录是 User 身份、账号启停和认证强度的权威源；Jira 是 Project/Jira 元数据的只读镜像来源；HuntAI Test 是 ProjectMember 平台角色授权的权威源（`../01_domain_and_service_architecture.md:595`、`../01_domain_and_service_architecture.md:599`）。
3. Jira 用户或组只能提供候选成员/映射输入，不能通过 webhook 或同步静默覆盖本地 `owner/admin/tester/viewer` 授权（`../01_domain_and_service_architecture.md:185`、`../01_domain_and_service_architecture.md:187`）。
4. 每个请求、查询、命令、Worker、队列消息、Artifact/Evidence 访问和 Tool/Connector 调用都必须建立可信 Organization tenant context；客户端提供的 tenant/角色不可信，无上下文即拒绝（`../03_security_reliability_and_operations.md:28`、`../03_security_reliability_and_operations.md:31`、`../03_security_reliability_and_operations.md:106`、`../03_security_reliability_and_operations.md:120`）。
5. 同租户内项目授权基于 ProjectMember 基础角色，并可叠加 Test Lead、Release Manager、性能工程师等职能资格和动作 Policy Gate；职能资格不替代项目成员身份（`../03_security_reliability_and_operations.md:84`、`../03_security_reliability_and_operations.md:94`）。
6. 已认证用户访问不存在对象或无权感知的跨租户对象，统一使用不可感知的“资源不存在”语义；同租户已可见对象的动作不足可表达权限不足。具体 HTTP 映射留待后续契约（`../02_api_workflow_and_review.md:147`、`../02_api_workflow_and_review.md:156`）。
7. 浏览器会话为可吊销的服务端会话候选，Cookie 使用安全属性；角色不作为长期静态快照，敏感动作和长流程恢复时读取当前授权（`../03_security_reliability_and_operations.md:69`、`../03_security_reliability_and_operations.md:76`、`../03_security_reliability_and_operations.md:96`）。
8. claim 映射、JIT/预配、会话时长、撤权传播、RLS、职能角色映射和 SLA 均为 TBD，不在本 ADR 中给默认值（`../03_security_reliability_and_operations.md:63`、`../03_security_reliability_and_operations.md:74`、`../03_security_reliability_and_operations.md:114`）。

## Alternatives

1. **Jira 成员为存在性权威，平台只保存角色 overlay**：减少维护，但同步失败可能误撤权/延迟撤权，且 Jira 未必能表达平台角色（`../01_domain_and_service_architecture.md:597`、`../01_domain_and_service_architecture.md:599`）。
2. **平台直连 LDAP 为主认证**：在无 OIDC 时可行，但组、禁用传播、TLS、连接池和故障行为复杂，仍需服务端会话（`../03_security_reliability_and_operations.md:63`、`../03_security_reliability_and_operations.md:65`）。
3. **仅入口层做租户过滤**：明确拒绝；后台、缓存、队列、对象和检索仍可能越权（`../03_security_reliability_and_operations.md:110`、`../03_security_reliability_and_operations.md:123`）。
4. **长期会话携带角色快照**：明确拒绝；成员变化和离职后旧权限可能继续执行副作用（`../03_security_reliability_and_operations.md:71`、`../03_security_reliability_and_operations.md:96`）。

## Consequences

- 身份、项目镜像和平台授权职责清晰，可支持四眼与平台专用角色；代价是需要 ProjectMember 生命周期、同步差异展示和撤权流程（`../01_domain_and_service_architecture.md:597`、`../01_domain_and_service_architecture.md:599`）。
- 全层 tenant scope 增加查询、消息、对象键、缓存、恢复和测试复杂度，但避免仅靠 UI/端点约定造成越权（`../03_security_reliability_and_operations.md:110`、`../03_security_reliability_and_operations.md:121`）。
- OIDC 仅是候选主路径；在企业 IdP 能力验证前不得锁定 claim、会话或 MFA 方案。

## Security and Operations

- 登录、登出、禁用、租户移除、角色变化和 Token 吊销必须可撤销会话/Token；传播机制与目标时延保持 TBD（`../03_security_reliability_and_operations.md:69`、`../03_security_reliability_and_operations.md:75`）。
- 所有 Cookie 写请求需要 CSRF 防护；OIDC 使用 state/nonce/PKCE 和精确回调 URI，认证日志不记录 Token（`../03_security_reliability_and_operations.md:75`）。
- 数据库/ORM 强制 tenant predicate，PostgreSQL RLS 仅为 Proposed 纵深防御，不替代应用过滤（`../03_security_reliability_and_operations.md:110`、`../03_security_reliability_and_operations.md:115`）。
- 平台安全跨租户检索需要独立高权限职能和额外审计，不得复用普通项目角色（`../03_security_reliability_and_operations.md:120`）。

## Migration or Follow-up

1. 与 IdP Owner 完成 OIDC capability、issuer、claim、MFA/强认证、禁用传播和 JIT/预配评审。
2. 由安全、Jira Owner 和产品正式裁决 ProjectMember 权威源；本 ADR 未获批准前不得让 Jira 同步覆盖本地角色（`../01_domain_and_service_architecture.md:632`）。
3. 定义 Project/Jira 镜像、候选成员映射、差异处理、离职/调岗撤权和 break-glass 流程。
4. Stage 7 定义不可感知资源语义、会话/Token 认证和租户上下文传递，但不擅自填充 TBD 数值。

## Verification

- OIDC/LDAP 候选测试覆盖登录、登出、禁用、会话轮换、CSRF、回调和再认证不绕审批（`../03_security_reliability_and_operations.md:524`、`../03_security_reliability_and_operations.md:527`）。
- 双租户测试覆盖 DB/ORM/RLS 候选、缓存、队列、对象、向量、异步、审计、导出和恢复；任一路径泄露即阻断（`../03_security_reliability_and_operations.md:527`）。
- 权限测试证明 Jira 同步不覆盖本地角色，ProjectMember 撤销后队列恢复、审批 consume 和 Connector 调用均拒绝旧权限（`../03_security_reliability_and_operations.md:528`）。
- 404 遮蔽测试证明跨租户对象存在性不可探测（`../02_api_workflow_and_review.md:149`、`../02_api_workflow_and_review.md:156`）。

## Open Questions

1. 企业 IdP、OIDC issuer/client、claim、MFA 与强认证能力尚未确定（`../03_security_reliability_and_operations.md:63`）。
2. ProjectMember 最终权威源、Jira 用户/组映射和撤权 SLA 尚未批准（`../01_domain_and_service_architecture.md:632`）。
3. JIT 创建或预配、服务端会话时长、并发会话数和禁用传播均为 TBD（`../03_security_reliability_and_operations.md:65`、`../03_security_reliability_and_operations.md:73`）。
4. PostgreSQL RLS、平台职能角色和跨租户安全检索流程仍需专项评审（`../03_security_reliability_and_operations.md:114`、`../03_security_reliability_and_operations.md:120`）。

## References

- `../../08_prd/prd.md:107`
- `../../03_problem_modeling/problem_model.md:276`
- `../01_domain_and_service_architecture.md:593`
- `../03_security_reliability_and_operations.md:55`
- `../03_security_reliability_and_operations.md:106`
- `../02_api_workflow_and_review.md:147`
