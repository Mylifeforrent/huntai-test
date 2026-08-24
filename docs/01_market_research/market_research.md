# 03 · 借鉴「企业研发 AI 助手研究包」——AI 自动化测试设计增强（Stage 3 · 市场调研）

> - **日期**：2026-08-23
> - **流程定位**：开发流程图 Stage 3「市场调研」产出链——研究包本体在 references/（源仓库 opensource-product-analysis：references/enterprise_ai_dev_assistant_research_2026-07-28/），本文档是其到我方平台的借鉴消费结论
> - **来源**：references/enterprise_ai_dev_assistant_research_2026-07-28/（源仓库 opensource-product-analysis：references/enterprise_ai_dev_assistant_research_2026-07-28/）（快照 2026-07-28，含 10 份 docs、5 张图、5 个示例、3 份数据）
> - **目的**：平台按模块化设计开发，**当前先攻克 AI 自动化测试**；本文档把研究包中与 AI 自动化测试相关、可借鉴的机制逐项映射到 [README.md](../README.md) 的既有决策上（新增 / 强化 / 修订），其余模块（Copilot / Release 已在 README 第 5 章，其余后置）只做索引。
> - **一句话结论**：研究包是 huntai-test 的「母体愿景」，其最有价值的可借鉴资产不是某个功能，而是一套**治理骨架**——副作用分级、持久工作流、Evidence 一等对象、参数哈希绑定审批、模型路由与数据分类、以「被接受的受控工作流」为北极星的评测体系。

---

## 1. 研究包与 huntai-test 的模块映射（范围裁定）

| 研究包模块 | huntai-test 落点 | 状态 |
| --- | --- | --- |
| 模块 A · Project Workspace | 集成中心 / 项目映射（Jira 同步已裁定） | 部分覆盖 |
| 模块 B · 日常研发助手（Chat + Skills） | README 5.2 全局 Copilot | 已纳入，本次增强 Skill 模型（3.11） |
| **模块 C · 自动化测试中心** | **三域执行 + 归因（README 第 4 章）** | **本次重点增强（3.2 / 3.5 / 3.14）** |
| 模块 D · Release Assistant | README 5.1 Release 模块 | 已纳入 |
| 模块 E · Admin Console | 平台管理（模型路由 / 预算 / 审计） | 本次增强（3.9 / 3.16） |
| Workflow Builder / Software Catalog / Marketplace / 多租户计费 | README 第 10 章不做清单 | 一致，不采纳 |
| 市场调研 / 竞品分析（Rovo、Copilot、Port 等）/ GTM / 定价 | — | 内部平台无商业化，不采纳（见第 5 节） |

**模块化排序确认**：AI 自动化测试（README M0–M3 主线）→ Copilot / Release（M3 起）→ 研究包其余愿景（V1+ 后置）。研究包的 Discovery 建议（收集 30–50 个历史测试样本、建立基线耗时指标）应在本模块开工前完成。

---

## 2. 关键架构裁定：执行面与治理面分离

研究包的核心立场是「**Jenkins 是执行面，正式测试不进 AI Sandbox，AI 只做触发/轮询/归一化/分诊**」。huntai-test 自建三域执行器，两条立场按如下方式统一：

1. **第一执行面：平台自建执行器**（接口 / Playwright / Locust-k6）——三域测试资产与执行是本平台的核心，此点不因研究包而改变；
2. **第二执行面：企业 CI/CD 存量测试 Job**——通过 Connector 接入：触发（带参数 Schema 校验 + 幂等键）→ 持久轮询 → 拉取 JUnit / Allure / Playwright / Pytest 报告与控制台日志 → **归一化为统一 TestRun 模型**，进入与第一执行面同一套 AI 分诊与证据层。平台侧以**引用型用例（Mock 型）**承载（v1.4 强化）：不迁移脚本，用例实体 = Job 引用 + 参数 + 采集配置；执行环境（平台执行器 / Jenkins 实例）为一等注册对象，Job 契约直接采纳研究包 Jenkins Job Contract（见 README 4.0 执行环境维度）；
3. **治理面统一**：工作流状态机、副作用分级、Policy Gate、审批、Evidence、审计对两个执行面一视同仁；
4. **AI 边界原则保留并转译**：「AI 不运行正式测试」→ AI 只在受限节点完成理解、分类、生成、候选计划，**不决定业务控制流、重试、幂等和权限**（业务代码不直接调厂商 SDK，LLM 循环不承担可靠性职责）。
5. **Agent Mode 的定位（v1.2 补充，对应 README 4.0 双执行模式）**：Agent Mode（Skill → Agent → Tool/浏览器动态执行）是「受限推理节点」向**单用例步骤执行层**的延伸——动态性限于步骤级，流程编排 / 重试 / 幂等 / 权限仍在治理面；结果默认不进门禁，**「AI 不运行正式测试」据此转译为「正式门禁与发布证据只采信 Script Mode」**；Agent Mode 的价值出口是把执行轨迹固化为脚本草稿回流 Script Mode。

**新增能力项**：存量 CI 测试报告接入是研究包带来的、README 原来没有的能力——企业已有大量 Jenkins/GitHub Actions 上的测试资产，不必迁移即可纳入统一分诊与发布证据（已落入 README 路线图 M2）。

---

## 3. 可借鉴机制清单（逐项映射）

格式：**机制** → 研究包出处 → huntai-test 落点 → 对 README 的影响。

### 3.1 产品原则七条
出处：`docs/03_产品战略与PRD.md` §1。
「Workflow first, Chat second」「AI proposes, policy decides, workflow executes」「Every side effect is attributable」「Evidence over eloquence」「Progressive autonomy」「模型与工具中立」「Jenkins is execution plane」。
→ 已精选六条写入 README 第 1 章「产品原则」（第 7 条并入 5.2 模型配置中心；第 8 条按第 2 节转译）。**新增**。

### 3.2 Test Center 标准流程与失败聚类
出处：`docs/03` §2.3、`diagrams/02_test_center_workflow.mmd`、`examples/workflow-test-center.yaml`。
11 步流程：选项目/测试包 → 校验元数据 → 选已批准 Job → 触发 → 持久轮询 → 拉取报告/日志/附件 → 归一化 Test Run/Suite/Case/Failure/Artifact → **AI 失败聚类 + 阻塞判断（release blocker）+ 与历史运行对比** → 用户审阅修正 → 生成 Jira/Confluence 更新与 Release Evidence → 逐项批准写入。界面必须显示：原始证据链接、模型置信度、无法判断项、用户修改历史。
→ huntai-test 落点：**把现有「单用例归因」升级为「run 级分诊」**——失败聚类（cluster）比逐条归因更接近 Test Lead 真实决策（15 分钟内判断是否阻塞发布）；验收指标「失败用例解析准确率 ≥ 98%」针对确定性解析器，与 AI 分开考核。**强化**（README M1/M2 已更新措辞）。

### 3.3 副作用五级模型 L0–L4
出处：`docs/04_系统架构设计.md` §3.1。
L0 只读 / L1 平台内草稿 / L2 外部系统非生产写 / L3 触发正式测试或变更审批 / L4 生产发布·邮件·删除。MVP：L0 默认允许、L1 允许可追溯、L2/L3 必须审批、L4 禁止或仅草稿。
→ 升级 README 中分散的「AI 写操作」规则为**统一分级制度**，所有工具/技能/动作声明 sideEffectLevel，Policy Gate 按级裁决（ALLOW/DENY/REQUIRE_APPROVAL/REQUIRE_REAUTH）。**新增**（README 7.9）。

### 3.4 持久工作流执行模型
出处：`docs/04` §3、`docs/06_技术栈设计.md` §5。
状态机 `DRAFT→VALIDATING→RUNNING→WAITING_EXTERNAL→WAITING_APPROVAL→SUCCEEDED/FAILED/CANCELLED`；每个步骤声明 type / input-output schema / timeout / retry / idempotency_key / side_effect / **compensation** / approval_policy / evidence_requirements / visibility / data_classification。
→ 与 README 已借鉴的 TestHub 性能 8 态模型**合并为平台统一执行模型**；「故障重启不重复副作用」列为技术 Gate。技术选型裁定见第 4 节。**强化**（README 7.10）。

### 3.5 Evidence 一等对象
出处：`docs/04` §2.2 Evidence Service。
`claim → evidence_link → source_object → connector/resource/version/timestamp`，Evidence 是一等对象而不是文本里塞 URL；配套指标：证据覆盖率 ≥ 95%、无据结论率（Unsupported Claim Rate）< 2%。
→ 把 README 的「执行证据链（截图/视频/Trace）」从 UI 域**升级为全域**：AI 的一切关键结论（归因、聚类、门禁解读、release notes 字段）都挂 Evidence 引用。**强化**（README 7.11）。

### 3.6 Connector Action Contract
出处：`docs/04` §4、`examples/connector-contract.yaml`。
每个 Connector 八组件：Auth Provider / Resource Reader / Action Provider / Webhook Adapter / Health Check / Rate Limit-Retry / Data Mapper / Permission Mapper；统一返回 `{status, resource_refs, evidence, raw_artifact_ref, external_request_id, warnings}`；动作声明 supportsPreview / supportsIdempotency / supportsCompensation（如 jenkins.job.cancel）；凭证只存引用、运行时从 Vault 取；写前 ETag/版本防并发覆盖。
→ 直接作为 README「集成中心」的**连接器开发规范**：Jira / GitHub / Release 系统 / CI 全部按此实现，contract test + mock server 进 CI。**强化**。

### 3.7 审批参数哈希绑定 + 审批界面九要素
出处：`docs/07_安全治理与评测.md` §2 副作用、`examples/workflow-test-center.yaml`（bindInputHash）。
Preview 与 Execute 参数生成哈希，**审批绑定该哈希，参数变化审批即失效**（anti-TOCTOU）；审批后执行前重新校验权限。审批界面必须展示：动作、目标资源、前后 diff、数据来源、模型与 Skill 版本、风险等级、成本估计、回滚/补偿能力、参数哈希。
→ 升级 README 安全清单第 7 条（diff→确认→快照→回滚）补上**参数哈希绑定**这一环；也是 5.2 Copilot「六件事」的补强。**强化**（README 9.12）。

### 3.8 Prompt Injection 防护
出处：`docs/07` §4。
外部内容（Jira 描述 / PR 评论 / Confluence / 测试日志）标记为不可信数据、不视为系统指令；System/Policy/Skill/User/Document 分层；工具参数由结构化对象生成、不直接复制文档指令；高风险工具不由模型直接执行；读取内容与执行工具之间强制 Policy Gate；建立恶意内容注入测试集。
→ README 原来没有的维度，Copilot / AI 归因 / RAG 全都会消费外部不可信内容，**必须补**。**新增**（README 9.13）。

### 3.9 模型路由 + 数据分类
出处：`docs/07` §2 数据、`examples/model-routing.yaml`。
数据四分级 Public/Internal/Confidential/Restricted；每条路由声明可处理数据等级、地域、成本上限、供应商白名单、fallback；策略：requirePromptVersion / requireStructuredOutputForSideEffects / cacheConfidentialData:false / logPromptBody:false；Restricted 仅本地模型或禁止处理。
→ 落到 Model Adapter 与 AI 调用日志：**按数据分级路由 + 脱敏策略**，与部门 Token 预算（配额）配合。**新增**（README 7.12）。

### 3.10 结构化输出优先
出处：`docs/06` §7。
所有关键生成直接输出结构化对象（TestSummary / FailureCluster / ReleaseChange / ChecklistResult / JiraUpdateDraft / EvidenceClaim…），渲染层再转 Markdown——而非生成 Markdown 再解析。
→ 落到所有 AI 生成物（用例、归因、聚类、release notes、Jira 草稿）：Pydantic/JSON Schema 校验后才允许进入审阅与写回链路；「requireStructuredOutputForSideEffects」作为策略默认开启。**强化**。

### 3.11 版本化 Skill 包模型
出处：`docs/03` §9、`examples/skill-manifest.yaml`。
Skill = 版本化能力包而非一段 Prompt：manifest + instructions + 输入/输出 Schema + allowedActions 白名单 + sideEffectLevel + modelPolicy（maxCost / 数据分级 / 供应商白名单）+ 超时重试 + 沙箱策略 + **金标准测试集** + Owner/版本/发布状态/审批人；三级发布：个人（项目内）→ 团队（Owner 审核）→ 组织（管理员 + 安全审核）。
→ 升级 README 5.2 Skills 体系：比原「manifest 声明式」更完整的规范，特别是 **allowedActions 白名单 + modelPolicy + 自带评测集** 三件。**强化**（README 5.2 已更新）。

### 3.12 Sandbox 具体规格
出处：`docs/04` §7、`docs/06` §11。
MVP：rootless Docker、临时容器、只读基础镜像、CPU/内存/磁盘/时间/pids 配额、默认无网络、tmpfs 工作区、no-new-privileges、镜像白名单、输入输出恶意文件扫描、文件经对象存储临时 URL 注入；长期：K8s Jobs、gVisor/Kata/Firecracker、cosign 签名 + SBOM/Trivy。
→ 把 README 安全清单第 1 条「容器沙箱」落成**可执行规格**；明确「Sandbox 只做数据加工（日志解析/XML/Excel），不运行正式测试」。**强化**。

### 3.13 Memory 三层策略
出处：`docs/03` §8。
User Memory 仅存用户显式确认的偏好；Project Memory 由管理员管理、带版本；Knowledge 由 Connector 同步并**继承源系统 ACL**；每条 Memory 有 owner/scope/source/confidence/过期；默认不从对话自动抽取写入长期记忆。
→ README M4 RAG / Copilot 的记忆设计基线，防止「Memory 保存不该保存的信息」。**新增索引**（细节到 M4 设计再展开）。

### 3.14 评测与 KPI 体系
出处：`docs/07` §6、`data/kpi_framework.csv`、`docs/05` Gate M1/M2。
北极星重定义：**「每周成功完成、被用户接受且产生可验证业务结果的受控工作流数量」**——不以对话次数 / Token 数 / 生成字数衡量价值。Test Center 指标：解析准确率 ≥ 98%、失败聚类 purity/coverage、blocking 判断准确率、历史相似失败召回、无据结论率 < 2%、证据覆盖率 ≥ 95%、首次接受率 ≥ 80%、越权副作用 = 0、审批反悔率 < 1%、中位分诊耗时 -50%。Gate M1（技术闭环）：重启不重复副作用、AI 结论全量挂证据、越权测试全阻断；Gate M2（业务价值）：分析耗时 -50%、Release 准备 -40%、30 天 ≥ 100 次成功工作流、外部误写 0。
→ README 路线图验收从「功能验收」升级为 **Gate 制 + 北极星指标**（内部场景把 Release 指标留给 Release 模块）。**强化**（README 8 章 Gate 段已加）。

### 3.15 AI 资产发布门禁
出处：`docs/07` §7。
任何 Skill / Workflow / Prompt / ModelRoute 升级进生产前十步：schema test → unit/contract → golden dataset → 安全注入套件 → 权限测试 → 成本/延迟回归 → shadow/canary → Owner+安全审批 → 版本锁定 → 回滚计划。
→ 落到 README M4 的 Prompt 版本化 / A/B：**A/B 不是上线手段而是门禁流程的一环**；「未版本化 Prompt/Skill/Workflow 不得进生产」写为安全底线。**强化**。

### 3.16 审计事件 Schema
出处：`examples/audit-event.json`。
字段：event_id/timestamp、tenant/project、actor_user/**delegated_agent**、workflow/step、skill+version、model/provider/**prompt_version**、tool/action/resource、**request_hash/response_hash**、approval{id, decision, **bound_hash**}、data_classification、external_request_id、result、evidence_refs、cost/latency。
→ 比 README 已借鉴的 WHartTest 七字段更完整：补上**代理身份、参数哈希、审批绑定哈希、数据分级、证据引用、成本延迟**；append-only、关键事件外发 SIEM。**强化**。

### 3.17 团队与风险提示
出处：`docs/05` §7、`docs/09_风险与待决策清单.md`。
MVP 7–9 人（Product/Tech Lead/后端×2/前端×1-2/AI×1/平台安全×1/评测×1）；**「企业 Connector 往往比模型功能更耗时，不应低估后端与集成投入」**；风险表：Connector 工作量失控→标准 Action Contract；「AI 摘要正确但业务不采用」→固定页面 + 流程嵌入 + 接受率指标；自研 Runtime 过度→只自研语义层。
→ 内部平台转译：集成中心（Jira/GitHub/Release/CI 四连接器）的工作量按**不少于三域执行器**估算；「不被采用」风险用北极星 + 首次接受率监控。**新增提示**。

---

## 4. 技术选型修订建议

| 议题 | 研究包建议 | README 原决策 | 修订裁定 |
| --- | --- | --- | --- |
| 执行编排 | Temporal（durable workflow：长审批/轮询/中断恢复/信号）；明确「不建议只用 Celery/RQ 承担长审批与可靠状态」 | Celery/Arq 任务队列 | **POC Temporal**：TestRun 生命周期含 WAITING_APPROVAL/WAITING_EXTERNAL 长等待与「重启不重复副作用」硬要求，Celery 表达吃力；若团队评估运维成本高，保底方案 = Celery + 自建状态机 + 幂等键纪律（必须通过 Gate M1） |
| Agent 框架 | LangGraph 等只作单点受限推理节点，不作业务控制面 | LangGraph create_agent 形态（5.2 Copilot） | 一致：Copilot 用 Agent 循环，**业务工作流不用**；两层不混 |
| 向量检索 | PostgreSQL + pgvector 起步，超需求再上专用向量库 | Qdrant + BM25 + Reranker 混合检索（借鉴 WHartTest） | **修订为分阶段**：MVP 用 pgvector + PG 全文混合检索（内部规模够用、少一个组件）；Qdrant+Reranker 保留为知识量/权限过滤超载后的演进方向 |
| Web/API 框架 | FastAPI + Pydantic，一切结构化对象过 Schema | 未明确 | 采纳：结构化输出优先（3.10）的技术前提 |
| 可观测 | OpenTelemetry 统一 trace（模型/工具/工作流三域关联） | 未明确 | 采纳：与 AIOps 边界裁定兼容——平台自身业务 trace 自持，基础设施监控归企业体系 |
| 数据库/存储 | PostgreSQL / Redis（不作工作流唯一状态）/ S3-MinIO / Vault | MinIO/S3 已有 | 一致；**新增**：Secrets 只存 credential reference，运行时从 Vault 取 |

---

## 5. 低相关 / 不采纳内容及理由

| 内容 | 理由 |
| --- | --- |
| 市场调研、ICP、GTM、定价、PoC 销售（docs/01、08） | 内部平台无商业化场景 |
| 竞品分析（Rovo Dev / Copilot / GitLab Duo / Port / Harness / Backstage / Amazon Q，docs/02） | 属研发助手赛道的竞争判断，与测试平台建设无直接关系；仅「集成而非对抗」的思路与 README 结论三一致 |
| Workflow Builder、Software Catalog/Scorecard、Marketplace、Agent Registry | 与 README 第 10 章不做清单一致；Builder 准入条件（≥10 个生产模板、70% 可组合）可作远期参考 |
| 多租户计费 / SaaS 双形态 | 内部多租户已裁定砍掉计费 |
| 「Jenkins 是唯一执行面」原始表述 | 按第 2 节转译为「执行面与治理面分离」，平台自建执行器为主、CI 存量 Job 为第二执行面 |
| Kill Criteria 商业条款 | 内部场景转译为价值检验：两个试点部门后首次接受率仍 < 60% 或流程频率过低，应重定位投入 |

---

## 6. README 更新落点索引（本次 v1.2 变更）

| README 位置 | 变更 | 对应本文 |
| --- | --- | --- |
| 元信息 | v1.2、输入加研究包 | — |
| 第 1 章 | 新增「产品原则」六条 | 3.1 |
| 第 5.2 节 Skills | 升级为版本化 Skill 包模型 | 3.11 |
| 第 7 章 | 新增 7.9 副作用分级 / 7.10 持久工作流 / 7.11 Evidence 一等对象 / 7.12 模型路由与数据分类 / 7.13 技术选型注记 | 3.3–3.5、3.9、第 4 节 |
| 第 8 章 | M1 加失败聚类；M2 加存量 CI 报告接入；新增 Gate 制验收与北极星指标 | 3.2、第 2 节、3.14 |
| 第 9 章 | 新增 9.12 参数哈希审批 / 9.13 Prompt Injection / 9.14 幂等与补偿 | 3.7、3.8、3.6 |
| 第 11 章 | 引用加入研究包与本文档 | — |
| （v1.4 追记）第 4.0 节 | 执行架构扩展为「双执行模式 × 双执行环境」；引用型用例（Mock 型）承载企业 CI 接入；M0 执行环境注册中心采纳 Jenkins Job Contract | 第 2 节 |
