# 安全、可靠性与运维架构

> - **Status: Draft**
> - **日期**：2026-08-26
> - **阶段**：Stage 6（系统架构设计）阶段二产出，Agent C 分册
> - **审批状态**：未批准；本文不将候选方案标记为定稿，不修改任何上游结论
> - **范围**：安全、可靠性、容量、可观测、事故响应、成本与运维边界；不包含代码、迁移、真实部署配置或供应商定稿
> - **上游**：`../00_setup/project_rules.md`、`../README.md`、`../03_problem_modeling/problem_model.md`、`../04_interaction_design/chains/c1_north_star_quality_loop.md` 至 `c4_failure_triage.md`、`../08_prd/prd.md`、`architecture.md`、`frontend_backend_boundary_spec-v1.0.md`、`../01_market_research/market_research.md`、`../02_competitor_analysis/competitor_analysis.md`

## 0. 文档纪律与决策标签

本文只细化上游已定义的安全与可靠性落点，不新增业务页面、领域对象或状态机。前端不是安全边界，状态迁移、租户与权限、Policy Gate、参数哈希、外部调用和 AI 调用均以后端裁决为准（`frontend_backend_boundary_spec-v1.0.md:17`、`frontend_backend_boundary_spec-v1.0.md:18`、`frontend_backend_boundary_spec-v1.0.md:19`、`frontend_backend_boundary_spec-v1.0.md:20`）。

| 标签 | 含义 |
| --- | --- |
| **上游约束** | 已在上游出现，本文只给架构落点；若上游本身仍标假设/TBD，本文不提升其成熟度 |
| **Draft 推荐** | 本分册建议，需后续安全、架构、SRE、法务或系统 Owner 评审 |
| **替代方案** | 推荐不可行时的备选；启用前必须达到同等 Gate |
| **TBD** | 缺数值、Owner、人名、供应商、合同或实测证据，不得当作默认值实施 |
| **阻断项** | 未闭环不得进入相应里程碑或生产放量 |

安全总原则：默认拒绝、最小权限、全程可归因、失败不静默、等待可见、恢复可验证。AI 不决定权限、重试、幂等、审批或业务状态迁移；其输出只是受约束输入（`../README.md:44`、`../README.md:45`、`../README.md:47`）。

## 1. 信任边界与威胁模型

### 1.1 信任边界

| 边界 | 区域与资产 | 主要入口 | 主要威胁 | Draft 控制与失败语义 |
| --- | --- | --- | --- | --- |
| TB-0 用户终端 ↔ 企业身份 | 浏览器、SSO 回调、会话 | OIDC/LDAP、前端请求 | 凭证窃取、会话固定、CSRF、开放重定向、失效账号继续访问 | 认证码流、服务端回调白名单、安全 Cookie、会话轮换；认证上下文缺失或校验失败即拒绝 |
| TB-1 网关 ↔ 应用治理面 | API、SSE、审批、Policy Gate | HTTP/SSE、ApiToken | 伪造租户头、越权、重放、绕过限流、SSE 泄露 | 网关做流量防护，应用每请求重建可信身份/租户上下文；不信任客户端传入的角色与 tenant_id |
| TB-2 治理面 ↔ 执行面 | TestRun、调度、平台执行器、外部 CI | 队列、工作流 Activity、终止信号 | 重复副作用、任务劫持、僵尸任务、越租户消费、取消失效 | 队列消息携带服务端签发的租户/任务上下文；消费时重校验；幂等、心跳、持久化信号、补偿；Redis 不作唯一状态源 |
| TB-3 应用 ↔ 数据面 | PostgreSQL、Redis、对象/向量存储、备份 | ORM、缓存、对象引用、检索 | 跨租户读取、缓存污染、未授权制品、向量召回越权、备份泄露 | 全层 tenant scope；DB 强制过滤并评估 RLS；缓存与对象键带租户；向量检索先授权后召回；备份加密与恢复隔离 |
| TB-4 应用 ↔ 模型面 | 模型网关、Embedding、Prompt/Skill | Model Adapter/LLM 工厂 | Restricted 出站、提示注入、日志泄密、供应商滥用、AI 旁路 | 模型唯一出口、数据分级路由、脱敏、供应商白名单、结构化输出、evidence 校验；Restricted 本地或拒绝 |
| TB-5 应用 ↔ 企业外部系统 | Jira/GitHub/CI/Release/通知/MCP | Connector、Webhook、MCP transport | SSRF、HMAC 绕过、重放、DNS rebinding、过度授权、重复写、污染输入 | 注册目标白名单、强制验签、重放存储、ETag、幂等、最小 scope、补偿、出站审计；连接器失效不绕过治理 |
| TB-6 应用 ↔ 文件与沙箱 | 上传源、报告、日志、脚本、截图/视频/Trace | 上传、外部 Artifact 拉取、容器输入输出 | 恶意文件、压缩炸弹、RCE、路径穿越、恶意输出、凭证外带 | 隔离区→扫描→准入；rootless 临时容器、只读镜像、默认无网、资源限制、输出再扫描 |
| TB-7 平台 ↔ 运维与观测 | OTel、日志、指标、Trace、SIEM、控制台 | Telemetry、运维管理 | 高权限误用、敏感字段进入日志、审计篡改、告警失效 | 运维身份分离、审计 append-only、日志脱敏、观测访问最小权限、关键事件外发 SIEM；业务审计与调试日志分离 |

上游已明确执行面与治理面分离，两个执行面必须共用工作流、策略、证据和审计（`../01_market_research/market_research.md:27`、`../01_market_research/market_research.md:33`）。因此“外部 CI 已认证”不能替代平台侧的租户、动作、参数和证据校验。

### 1.2 资产、攻击者与优先级

**高价值资产**：身份与项目成员关系、ApprovalRequest 绑定哈希、连接器/Vault 凭证、ApiToken、TestRun 与范围快照、用例脚本、测试数据、Artifact/Evidence、AI 输入输出、AuditEvent、模型路由、kill switch、备份与恢复密钥。

**攻击者模型**：越权内部用户、被盗账号/Token、恶意或失陷的外部系统、被污染的 Jira/PR/Confluence/日志内容、恶意上传者、受提示注入影响的模型、越界 Skill/MCP 工具、失陷 worker/执行容器、误操作管理员。基础设施完全失陷后的取证与恢复属于企业安全体系与本平台联合响应，不假设平台自身仍可信。

| 优先级 | 威胁事件 | 安全目标 |
| --- | --- | --- |
| P1 | 跨租户数据泄露、未经审批的外部写、生产发布执行越界、Restricted 数据出站、凭证泄露、审计链被破坏 | 立即阻断相关能力，保全证据，启动 P1 流程 |
| P2 | AI 无据结论率恶化、Prompt/Skill 行为漂移、连接器重复写、制品访问越权、沙箱逃逸迹象 | 降级/回滚/隔离，暂停放量 |
| P3 | 单一 AI 能力不可用、非关键连接器降级、报表延迟、等待态积压 | 保核心执行与证据，告警并人工接管 |

PRD 将外部误写/数据泄露列为 P1，并给出“15 分钟启动、1 小时止血决策”的现有目标；由于 PRD 自述仍为中期版，本文把它作为 **Draft 事故响应目标**，待值班体系演练后确认（`../08_prd/prd.md:343`）。

## 2. 身份、会话与持续授权

### 2.1 SSO 候选

上游要求企业 SSO，候选为 OIDC/LDAP（`../08_prd/prd.md:107`、`../README.md:329`）。

| 项目 | Draft 推荐 | 替代方案 | 待决项 |
| --- | --- | --- | --- |
| 主认证 | **OIDC Authorization Code + PKCE**；FastAPI 认证端完成回调和 Token 校验，前端不保存 IdP Token | 企业身份代理将 LDAP 转为 OIDC/SAML 后平台只接代理 | IdP、Issuer、Client、claim 映射、MFA/强认证能力 **TBD** |
| LDAP | 仅在企业无 OIDC 时作为兼容候选；必须 LDAPS/StartTLS、专用只读 bind 身份、严格证书校验、查询范围最小 | 平台直连 LDAP，但仍由服务端建立本地会话 | 组同步、账号禁用传播、嵌套组、连接池和故障行为 **TBD** |
| 账号来源 | IdP/目录是身份事实源；Organization、ProjectMember 和职能授权由平台映射，不接受浏览器自报 | 周期同步 + 登录时校验 | JIT 创建或预配、离职禁用时效 **TBD** |

禁止：密码模式、前端 localStorage 保存访问/刷新 Token、弱口令本地后门账号、TLS `verify=false`。竞品已出现明文 Key、跨用户取 Key 与弱安全默认值，必须作为反向验证项（`../02_competitor_analysis/competitor_analysis.md:75`、`../README.md:359`）。

### 2.2 会话

**Draft 推荐**：服务端维护可吊销会话，浏览器仅持 `HttpOnly + Secure + SameSite` 会话 Cookie；登录、权限提升和再认证后轮换 session id。会话中只保存身份引用与认证强度，不把可变角色快照当作长期授权事实。

- 会话绝对时长、空闲时长、刷新窗口、并发会话数、时钟偏差均 **TBD**，不得在实现中自行固化。
- 登出、账号禁用、租户移除、项目角色变更、ApiToken 吊销、全局安全事件必须触发会话/Token 失效；传播机制和目标时延 **TBD**。
- CSRF 防护用于所有 Cookie 认证写请求；OIDC state/nonce/PKCE、回调 URI 精确匹配；认证失败与异常 claim 写安全审计但不记录 Token。
- SSE/下载/预签名链接不能把会话或凭证放入 URL；长连接建立时和敏感事件处理前都需授权。

### 2.3 再认证

上游已定义 `REQUIRE_REAUTH`：L3+ 且会话超过再认证窗口，或目标资源声明强认证（`../08_prd/prd.md:111`、`../04_interaction_design/chains/c2_approval_chain.md:220`）。

**Draft 推荐流程**：Policy Gate 返回 `REQUIRE_REAUTH` → 保存待执行动作引用而非凭证 → 通过 IdP 强认证/新鲜认证 → 重算当前权限、租户、动作参数哈希 → 再进入审批或执行。再认证不替代四眼审批；审批也不替代再认证。再认证窗口数值、认证上下文 claim 和强认证等级 **TBD**。

### 2.4 RBAC、职能角色与持续授权

| 层 | 权限语义 | 强制点 |
| --- | --- | --- |
| 平台层 | 平台管理员、安全、SRE 值班等职能角色 | 管理模型路由、连接器、审计、kill switch、运维操作；职能角色映射方式 **Draft/TBD** |
| 组织层 | Organization 归属、Owner、预算与配额管理 | 所有请求必须有唯一可信组织上下文；无上下文拒绝 |
| 项目层 | `owner/admin/tester/viewer` 统一项目角色 | viewer 只读；具体动作按权限矩阵；项目成员变更立即影响后续授权 |
| 业务职能 | Test Lead、Release Manager、性能工程师 | 是附加资格，不替代项目成员身份；Release/门禁/压测动作同时满足项目权限与职能资格 |
| 动作层 | L0–L4 + Policy Gate | 未声明等级默认 DENY；L2/L3 审批；L4 仅允许明确的“准备/草稿”子动作，实际发布/删除禁止 |

项目角色与职能角色已在交互链中分开使用（`../04_interaction_design/chains/c1_north_star_quality_loop.md:15`）。**Draft 推荐**采用“RBAC 基础角色 + 资源属性/职能资格 + Policy Gate”组合，不新增第二套同名角色体系。

**持续授权检查点**：请求入口、对象加载、队列消费、工作流恢复、审批创建、审批提交、APPROVED consume、连接器调用、制品签名 URL 签发、向量召回、MCP/Tool 调用。长流程恢复时不得沿用旧权限快照直接执行副作用；必须重校验当前成员关系、动作资格、目标租户和参数哈希。前端置灰仅改善体验，不构成授权（`frontend_backend_boundary_spec-v1.0.md:240`）。

### 2.5 四眼与高危动作

- ApprovalRequest 创建和批准时均强制 `approver_id != initiator_id`；重新提交以重新提交人为 initiator，并保留原始归因链（`../03_problem_modeling/problem_model.md:195`、`../03_problem_modeling/problem_model.md:206`）。
- APPROVED consume 必须事务性单次消费；并发第二次执行拒绝并审计（`../04_interaction_design/chains/c2_approval_chain.md:180`）。
- 执行前重算权限与 param_hash；参数或授权变化使原审批失效，fail-close（`../08_prd/prd.md:110`）。
- kill switch **关停**为收紧控制，立即生效且不受审批阻塞；**恢复**为 L3，走 `kill_switch_restore` 审批（`../03_problem_modeling/problem_model.md:337`）。
- Release 的实际生产发布仍为 DENY；平台仅准备 release item。其动作处于 L4 风险域，不因命名为“准备”而取消审批和审计（`../03_problem_modeling/problem_model.md:220`、`../08_prd/prd.md:138`）。

## 3. 全层租户隔离

Organization 是部门/事业部租户。所有核心表必须带 tenant_id，缺租户上下文拒绝；跨租户引用返回 404，不泄露存在性（`../03_problem_modeling/problem_model.md:97`、`../08_prd/prd.md:151`）。

| 层 | Draft 隔离要求 | 验证重点 |
| --- | --- | --- |
| 请求/认证 | tenant_id 只由服务端根据会话、Token 和资源归属解析；忽略/拒绝客户端伪造租户头 | 双租户同 ID/猜 ID/换头/换 Token 回归 |
| DB/ORM | 每个租户表强制 tenant predicate；关联加载、聚合、审计检索、后台任务同样过滤；唯一约束优先包含 tenant_id | ORM 绕过、raw SQL、管理脚本、聚合、异步路径扫描 |
| PostgreSQL RLS 候选 | **Draft 推荐**以 RLS 作纵深防御，应用事务设置可信 tenant context；不是 ORM 的替代品 | 连接池 context 泄漏、管理员 bypass、迁移/备份账户 |
| 缓存/限流/短锁 | key namespace 必含 tenant_id + resource scope；Confidential 禁缓存；缓存值带 schema/version；禁止用 Redis 作为授权事实或工作流唯一状态 | key 碰撞、缓存投毒、租户切换、过期后权限变化 |
| 队列/工作流 | message/workflow/activity 带 tenant_id、project_id、actor/ref 和 request_hash；生产者服务端生成；消费者重校验资源归属 | 伪造消息、重放、错误队列消费、恢复后旧授权 |
| 对象存储 | 对象键或 bucket policy 强制 tenant namespace；元数据含 tenant/project/classification；默认私有；访问经短时授权代理或预签名 URL 候选 | 枚举、路径替换、URL 泄露、过期、跨租户 copy |
| 向量/全文检索 | embedding/索引行带 tenant_id、project/source ACL、classification；先确定授权过滤器，再召回；检索结果再次鉴权 | filter 缺失、全局近邻泄露、删除后残留向量 |
| 异步解析/AI | 暂存、批次、failed_items、embedding、AIInvocationLog 继承原始租户与分类；后台服务不得使用“无租户即全局” | partial 任务、重试、死信、跨租户批处理 |
| 证据/审计/SIEM | Evidence、Artifact、Audit 查询按租户隔离；平台安全跨租户查询需独立高权限职能与审计 | 管理员滥用、导出范围、SIEM 多租户路由 |
| 备份/恢复 | 备份加密、访问独立；恢复到隔离环境；租户级恢复不得覆盖或暴露其他租户；恢复后重建向量/缓存需保持 scope | 恢复演练、导出审计、密钥分离、删除传播 |

**禁止的反模式**：无组织上下文时取消过滤、仅在端点手工过滤、仅靠 prompt 注入角色、只在 UI 隐藏对象。竞品中“无组织上下文 = 不过滤”已被明确取证（`../02_competitor_analysis/competitor_analysis.md:32`）。

### 3.1 数据库选型冲突处理

- **冲突**：根 README 仍写“开发期 SQLite，需并发再切 PostgreSQL”（`../../README.md:47`）；PRD 与架构输入已指定 PostgreSQL + pgvector，并要求第一天多租户隔离（`../08_prd/prd.md:221`、`../08_prd/prd.md:222`）。
- **Draft 推荐**：M0 集成与安全 Gate 使用 PostgreSQL；SQLite 只能作为无共享数据、无并发、无租户安全结论的本地开发便利，不得作为租户隔离、并发审批、幂等、恢复或 Temporal POC 的验收环境。
- **替代方案**：若阶段资源不足，单元测试可用 SQLite，但所有安全/并发/恢复集成 Gate 必须在 PostgreSQL 重跑。
- **状态**：Draft，需总架构文档定稿；本文不修改上游。

## 4. Vault、密钥与凭证

上游要求连接器凭证仅存 Vault 引用，运行时读取；前端不持有外部凭证（`../03_problem_modeling/problem_model.md:228`、`frontend_backend_boundary_spec-v1.0.md:19`）。工程红线禁止密钥、生产数据和隐私数据进入 AI、日志或提交（`../00_setup/project_rules.md:124`）。

### 4.1 Draft 控制

1. **存储**：数据库只存 `credential_ref`、版本和非敏感元数据；Vault policy 按环境、服务身份、连接器和租户 scope 最小授权。禁止把 Vault 返回值写入配置表、队列、Trace、错误消息、Prompt 或 Artifact。
2. **获取**：worker/Connector 在执行前以工作负载身份获取短期凭证；缓存仅在受控内存内且不超过 lease，持久缓存禁止。Vault 不可用时，新凭证相关动作 fail-close；是否允许已持 lease 的在途只读操作继续由动作策略决定，**TBD**。
3. **轮换**：连接器 Token、OIDC secret、LDAP bind、Webhook HMAC、对象存储和模型网关凭证均有 Owner、轮换周期、版本与撤销流程，周期数值 **TBD**。Webhook 可候选支持 current/next 双 key 短窗口，窗口 **TBD**。
4. **展示**：ApiToken/一次性凭证只在签发时显示一次；服务端保存不可逆摘要，列表只显示标识与元数据，不打印前后缀。算法和参数 **TBD/安全评审**。
5. **审计**：读取、失败、轮换、撤销、权限变更均进安全审计；审计不记录 secret value。
6. **Break-glass**：不预设长期共享超管密钥。紧急访问候选采用限时、双人批准、全量审计和事后复核；具体企业流程 **TBD**。即时关停 kill switch 不依赖 break-glass 审批。

### 4.2 凭证生命周期 Gate

创建 → 一次展示/引用入库 → 最小 scope 验证 → 健康检查 → 轮换演练 → 撤销验证 → 关联会话/连接器失效验证 → 审计检索。任一步泄露明文、无法撤销、空 secret 可绕过或 TLS 校验关闭，均阻断上线。

## 5. 文件上传、制品访问与沙箱

### 5.1 文件信任状态

所有用户上传、外部 CI Artifact、Jira/Confluence 附件、导入包、日志与模型生成脚本均为**不可信输入**，状态按 `隔离 → 校验/扫描 → 可消费或拒绝 → 生命周期处置` 管理；这只是安全处理状态，不新增领域对象状态机。

| 控制点 | Draft 要求 |
| --- | --- |
| 鉴权与范围 | 上传、SSE、下载全部鉴权；在接受字节前校验租户、项目、用途和权限；跨租户统一 404 |
| 类型校验 | 扩展名、声明 MIME、magic bytes 三者联合；用途白名单；文件名只作展示元数据，不作存储路径 |
| 大小与结构 | 单文件、批次、解压后总量、文件数、嵌套深度、解析时间均配置化 **TBD**；防 zip bomb、XML 外部实体、CSV/Excel 公式注入、路径穿越和符号链接 |
| 恶意文件 | 隔离区恶意文件扫描；命中则拒绝、保留最小安全审计并按事故策略处置；扫描引擎/隔离保留期 **TBD** |
| 脱敏 | 报告/日志入库前走正则 + 字典脱敏；高风险字段优先结构化屏蔽；原件是否可留、谁可看、是否需二次加密 **TBD/法务** |
| 完整性 | 对象保存摘要、来源、版本、classification；外部 manifest 与实际内容不一致拒绝或显式标记失败，不静默截断 |
| 访问 | 默认私有；**Draft 推荐**由后端鉴权后签发短时、单对象、只读 URL；替代为后端代理下载。边界文档已将具体方式列为未决（`frontend_backend_boundary_spec-v1.0.md:345`） |
| 浏览器安全 | 下载响应防 MIME sniffing，用户提供 HTML/SVG 等主动内容不得与主站同源直接渲染；查看器沙箱化 |

### 5.2 制品访问

- Artifact/Evidence 引用不是访问授权。每次签发访问权时重校验当前租户、项目、角色、classification、保留/Legal Hold 状态。
- URL 不包含会话 Token；有效期、下载次数、IP 绑定是否启用均 **TBD**。敏感制品优先后端代理或一次性授权。
- Evidence 导出包记录导出人、范围、时间、摘要、分类和来源；导出不得绕过源对象 ACL。
- Restricted 制品默认不可经普通预签名 URL 分发；候选为受控代理、专用隔离查看环境或禁止导出，待安全评审。

### 5.3 沙箱

上游沙箱规格为 rootless 临时容器、只读基础镜像、默认无网、tmpfs、CPU/内存/磁盘/时间/pids 配额、no-new-privileges、镜像白名单和输入输出扫描（`../01_market_research/market_research.md:100`）。

**Draft 基线**：

- 解析沙箱与测试执行器至少逻辑隔离；不把 AST 黑名单当沙箱；不挂宿主 Docker socket、宿主凭证目录或共享可写工作区。
- 根文件系统只读，仅临时工作区可写；非 root；移除 capabilities；禁止特权容器；默认无网络。需要外网的测试执行按环境级 egress policy 单独授权。
- 输入通过临时对象授权注入，输出只允许写指定目录；输出重新扫描、类型校验、摘要后再入对象存储。
- 容器超时、资源耗尽和异常退出必须落账为明确失败；不得残留运行进程。执行终止信号服务端持久化（`../08_prd/prd.md:129`）。
- **演进候选**：Kubernetes Job + gVisor/Kata/Firecracker、镜像签名、SBOM/漏洞扫描；是否采用取决于风险评估与运维能力，均为 Draft/TBD，不作为当前部署结论。

## 6. 数据分类、模型出站与 Prompt Injection

### 6.1 四级分类

上游四级为 Public / Internal / Confidential / Restricted；Confidential 禁缓存，Restricted 仅本地模型或禁止处理（`../08_prd/prd.md:235`、`../README.md:338`）。

| 级别 | 示例边界（Draft，需数据 Owner 确认） | 模型与存储策略 |
| --- | --- | --- |
| Public | 已批准公开的文档、公开 API 示例 | 可走批准供应商；仍需日志、成本与版本记录 |
| Internal | 企业内部非敏感流程、合成测试数据 | 仅企业批准网关/供应商；按合同和区域策略处理 |
| Confidential | 未公开代码/需求、测试结果、内部 URL、可能含业务数据的日志 | 禁缓存；最小上下文、先脱敏；仅允许明确批准的私有路由；prompt 正文默认不落普通日志 |
| Restricted | 密钥、生产 PII、受监管数据、生产数据、认证材料 | 默认拒绝模型出站；仅批准本地模型或完全禁止；不得用“脱敏失败后继续”降级 |

分类采用“输入、关联证据、历史上下文、工具结果中的最高级别”。脱敏不自动降低分类，只有经批准的不可逆变换和数据 Owner 规则才能降级。分类缺失时 **Draft 推荐按 Confidential fail-close**；替代为直接拒绝 AI 调用，取决于业务可用性评审。

### 6.2 模型出站控制

1. 所有 chat/structured/embed 经 Model Adapter/LLM 工厂唯一出口，并记录 AIInvocationLog；业务代码和 Skill 禁止直连厂商 SDK（`../08_prd/prd.md:226`）。
2. 路由键至少包含 task_type、data_classification、供应商/模型白名单、区域/数据处理条件、成本上限、fallback、prompt/skill 版本。供应商、模型、价格和合同均 **TBD**。
3. 发出前执行分类、授权、最小化、脱敏和策略裁决；响应执行 schema、evidence_refs、敏感输出和内容安全校验。校验失败整批拒收或走明确 fallback，不把不合格响应交给副作用链。
4. Prompt/response 正文默认不进普通日志；调试采样须显式审批、限时、脱敏、限定环境和访问者。
5. Embedding 同样属于模型出站和数据副本；继承分类、租户、删除、Legal Hold 和供应商约束。

### 6.3 Prompt Injection 与间接注入

- System / Policy / Skill / User / Document 分层；Jira 描述、PR 评论、Confluence、上传文件、测试日志、网页 DOM、MCP tool description/result 全部标为不可信数据（`../08_prd/prd.md:181`、`../08_prd/prd.md:186`）。
- 模型不能从文档文本直接构造高风险调用；工具参数由受控 schema 和服务端资源引用生成，Tool Router 后再经过租户/RBAC/Policy Gate。
- 高风险工具永不因模型“声称已获批准”而放行；审批、再认证、param_hash 和当前权限只认平台事实。
- 检索结果继承源 ACL；上下文只取当前授权范围；引用和 provenance 进入 Evidence。
- 注入命中、越权尝试、白名单外工具、连续拒止进入安全事件；终止阈值沿用上游现有“连续 3 次拒绝终止 Agent”要求（`../08_prd/prd.md:155`），但检测规则集与误报处置 **TBD**。
- 上线 Gate 包含恶意 Jira/日志/评论/网页/MCP 样本，要求越权副作用 100% 阻断（`../08_prd/prd.md:247`）。C4 还要求 Restricted 内容不得进入 AI prompt，跨租户 evidence/case_result 访问统一返回 404（`../04_interaction_design/chains/c4_failure_triage.md:181`、`../04_interaction_design/chains/c4_failure_triage.md:182`）。

## 7. 保留、删除、Legal Hold 与 WORM 候选

PRD 提到 Trace/视频默认 90 天，但同时明确“法务确认 TBD”（`../08_prd/prd.md:222`）；Q6 也把制品与审计留存交法务+安全确认（`../08_prd/prd.md:363`）。因此 **90 天不是本分册定稿值**。

### 7.1 Draft 保留矩阵

| 数据类 | 正常保留 | 删除传播 | Legal Hold | WORM 候选 |
| --- | --- | --- | --- | --- |
| 会话/临时草稿/缓存 | TTL **TBD** | 到期清理；缓存与临时对象同步 | 通常不适用，例外 TBD | 否 |
| TestCase/TestRun/结果/配置快照 | 按项目与审计需求 **TBD** | 主库、搜索、向量、导出副本、对象引用 | 可冻结相关 run/版本 | 关键快照摘要候选 |
| Screenshot/Video/Trace/日志/报告 | 生命周期 **TBD**；90 天仅上游假设 | 对象、缩略图、CDN/缓存、索引、临时 URL | Hold 覆盖正常过期 | 关键证据包候选 |
| EvidenceObject | 与所支撑决策/审计期对齐 **TBD** | 删除需保留必要 tombstone/摘要与合法依据 | 必须支持 | 证据导出候选 |
| AuditEvent | 安全/法务期 **TBD** | 原则上不做业务删除；法定删除冲突由法务裁定 | 必须支持 | **优先候选**：对象锁/SIEM 不可变层 |
| AIInvocationLog | 成本与审计期 **TBD**；正文最小化 | 主库、分析仓、向量/缓存、调试样本 | 按事件/主体 Hold | 元数据审计候选 |
| 备份 | 代际与隔离期 **TBD** | 通过备份过期传播；恢复后重放删除清单 | Hold 备份隔离标识 | 不以 WORM 阻断合法删除，策略 TBD |

### 7.2 删除与 Hold 语义

1. **删除请求**先做身份、范围、Legal Hold、依赖和审计判定；生成可追踪删除作业，覆盖 DB、缓存、对象、向量、搜索、导出暂存和后续备份恢复重放。
2. **Legal Hold**优先于正常生命周期和租户删除；创建/解除 Hold 需专门职能授权、四眼候选、原因与范围、全审计。角色、流程和 SLA **TBD/法务**。
3. **WORM 候选**不等于当前 append-only。DB 禁 UPDATE/DELETE 只能提供逻辑不可变；真正防篡改候选是对象锁、独立审计账户/存储、哈希链或企业 SIEM 不可变能力，选型 **TBD**。
4. 删除后的业务对象不应通过向量近邻、缓存、旧预签名 URL 或恢复演练重新出现；恢复流程必须重放删除与 Hold 状态。

## 8. Connector 与外部系统安全可靠性

上游 Connector Contract 包含 Auth/Reader/Action/Webhook/Health/RateLimit-Retry/DataMapper/PermissionMapper，动作声明 Preview/Idempotency/Compensation，写前使用 ETag/版本（`../08_prd/prd.md:230`、`../01_market_research/market_research.md:70`）。

### 8.1 入站 Webhook：HMAC、重放与归属

- 对**原始请求字节**做 HMAC，常量时间比较；secret 为空、GET 请求、调试模式均不得跳过验签。每租户/连接器独立密钥。
- 签名覆盖时间戳、事件 ID、请求体摘要和来源标识；允许时钟窗口 **TBD**。缺时间戳/事件 ID的上游协议需由连接器专门定义补偿控制，不能默认放行。
- 重放存储键至少为 tenant + connector + event_id/body_hash，原子写入并有 TTL；TTL **TBD**。重复事件返回幂等结果，不重复触发 TestRun/外部写。
- 验签后再做仓库/项目/环境归属映射；签名有效不代表有权访问任意租户资源。
- 请求体大小、事件类型、schema 和速率限制配置化；验签失败、重放、归属不匹配写安全审计并告警聚合。

竞品曾存在 secret 为空整段跳过 HMAC，已被列为必须反向做对项（`../02_competitor_analysis/competitor_analysis.md:59`）。

### 8.2 出站 SSRF 与 egress

**Draft 推荐**：仅连接已由管理员审批的 Connector/ExecutionEnvironment 目标；endpoint 保存时校验，调用时再次解析与校验。

- URL 只允许明确协议，默认 HTTPS；TLS 校验必须开启。HTTP 内网例外是否允许 **TBD/安全审批**。
- 规范化 host/port/path，拒绝 userinfo、混淆编码、未允许端口；重定向默认关闭，若启用则每跳重验并限制跳数 **TBD**。
- DNS 在连接时解析；拒绝 loopback、link-local、multicast、云 metadata 和未注册地址。企业 Jenkins 可能使用私网，故**不采用“所有私网一律拒绝”**；替代为管理员批准的内部 DNS/CIDR allowlist + 解析后 IP 校验，防 DNS rebinding。
- egress policy 绑定 connector_id/tenant/environment，不允许任意 URL 参数覆盖已注册 origin；请求日志记录目标标识而非凭证/敏感 query。
- 外部返回内容一律不可信，走大小、类型、脱敏、恶意文件和 Prompt Injection 控制。

### 8.3 幂等、ETag、重试与补偿

| 控制 | Draft 语义 |
| --- | --- |
| 入站幂等 | Webhook event id/body hash 原子去重；相同键不同 request_hash 视为冲突并告警 |
| 工作流幂等 | TestRun external_ci 使用唯一 idempotency_key；故障恢复不得重复触发外部 Job（`../03_problem_modeling/problem_model.md:146`） |
| 审批执行领取 | consume 行锁事务只创建以 approval_request_id + bound_hash 唯一标识的基础设施 execution intent 与 Outbox，不提前写 EXECUTED；重复 consume/Outbox 重投/Worker 重领复用同一意图 |
| 外部写幂等 | tenant + action + target + stable request hash 生成幂等范围；保存 external_request_id 与响应摘要；重试先查询既有结果 |
| ETag/版本 | 读取目标版本→Preview→审批绑定→执行前重读并比较；冲突则失效/重建审批，不覆盖最新外部状态 |
| 重试 | 仅对已知幂等或可安全查询结果的操作自动重试；指数退避、抖动、Retry-After、最大尝试与总时长均 **TBD**；鉴权/权限/Schema/Policy DENY 不重试 |
| 补偿 | 每个可补偿动作显式定义、人工可见、可审计；补偿不是事务回滚，不保证恢复外部世界原状。Jira 不自动删除，生成关闭草稿；CI cancel 幂等 |
| 熔断 | 按连接器/租户/动作隔离；熔断时保留查询、取消、审计和人工恢复路径；阈值 **TBD** |

压测与 Agent 任务禁止自动重试；功能回归的内部重试不新造 TestRun 状态语义（`../04_interaction_design/chains/c3_execution_kickoff.md:286`）。

## 9. 容量、SLO、配额与限流

### 9.1 数值成熟度

PRD 的容量和 SLO 是当前输入，但容量明确标为“假设值，M0 校准”，且多个值为 TBD（`../08_prd/prd.md:280`、`../08_prd/prd.md:287`）。本文不把它们升级为定稿：

| 指标 | 上游当前假设/目标 | 本文状态 |
| --- | --- | --- |
| 注册/活跃用户 | 1000 注册、200 DAU 假设 | Draft，需压测画像与试点数据校准 |
| 只读 API | P95 < 1s（不含模型） | Draft SLO |
| AI 流式生成 | 首 token P95 ≤ 3s | Draft SLO，受企业模型网关影响 |
| A2 分诊 | 10k 用例级 run 完成后 ≤5 分钟 | Draft SLO |
| Check Run 回写 | CI 结束后 ≤2 分钟 | Draft SLO |
| 执行并发 | 接口 50 run、UI 8 slot TBD、压测全局并发 TBD | 假设/TBD，不得当默认配额 |
| 报告解析 | ≥1000 用例结果/分钟 | Draft 容量目标 |

### 9.2 网关限流与业务配额

| 层 | 职责 | 典型维度 |
| --- | --- | --- |
| 企业网关 | HTTP 连接、请求速率、突发、体积、并发连接、SSE 连接、基础 DDoS/WAF | source/identity/route；具体规则 **TBD** |
| 应用认证层 | 用户/ApiToken/租户/项目动作频率；签名失败和登录滥用 | identity + tenant + action |
| AI 预算 | OrgQuota Token 预算、模型路由 max_cost、并发 AI 调用 | tenant + task_type + model route |
| 执行资源 | API run、UI slot、压测并发、场景互斥、外部 CI 使用配额 | tenant/project/environment/case type |
| Connector | 外部系统 rate limit、并发、重试预算、熔断 | connector + tenant + action |
| 文件/解析 | 上传体积、批次、解压预算、解析并发、对象存储带宽 | tenant + project + file purpose |

网关限流不能替代业务配额；上游已裁定 HTTP 限流归网关，但 AI Token 与执行资源配额留平台（`../README.md:306`）。

### 9.3 过载与资源保留

**Draft 降级顺序**：拒绝/排队新的 AI 增强 → 限制新的低优先级解析与执行 → 保持状态查询、审计、证据写入、取消/停止、kill switch、审批拒绝与安全控制可用。不得因系统过载阻塞关停动作或丢失已产生证据。

- 队列按任务类与租户隔离，防单租户占满；公平策略和权重 **TBD**。
- 每个异步任务有最大输入、运行时间、重试预算、死信和人工处理入口；数值 **TBD**。
- WAITING_APPROVAL/WAITING_EXTERNAL 不消费执行 slot，但持续计入滞留观测；不得因等待时间长而隐藏（`../08_prd/prd.md:158`）。
- 配额检查与占用应原子化；释放以终态/租约回收为准；缓存计数不可成为唯一账本。

## 10. 可用性、备份与恢复

架构占位文件当前仅提出“私有化单企业部署起步”和 PostgreSQL/Redis/MinIO 职责，未给部署拓扑或 RPO/RTO（`architecture.md:14`、`architecture.md:15`）。因此本节只定义目标形态与决策 Gate。

### 10.1 可用性 Draft

| 能力 | Draft 要求 | 失败时语义 |
| --- | --- | --- |
| API/治理面 | 无本地唯一状态；支持多实例候选；健康/readiness 区分；滚动升级需兼容在途工作流 | 无法受理新请求时明确失败；已受理任务可恢复 |
| PostgreSQL | 事务事实源；HA、备份、PITR 候选；审批 consume 与幂等依赖其一致性 | DB 不可用时副作用 fail-close；不得降级到无审计写入 |
| Redis | 缓存/限流/短锁，不作工作流唯一状态 | 丢失后可重建；必要限流 fail-safe/fail-close 策略按路由 TBD |
| 对象存储 | Artifact/Evidence 持久层；版本/摘要/生命周期；跨故障域和不可变能力候选 | 上传失败时证据要求未满足的流程不得假装成功 |
| Worker/执行器 | 心跳、租约、持久终止信号、幂等 Activity；worker 隔离 | 失联收敛 TIMEOUT 或由 durable workflow 恢复，不永久 RUNNING |
| Connector | 每连接器健康、熔断、重试、轮询兜底 | 外部系统不可用不影响核心只读/证据；写入显示未决/失败，不假成功 |
| 模型网关 | AI 能力可降级；平台执行/报告/门禁独立 | fallback 或功能置灰并显式横幅（`../08_prd/prd.md:147`） |

### 10.2 备份与恢复

| 数据面 | 备份候选 | 恢复要求 | RPO/RTO |
| --- | --- | --- | --- |
| PostgreSQL | 全量 + 增量/WAL/PITR，独立加密与访问域 | 一致恢复主对象、审批、审计索引；恢复后重放删除/Hold；校验租户隔离 | **TBD** |
| 对象存储 | 版本/复制/对象锁候选 | 校验摘要与引用；孤儿对象盘点；Evidence 链可解析 | **TBD** |
| Vault | 按企业 Vault DR/备份方案 | 不在普通应用备份中导出明文 secret；恢复后轮换/验证租约 | **TBD** |
| Redis | 通常不作为必须恢复事实 | 从 DB/工作流重建；限流和租约安全恢复 | **TBD/可能为 0**，需 SRE 定义 |
| Temporal（若采用） | 持久库 + namespace/visibility 配置备份 | workflow history 可恢复且不重复 Activity；worker 版本兼容 | **TBD** |
| 配置/Prompt/Skill | 版本化资产与批准记录 | 恢复到最后 approved 版本；配置漂移检查 | **TBD** |

**Draft 推荐**先完成业务影响分析，再按数据类定 RPO/RTO，不使用单一平台数字掩盖差异。备份成功不等于可恢复；生产放量前必须做隔离环境恢复演练、应用一致性校验、租户越权回归、在途工作流恢复与外部副作用去重验证。恢复演练频率、保留代际、异地/离线副本均 **TBD**。

## 11. OpenTelemetry、日志、指标、Trace 与告警

市场调研已建议 OpenTelemetry 关联模型、工具和工作流，基础设施监控归企业体系，平台保留业务 trace（`../01_market_research/market_research.md:140`）。

### 11.1 三类记录分工

| 类型 | 用途 | 必备关联 | 禁止/限制 |
| --- | --- | --- | --- |
| AuditEvent | 谁在何租户对何资源做了什么，审批/哈希/证据/结果 | event_id、tenant/project、actor/delegated_agent、workflow/step、action/resource、request/response hash、approval bound_hash、classification、external_request_id、result、evidence_refs、cost/latency | append-only；不得写 secret、完整 Token、默认 prompt 正文 |
| 应用日志 | 调试、错误、状态与依赖事件 | timestamp、service、environment、request/trace/span、tenant 的非敏感稳定标识、error code | 结构化；脱敏；禁止日志成为审计替代；限制高基数字段 |
| OTel Trace | 请求→工作流→Activity→Connector→模型的因果链 | trace_id、span_id、workflow/run/approval/connector 引用 | 不采集敏感正文；外部 trace context 不可信，需格式/长度校验；采样策略 **TBD** |

### 11.2 指标域

- **安全**：认证失败、REQUIRE_REAUTH、RBAC/租户 DENY、四眼违例、HMAC 失败、重放、SSRF 拒绝、恶意文件、Restricted 出站拦截、MCP/Tool 拒止、Vault 失败。
- **可靠性**：API RED 指标、队列深度/年龄、workflow backlog、Activity retry、心跳丢失、TIMEOUT、STOPPING 滞留、WAITING 状态年龄、死信、幂等冲突、补偿失败、恢复点健康。
- **连接器**：按 connector/action 的成功率、延迟、429/5xx、重试、熔断、ETag 冲突、webhook 投递延迟、重复事件。
- **AI**：usage/cost/latency、schema 失败、fallback/降级率、evidence 覆盖、无据结论率、注入拦截、模型路由拒绝；所有调用无旁路。
- **容量/成本**：租户并发、slot 使用、解析吞吐、对象增长、向量增长、Token 预算、每成功工作流成本。

### 11.3 告警与事故响应

| 告警类 | 触发原则 | 初始处置 |
| --- | --- | --- |
| P1 安全 | 未审批外部写、跨租户证据、secret/Restricted 泄露、生产发布执行越界、审计不可用 | 关停相关连接器/能力；保留读取与取证；通知 SRE+安全+平台负责人 |
| P2 AI/治理 | 无据结论率达到上游告警线、Prompt/Skill 回归、持续注入命中、审批/幂等异常 | 回滚版本、收量或禁用能力；保留确定性平台功能 |
| 可靠性 | SLO burn、队列年龄、僵尸/STOPPING、恢复点失败、对象写失败 | 限流/降级/扩容候选，人工接管在途任务 |
| 外部依赖 | Connector 错误/限流/熔断、Vault/IdP/模型网关异常 | 隔离故障域，停止不安全重试，启用明确 fallback |

除 PRD 已给出的 P1 Draft 目标和业务指标外，告警阈值/窗口均 **TBD**，必须由基线与演练校准。

事故流程：检测与分级 → 即时关停/隔离 → 保护证据与时钟 → 指派 Incident Commander → 影响范围与租户判断 → 修复/补偿/凭证轮换 → 恢复前安全 Gate → 通知与审计 → 无责复盘与行动项。关停即时、恢复审批的方向不对称必须在演练中验证。

## 12. 成本、运维边界与 RACI

### 12.1 成本域

成本至少按租户、项目、工作流、AI 能力/模型、执行环境、对象存储、向量、Connector、Temporal（若采用）归集。优先使用真实 usage 和账单/资源数据，不用估算替代真实计量。单价表、分摊规则、成本基线和预算值均 **TBD**（`../08_prd/prd.md:278`）。

**Draft 成本保护**：模型路由 max_cost、OrgQuota、执行 slot、解析并发、对象生命周期、Trace 采样和连接器重试预算；保护顺序不得牺牲审计、证据、取消或 kill switch。

### 12.2 运维边界

| 责任域 | 企业平台/AIOps | HuntAI Test 平台团队 | 外部系统 Owner |
| --- | --- | --- | --- |
| 基础设施 | 主机/K8s/网络/网关/基础 DB 与对象存储平台监控、企业备份能力 | 声明业务需求，消费基础指标，验证恢复 | — |
| 应用与工作流 | 接收平台告警 | API、状态机、队列/Temporal、幂等、心跳、等待态、Evidence/Audit SLO | — |
| 身份/Vault | IdP/Vault 平台可用性与企业策略 | claim/角色映射、会话、credential_ref、应用最小权限 | 身份/凭证 Owner 配合 |
| Connector | 网络与统一 egress 能力 | Connector contract、安全、重试、审计、健康与版本 | Jira/GitHub/CI/Release API、权限和变更通知 |
| 执行环境 | 基础资源与容器平台 | 沙箱、执行器、slot、终止、证据采集 | 企业 CI Job 契约与产物质量 |
| AI | 企业模型网关基础能力 | ModelRoute、Prompt/Skill Gate、AIInvocationLog、质量与成本 | 模型网关 Owner 提供 SLA/合同 |
| 事故 | 企业值班与安全响应 | 业务 IC、kill switch、取证、租户影响、补偿 | 受影响依赖共同响应 |

### 12.3 RACI（角色级 Draft）

| 事项 | R | A | C | I |
| --- | --- | --- | --- | --- |
| 身份/租户/RBAC | 后端/平台工程师 | 平台架构师 | 安全、IdP Owner、QA | 产品 |
| 数据分类/模型出站 | AI 工程师 + 安全工程师 | 安全负责人 | 数据 Owner、法务、模型网关 Owner | 平台负责人 |
| Vault/凭证/Connector | 后端/集成 Owner | 平台架构师 | 安全、外部系统 Owner、SRE | 产品 |
| 沙箱/执行器 | 执行器团队 | 平台架构师 | 安全、SRE、QA | 产品 |
| 保留/Hold/WORM | 安全 + 法务 | 安全负责人 | SRE、数据 Owner、平台架构师 | 平台负责人 |
| SLO/容量/备份恢复 | SRE | 平台负责人 | 架构师、后端、企业基础设施 | 产品/安全 |
| AI/Prompt/Skill 发布 | AI 工程师 | 平台产品负责人 | QA/评测、安全 | SRE |
| 事故响应 | SRE 值班/Incident Commander | 平台负责人 | 安全、产品、外部系统 Owner | 受影响租户 |
| 成本与预算 | 平台管理员 | 平台负责人 | 财务（如涉）、AI/SRE | 部门 Owner |

RACI 人名仍为 PRD Q8 的 M0 待办，不在本文虚构（`../08_prd/prd.md:365`）。

## 13. Temporal POC 运维门槛

上游裁定是 **POC Temporal，Celery + 自建状态机 + 幂等纪律为保底**，原因是长审批、长轮询、中断恢复与“不重复副作用”（`../01_market_research/market_research.md:136`）；PRD Q3 仍未闭环（`../08_prd/prd.md:360`）。

### 13.1 POC 必须证明

1. TestRun 统一 10 态映射不新增/扭曲业务状态；WAITING_APPROVAL/WAITING_EXTERNAL 可长等待、可见、可告警、可人工取消。
2. API/worker/Temporal/DB 分别重启后，workflow 恢复且外部 CI/Jira/Release 不重复副作用。
3. Signal（取消/审批/外部 webhook）持久、可重放、乱序/重复安全；Activity 有明确 timeout、heartbeat、retry 和 idempotency。
4. Worker 版本升级、回滚、workflow versioning 和旧历史兼容可操作；不得要求清空在途任务。
5. 租户 context、classification、actor/request hash 在 workflow/activity 间传播并在执行点重校验；secret value 不进入 workflow history。
6. 可观测：workflow/run/approval/connector trace 关联、task queue backlog、schedule-to-start、Activity retry、stuck workflow 与 visibility 查询可用。
7. 运维：持久库备份恢复、升级、证书/凭证轮换、容量、history/visibility retention、namespace/task queue 权限与故障手册可执行。
8. 成本与人员：自托管/托管候选、值班技能、升级频率、资源成本和单人项目维护负担有实测结论。

### 13.2 放行门槛与替代

**Draft 推荐**：只有上述 8 项及 Gate M1 的混沌/幂等测试通过，才可定稿 Temporal。任何一项无法运维、恢复会重复副作用、secret 进入 history、升级不能兼容在途任务，都不得定稿。

**替代方案**：Celery + PostgreSQL 自建权威状态机 + outbox/inbox + 幂等键 + 持久轮询/信号 + 心跳/僵尸回收。替代方案不是降级安全标准，仍须通过相同重启、重复、乱序、恢复、租户和审计 Gate；Redis/Celery task state 不得成为唯一事实源。

所有 timeout/retry/history retention/task queue 数值均 **TBD**；POC 不产生真实部署配置或依赖变更。

## 14. LangGraph 与 MCP 安全边界

### 14.1 LangGraph

LangGraph 只用于 Copilot/Agent 的受限推理循环，不承担 TestRun 可靠状态机、权限、重试、幂等或审批控制面（`../01_market_research/market_research.md:137`）。

- Agent 每步通过 Tool Router schema 校验、租户/RBAC 和 Policy Gate；未声明动作默认 DENY。
- SkillVersion 必须版本化，manifest 声明 allowedTools、max_steps、超时、sideEffectLevel、modelPolicy 和金标准测试集（`../01_market_research/market_research.md:95`）。
- checkpoint/会话持久化若启用，继承租户、分类、保留与删除策略；不得保存 secret 或 Restricted 原文。
- 模型生成的工具名、参数、URL、资源 ID 都不可信；只接受服务端注册的工具和 schema，资源重新加载并鉴权。
- Summarization/Memory 不得提升权限、丢失安全指令或自动写长期记忆；Memory 设计留 M4，默认不从对话自动抽取长期偏好（`../01_market_research/market_research.md:105`）。

### 14.2 MCP

PRD 明确一期不做 MCP 对外暴露，M4 才评估（`../08_prd/prd.md:73`、`../08_prd/prd.md:303`）。因此当前基线是 **外部 MCP Server/Client 能力默认禁用**。

M4 候选边界：

1. MCP transport 不是信任证明；每个 server、tool、版本、auth、egress 目标和数据等级显式注册并审批，禁止用户任意填写远程 MCP URL。
2. 平台作为 MCP client：只连企业 allowlist server；server/tool description、resource、prompt、result 全部视为不可信内容，进入 Prompt Injection 和数据出站控制。
3. 平台作为 MCP server：调用者身份映射到 tenant/project/role；不接受调用者声明的 tenant；工具层重校验；外部 IDE/Agent 不获得平台会话或 Vault secret。
4. 工具声明 input/output schema、sideEffectLevel、Preview/Idempotency/Compensation；L2/L3 仍走平台审批和再认证，L4 实际执行 DENY。
5. 每次 list/read/call 记录 server/tool/version、actor/delegated_agent、request hash、classification、approval、结果和 evidence；敏感内容不进普通 Trace。
6. 结果大小、超时、并发、重试、递归调用深度、采样/roots 能力均设配置 Gate，数值 **TBD**；禁止 MCP 工具互相递归形成无界 Agent 循环。
7. MCP 依赖/SDK、协议版本与供应链审计须另行批准；当前文档不引入依赖。

## 15. 配置项表（概念级，非真实部署配置）

本表只定义后续配置合同中的**概念键**、Owner 和定稿证据，不给真实值。所有数值默认为 **TBD/无架构默认值**；实际键名、环境变量、Secret 路径和部署载体由后续设计确定，并遵循 `.env` 与 Vault 规则。

| 域 | 概念配置项 | 用途 | Owner | 状态/定稿 Gate |
| --- | --- | --- | --- | --- |
| 身份 | OIDC issuer/client/redirect/scopes/claim mapping | OIDC 信任与身份映射 | IdP Owner + 安全 | Draft/TBD；IdP 联调与 claim 越权测试 |
| 身份 | LDAP endpoint/base/bind ref/group mapping | LDAP 兼容接入 | IdP Owner + 安全 | Candidate/TBD；TLS、禁用传播、组映射测试 |
| 会话 | idle/absolute/refresh/reauth windows | 会话与强认证时效 | 安全 | 数值 TBD；风险评审与会话演练 |
| 会话 | cookie/CSRF/OIDC state policy | 浏览器会话保护 | 后端 + 安全 | Draft；Web 安全测试 |
| 授权 | role/functional-role/action policy version | RBAC/职能/Policy Gate | 安全 + 产品 | Draft；策略表测试全覆盖 |
| 审批 | approval TTL/escalation/reauth threshold | 审批过期与升级 | 产品 + 安全 | 数值 TBD；C2 缺口与演练闭环 |
| 租户 | tenant context/RLS/cache namespace policy | 全层隔离 | 架构师 | Draft；双租户回归 + 连接池测试 |
| Vault | auth method/policy/lease/rotation/revocation | 服务身份与凭证生命周期 | 安全 + SRE | 方案/数值 TBD；轮换撤销演练 |
| 文件 | upload size/type/decompression/parser limits | 上传与解析资源保护 | 后端 + 安全 | 数值 TBD；恶意文件集压测 |
| 文件 | malware scanner/quarantine/object access TTL | 扫描、隔离与访问 | 安全 + SRE | 供应商/数值 TBD；EICAR/隔离演练 |
| 沙箱 | image allowlist/resource/pids/time/network policy | 执行隔离 | 执行器团队 + 安全 | 数值 TBD；逃逸/资源/egress 测试 |
| 数据 | classification rules/default/override workflow | 四级分类 | 数据 Owner + 安全 | Draft；数据盘点与误分级测试 |
| 模型 | provider/model/region/classification allowlist | 模型出站路由 | AI + 安全 | 全部 TBD；合同、安全和质量 Gate |
| 模型 | prompt logging/cache/retention/redaction policy | AI 正文与缓存 | AI + 安全/法务 | Draft/TBD；泄露测试 |
| 注入 | injection rules/refusal/termination policy | Prompt/MCP/Tool 防护 | 安全 + AI | 规则 TBD；注入套件 100% 越权阻断 |
| 保留 | per-data-class retention/delete propagation | 生命周期与删除 | 法务 + 安全 | 数值 TBD；Q6 + 删除演练 |
| Hold | legal hold scope/approval/release | 法务冻结 | 法务 + 安全 | 流程 TBD；法务批准 |
| WORM | audit/evidence immutable target/retention | 防篡改候选 | 安全 + SRE | Candidate/TBD；法务/恢复/成本评审 |
| Webhook | HMAC algorithms/key refs/clock/replay windows | 验签与防重放 | 集成 Owner + 安全 | 算法/数值 TBD；绕过/重放测试 |
| Egress | connector DNS/CIDR/port/redirect/TLS policy | SSRF 与出站控制 | 网络 + 安全 | Draft/TBD；DNS rebinding/metadata 测试 |
| Connector | timeout/retry/backoff/jitter/circuit budgets | 外部调用可靠性 | 集成 Owner + SRE | 数值 TBD；限流/5xx/未决结果演练 |
| Connector | ETag/idempotency/compensation contract | 并发写与副作用 | 集成 Owner | Draft；contract test |
| 网关 | route/rate/burst/body/SSE limits | HTTP 入口保护 | 网关 Owner | 数值 TBD；容量压测 |
| 配额 | AI token/API run/UI slot/perf/connector quotas | 业务资源治理 | 平台管理员 + SRE | 数值 TBD；试点校准 |
| 工作流 | heartbeat/zombie/wait/stopping thresholds | TestRun 收敛与滞留告警 | SRE + 架构师 | 数值 TBD；混沌测试 |
| 工作流 | activity timeout/retry/idempotency/history | Temporal/Celery POC | 架构师 + SRE | 全部 TBD；POC Gate |
| 备份 | backup/PITR/replication/encryption/retention | 数据保护 | SRE + 安全 | 数值/拓扑 TBD；恢复演练 |
| 恢复 | service/data-class RPO/RTO | 业务连续性 | 平台负责人 + SRE | **TBD**；BIA 与演练批准 |
| OTel | propagation/sampling/attribute/redaction/export | Trace 与观测 | SRE + 安全 | 数值/后端 TBD；敏感字段检查 |
| 日志 | levels/retention/redaction/SIEM routing | 调试与安全分析 | SRE + 安全/法务 | 数值 TBD；查询与删除/Hold 测试 |
| 告警 | SLO burn/queue/security/AI/connector rules | 事故检测 | SRE + 安全 | 阈值 TBD；演练校准 |
| 成本 | price table/allocation/budget/alert policy | 成本归集与熔断 | 平台管理员 | 单价/基线 TBD；账单对账 |
| MCP | enabled/server/tool/version/egress/data allowlist | M4 MCP 边界 | 安全 + 架构师 | 默认禁用候选；M4 独立评审 |

## 16. 冲突与缺失：推荐及替代

| # | 冲突/缺失 | Draft 推荐 | 替代方案 | 状态 |
| --- | --- | --- | --- | --- |
| C-01 | SQLite 开发决策与 PostgreSQL 多租户/pgvector 事实源冲突（`../../README.md:47` vs `../08_prd/prd.md:221`） | M0 安全/并发/恢复验收统一 PostgreSQL | SQLite 仅单元/本地便利，集成 Gate 在 PG 重跑 | Draft，待总架构定稿 |
| C-02 | C1/C2/C3 个别旧图仍写审批过期→CANCELLED（`../04_interaction_design/chains/c1_north_star_quality_loop.md:180`、`../04_interaction_design/chains/c2_approval_chain.md:161`），但回写与建模裁定为过期停 WAITING_APPROVAL（`../03_problem_modeling/problem_model.md:178`、`../04_interaction_design/chains/c2_approval_chain.md:261`） | 采用最新裁定：过期不迁移、不放行，可重新提交或人工取消 | 若产品要过期自动取消，必须先走上游变更流程并同步状态机/交互/API | Draft 解释，不改上游 |
| C-03 | release_push 在 C1 被写 L3（`../04_interaction_design/chains/c1_north_star_quality_loop.md:278`），建模冻结表为 L4（`../03_problem_modeling/problem_model.md:220`） | 视为 L4 风险域的“仅准备”动作：强审批；实际发布执行 DENY | 将“准备”单独建 L3 需上游统一改级并证明不触发发布 | Draft，采用较新冻结表 |
| C-04 | 制品 90 天与法务 TBD 并存（`../08_prd/prd.md:222`、`../08_prd/prd.md:363`） | 不把 90 天写成部署默认；法务确认后按数据类定值 | 试点临时值须显式批准、限环境并记录到期复核 | TBD，阻断正式放量 |
| C-05 | OIDC/LDAP 被列为候选，但 IdP、MFA、claim、会话与禁用传播未定义 | OIDC 主路径，LDAP 经身份代理优先 | 平台直连 LDAP | TBD，阻断认证定稿 |
| C-06 | RPO/RTO、备份拓扑和恢复演练频率缺失 | 先 BIA，按数据类定 RPO/RTO并演练 | 单一平台目标仅可作临时假设 | TBD，阻断生产恢复 Gate |
| C-07 | Artifact/导出访问方式缺失（`frontend_backend_boundary_spec-v1.0.md:345`） | 后端鉴权后短时单对象 URL，Restricted 走代理/隔离查看候选 | 全部后端代理下载 | Draft/TBD，API 契约收口 |
| C-08 | Legal Hold/WORM 未在上游定义 | 法务+安全设计 Hold；Audit/Evidence 评估对象锁/SIEM 不可变层 | 仅 append-only DB，但不得宣称满足 WORM | TBD，法务 Gate |
| C-09 | HMAC 时间窗/重放 TTL、SSRF 内网例外、重试预算无数值 | 全部配置化，经威胁测试和依赖实测定值 | 系统级统一值，但必须证明适配各 Connector | TBD，不虚构默认 |
| C-10 | Temporal POC 未结论（`../08_prd/prd.md:360`） | 通过 §13 运维/恢复/幂等 Gate 后再定 | Celery + PG 权威状态机，过同等 Gate | TBD，M0 第 4 周目标沿上游 |
| C-11 | MCP 在愿景中存在但一期明确不做 | 当前默认禁用；M4 独立威胁建模、依赖审计和 Gate | 不启用 MCP，只保留内部 Connector/Tool Router | Draft，M4 前不放行 |
| C-12 | 容量/SLO 有假设值但无我方基线 | 保留为 Draft 目标，M0/M1 压测与试点校准 | 使用更保守临时限额，但必须显式标临时 | TBD，不作为定稿 |

## 17. 验证 Gate

任一 Gate 失败均不得以“仅内部平台”为由豁免。具体验证命令、测试数据和执行人由后续测试阶段落地；测试数据必须为合成/脱敏数据，遵守 AI 红线（`../00_setup/project_rules.md:126`）。

| Gate | 必须证明 | 证据/阻断条件 |
| --- | --- | --- |
| G-01 身份与会话 | OIDC/LDAP 候选登录、登出、禁用、会话轮换、CSRF、回调、Token 不落前端；再认证不绕审批 | 越权/失效会话仍可操作即阻断 |
| G-02 租户隔离 | DB/ORM/RLS 候选、缓存、队列、对象、向量、异步、审计、导出、备份恢复的双租户互访 100% 阻断 | 任一路径泄露存在性或数据即 P1 阻断 |
| G-03 RBAC/持续授权 | 项目角色+职能资格；工作流恢复、审批 consume、制品/MCP/Tool 调用前重校验 | 旧角色快照可继续副作用即阻断 |
| G-04 四眼/再认证/TOCTOU | 自批拒绝、并发双 consume 只产生一个 execution intent、参数变化失效、L3+ 再认证、过期不放行 | 外部误写必须为 0 |
| G-05 Vault/凭证 | 无明文落 DB/日志/Trace/Prompt；轮换、撤销、Vault 故障 fail-close；HMAC 空 secret 不绕过 | gitleaks/日志扫描/撤销演练失败即阻断 |
| G-06 文件/沙箱 | 类型伪造、zip bomb、XXE、路径穿越、恶意文件、资源耗尽、网络外带、输出恶意内容、容器残留 | 沙箱逃逸/宿主访问/未扫描入库即阻断 |
| G-07 数据与 AI | 四级路由、Restricted 拒绝/本地、Confidential 禁缓存、prompt 正文默认不落普通日志、schema/evidence 校验 | Restricted 出站或 AI 调用旁路即阻断 |
| G-08 Prompt/Agent/MCP | 注入套件、白名单外工具、越权资源、恶意 tool description/result、max_steps、持久终止 | 越权副作用拦截率必须 100%；MCP 未批准保持禁用 |
| G-09 Connector | HMAC、重放、归属、SSRF/DNS rebinding/metadata、TLS、ETag、幂等、调用前/后崩溃、响应丢失、429/5xx/超时、补偿 | 重启/重试重复触发或重复写即阻断 |
| G-10 状态与可靠性 | 所有 TestRun 边、等待可见、STOPPING 兜底、心跳 TIMEOUT、进程/worker/DB 恢复 | 永久 RUNNING、状态假绿、丢证据即阻断 |
| G-11 Temporal POC | §13 八项：恢复、Signal、Activity、版本升级、租户、安全、观测、运维成本 | 未通过则不得定稿，切保底方案重测 |
| G-12 容量/SLO/限流 | 假设负载、突发、单租户占用、超大报告、对象增长、网关与业务配额、降级顺序 | 过载导致 kill/取消/审计/证据不可用即阻断 |
| G-13 备份恢复 | PG/对象/Vault/工作流恢复、摘要一致、租户隔离、删除/Hold 重放、外部副作用不重复 | 未完成隔离恢复演练或 RPO/RTO 未定即阻断正式生产 |
| G-14 OTel/告警/事故 | Trace 关联、敏感字段检查、P1/P2/可靠性告警、kill switch 关停与审批恢复、SIEM | P1 无告警/无取证/关停受阻即阻断 |
| G-15 保留/删除/Hold/WORM | 生命周期、删除全副本传播、Hold 优先、恢复后不复活、WORM 候选能力实测 | Q6 未闭环阻断正式保留策略定稿 |
| G-16 成本与 RACI | usage 对账、每工作流成本、预算熔断、值班/Owner/人名、外部依赖升级通知 | 无 Owner、无值班或预算不可执行即阻断放量 |

## 18. 关键结论与行号追溯

| 关键结论 | 上游依据（相对路径:行号） |
| --- | --- |
| 前端不是权限、状态或外部调用安全边界 | `frontend_backend_boundary_spec-v1.0.md:17`、`frontend_backend_boundary_spec-v1.0.md:18`、`frontend_backend_boundary_spec-v1.0.md:19` |
| 所有核心表强制 tenant_id；无租户上下文拒绝；跨租户返回 404 | `../03_problem_modeling/problem_model.md:97`、`../08_prd/prd.md:151` |
| SSO 候选 OIDC/LDAP，角色为 owner/admin/tester/viewer | `../08_prd/prd.md:107` |
| REQUIRE_REAUTH 用于 L3+ 过再认证窗口或强认证资源 | `../08_prd/prd.md:111` |
| 四眼原则、参数哈希、执行前复核和单次 consume | `../03_problem_modeling/problem_model.md:193`、`../03_problem_modeling/problem_model.md:195`、`../03_problem_modeling/problem_model.md:199` |
| 审批过期不自动放行，TestRun 停 WAITING_APPROVAL | `../03_problem_modeling/problem_model.md:178`、`../08_prd/prd.md:148` |
| 凭证只存 Vault 引用，前端不持有外部凭证 | `../03_problem_modeling/problem_model.md:228`、`frontend_backend_boundary_spec-v1.0.md:19` |
| Restricted 仅本地模型或拒绝，Confidential 禁缓存 | `../08_prd/prd.md:235` |
| Prompt Injection 将外部内容视为不可信数据，工具参数结构化；Restricted 不进 AI prompt | `../08_prd/prd.md:181`、`../08_prd/prd.md:186`、`../README.md:373`、`../04_interaction_design/chains/c4_failure_triage.md:181` |
| 沙箱要求 rootless、临时、只读、默认无网、资源限制和扫描 | `../01_market_research/market_research.md:100`、`../01_market_research/market_research.md:102` |
| HMAC 必须无例外，外部写需幂等与补偿 | `../README.md:363`、`../README.md:374` |
| Connector 使用 ETag、幂等、补偿、统一返回与 Vault 引用 | `../08_prd/prd.md:230`、`../01_market_research/market_research.md:70` |
| HTTP 限流归网关，AI Token 与执行配额归平台 | `../README.md:306` |
| 容量是假设值、多个数值 TBD | `../08_prd/prd.md:287`、`../08_prd/prd.md:289` |
| Redis 不作工作流唯一状态；存储为 PG/Redis/S3 | `../08_prd/prd.md:221` |
| OTel 关联模型/工具/工作流，基础设施监控归企业体系 | `../01_market_research/market_research.md:140` |
| P1 为外部误写/泄露；关停即时、恢复审批 | `../08_prd/prd.md:343`、`../08_prd/prd.md:347` |
| Temporal 仅 POC，Celery+状态机为保底 | `../01_market_research/market_research.md:136`、`../08_prd/prd.md:360` |
| LangGraph 不作业务工作流控制面 | `../01_market_research/market_research.md:137` |
| MCP 对外暴露一期不做，M4 评估 | `../08_prd/prd.md:73`、`../08_prd/prd.md:303` |
| 制品 90 天仍待法务确认，不是本分册定稿值 | `../08_prd/prd.md:222`、`../08_prd/prd.md:363` |
| RACI 目前只有角色级，人名待 M0 指派 | `../08_prd/prd.md:305`、`../08_prd/prd.md:365` |

## 19. Draft 收口

本文完成安全、可靠性与运维的架构草案，但不代表 Stage 6 总架构批准。以下项目仍阻断相应定稿：IdP 与会话数值、职能角色映射、PostgreSQL/RLS 决策、Artifact 访问契约、Vault 与扫描方案、保留/删除/Legal Hold/WORM、Connector 时间窗与重试预算、容量/SLO 校准、RPO/RTO、Temporal POC、MCP M4 评审、告警阈值、RACI 人名与值班安排。

任何需要推翻冻结上游结论的选择，必须先走 `docs/13_changes/` 变更流程；本文仅记录冲突、推荐和替代，不回写上游、不标批准（`../00_setup/project_rules.md:130`）。
