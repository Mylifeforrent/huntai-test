# 12 · HuntAI Test PRD——企业内部 AI 自动化测试平台（Stage 12 · 终版收口位）

> - **文档版本**：v1.5（2026-08-24，全链路一致性复核修复）
> - **流程定位**：开发流程图 Stage 12「生成 PRD 需求文档」槽位（与 Stage 8 后端架构设计并行）。**当前为中期版**——基于决策总纲与竞品拆解生成，尚未吸收 05 业务建模 / 06 核心交互链 / 07 产品原型的结论；按流程图应在 Stage 6、7 完成后重生成 **v2 终版**。FR 编号保持稳定以维持全链路溯源
> - **依据**：[README.md](../README.md)（决策总纲）、[market_research.md](../01_market_research/market_research.md)、三份竞品拆解（`competitors/`）、研发助手研究包（源仓库 opensource-product-analysis：references/enterprise_ai_dev_assistant_research_2026-07-28/）
> - **评审对象**：产品、设计、工程、数据、安全、法务（含合规）
> - **模板填空**：产品/功能 = HuntAI Test 平台（一期聚焦 AI 自动化测试）；用户问题/目标用户/业务目标/非目标/已有资料/约束 → 见第 1 章

---

## 0. 生成前一致性检查（按模板要求先行输出）

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| 用户故事 → 功能需求映射 | ✅ PASS（v1.5 补齐后） | 第 2.1 节映射表，每个 US 至少对应 1 个 FR，无孤儿。**双向核查（v1.5 新增）**：反向映射原有 5 个 FR 无 US 承接（FR-01/02/08/12/17——均为基座与治理类需求），已补 US-15–US-19；现 19 个 FR 全部有 US 落点，19 个 US 全部有 FR 落点 |
| 功能需求 → 验收标准 | ✅ PASS（v1.5 补齐后） | 第 2.2 节每个 FR 必含验收标准，**v1.5 补 FR-12 验收（原缺）** |
| AI 能力编号完整性 | ✅ PASS（v1.5 修正后） | 第 3.1 节 A1–A8 连续无断号（v1.5 修正：§7.4 原表述「A1–A7」漏 A8 Agent Mode；05 §5 v1.3 已补 A2 登记行消除原跳号） |
| 领域对象 ⊆ 05 建模层 | ✅ PASS（v1.5 新增核查） | 第 3 节「核心对象」摘要 v1.5 补齐 8 个对象（OrgQuota / QualityGatePolicy / GateEvaluation / CopilotSession / Connector / ApiToken / PerfBaseline），现与 [05-业务建模](../03_problem_modeling/problem_model.md) §1.1 的 23 对象清单对齐——本 PRD 为摘要，05 为唯一建模事实源 |
| 业务/用户目标 → 指标 | ✅ PASS | 第 1.4 / 5.3 节，每个目标配指标 + 目标值 + 时间范围 |
| 指标 → 基线 | ❌ **FAIL（3 项）** | ① 测试分析中位耗时基线无我方数据；② AI 生成采纳率基线无数据；③ 每成功工作流成本基线无数据。根因：我方现状未盘点（各竞品 `04-能力对比.md` 空白列同样未填）。处置：全部标 TBD，登记于第 8.1 节，由平台负责人 + QA 负责人在 M0 第 2 周前完成基线盘点后回填；本文所有目标值为**假设目标**（源自研究包建议），基线回填后须复核 |
| 风险 → 负责人 | ⚠️ PARTIAL | 第 8.3 节全部风险已配**角色级**负责人；具体人名 TBD（角色定义见 6.6 RACI），M0 启动会指派 |
| AI 能力 → 质量阈值 + fallback | ✅ PASS | 第 3.1 节每项能力六要素齐全 |
| 「智能/准确/实时」禁用 | ✅ PASS | 全文指标均为可测定义（如「实时」改写为「流式首 token P95 ≤ 3s」） |
| 引用文档版本对齐 | ✅ PASS | 引用 [README](../README.md)（决策总纲）、[03](../01_market_research/market_research.md) 借鉴文档、[05](../03_problem_modeling/problem_model.md) 业务建模、[06](../04_interaction_design/interaction_flows.md) 交互链（四链，口径对齐 05「25 页 / 23 对象」）。**各被引文档的最新版本以其文首版本头为唯一事实源，本文不随下游升版回头改此行**（本行写定于 v1.5，核查时点：README v1.5 / 03 v1.0 / 05 v1.3 / 06 v1.1）；各文档编号真实可达 |

**结论：存在 1 项 FAIL（指标基线）与 1 项 PARTIAL（风险人名），不假装通过；已全部转为带负责人和期限的 TBD 项，不阻塞评审，但阻塞 M1 放行。**

---

## 1. 摘要、问题、用户、目标和非目标

### 1.1 摘要

HuntAI Test 是企业内部自用（≤1000 用户、部门级多租户）的 AI 自动化测试平台：以接口 / Web / 性能三大自动化域为核心，用 AI 做用例生成、失败聚类与归因、自愈建议，用确定性工作流、副作用分级、审批与证据链约束一切有副作用的动作，并与既有 Jira / GitHub / Confluence / CI-CD / Release 系统打通形成端到端质量闭环。一期（M0–M3）聚焦 AI 自动化测试；Release 编排与全局 Copilot 为平台模块（M3 起），本 PRD 一并纳入但明确分期。

### 1.2 用户问题（问题与证据）

| # | 问题 | 证据 | 置信度 |
| --- | --- | --- | --- |
| P1 | 测试资产分散（Excel、代码仓、CI Job 各处），无统一用例库与执行入口 | 我方现状盘点 TBD；TestHub 拆解显示 Excel 导入为企业迁移刚需 | 中，待盘点验证 |
| P2 | 测试结果分析耗时：失败逐条人工归因，无法快速判断是否阻塞发布 | 研究包 PRD「15 分钟内判断是否阻塞发布」场景与 -50% 假设；Test Lead 用户故事 | 中，基线 TBD |
| P3 | 系统割裂：Jira（缺陷）/ GitHub（PR）/ CI（执行）/ Release（发布）之间靠人肉搬运，质量证据不可追溯 | 三份竞品拆解：三家对 CI/Jira/GitHub 集成为零或源码级断裂（`competitors/*/modules/`） | 高 |
| P4 | 对「AI 替我执行」缺乏信任：生成质量不可知、副作用不可控 | 三竞品 AI 效果均无量化数据（各家 `07-证据不足清单`）；FullScopeTest C1–C12 反面清单 | 高 |
| P5 | 存量 CI 测试资产（JUnit/Allure 报告）无法进入统一分析与发布证据 | 研究包模块 C 流程支持，竞品均未覆盖 | 高 |

### 1.3 目标用户（用户、场景、频率）

| 用户 | 场景 | 频率 |
| --- | --- | --- |
| 测试工程师（主用户，假设 200–400 人） | 维护用例、执行回归、查看归因、修复失败 | 每日 |
| Test Lead / QA 负责人 | run 级失败聚类审阅、门禁策略配置、发布就绪判断 | 每日 / 每次回归 |
| 开发工程师 | PR 上看门禁结论、接收 Jira 缺陷 | 每次 PR（高频） |
| 性能工程师 | 压测场景配置、执行、基线对比 | 每迭代 / 每月 |
| Release Manager | Release Task 创建、Readiness Gate 审阅（M3+） | 每次发布 |
| 全体研发 | Copilot 查询测试资产（M3+ 最小版） | 按需 |
| 平台管理员 / 安全 | 连接器、模型路由、预算、审批、审计（M0 起） | 每日 |

### 1.4 业务目标（≤3，均配指标/基线/目标值/时间范围）

| # | 目标 | 指标（可测定义） | 基线 | 目标值 | 时间范围 |
| --- | --- | --- | --- | --- | --- |
| BG-1 | 回归分析提效 | 「CI/执行完成 → 分诊报告被审阅通过」中位耗时 | **TBD**（M0 第 2 周盘点） | 较基线下降 ≥50% | M2 上线后 3 个月 |
| BG-2 | 质量门禁普及 | 核心项目 CI 中门禁结论写入 exit code 的流水线占比；关键字段首次接受率（生成内容未经修改被接受的比例） | 0%（新平台）；接受率基线 **TBD** | 核心项目 100% 覆盖；首次接受率 ≥80% | M2 结束时；接受率 M1 起 3 个月 |
| BG-3 | 可审计质量证据链 | 证据覆盖率（关键结论挂有效 evidence_ref 的比例）；外部系统误写次数（未经有效审批的外部写操作） | 0%（新平台） | 覆盖率 ≥95%；误写 = 0（硬性） | M2 起 3 个月；误写永久 |

### 1.5 非目标（明确不做什么）

1. 不替代 Jira / Confluence / GitHub / CI-CD / Release 系统——只做单向读取 + 审批后写入，不做双向全量同步；
2. 不自研压测引擎（包装 Locust/k6）、不做 APP 自动化、不做计费/白标/Workflow Builder/软件目录；
3. 不做无人审批的 AI 自动改写/自动应用（一切 L2+ 副作用必须 HITL）；
4. 不做对外 SaaS / 多租户计费；
5. 不复制 TestHub（GPL-3.0）任何源码——只借鉴机制；
6. 一期不做：视觉回归、语义去重、NL2Script、MCP 对外暴露（M4 评估）。

---

## 2. 用户故事、功能需求、验收标准和边界场景

### 2.1 用户故事 → 功能需求映射

| US | 故事（作为…我希望…以便…） | 映射 FR | 阶段 |
| --- | --- | --- | --- |
| US-01 | 测试工程师：导入 OpenAPI 后 AI 生成接口用例草稿，人工审阅后入库 | FR-05 | M1 |
| US-02 | 测试工程师：接口失败时得到带证据的归因与修复建议（不自动应用） | FR-06 | M1 |
| US-03 | Test Lead：一次执行后看到失败聚类 + 阻塞判断 + 历史对比，15 分钟内决策 | FR-07 | M1 |
| US-04 | 测试工程师：Web 用例执行自动留存截图/视频/Trace，可回放 | FR-09 | M2 |
| US-05 | 测试工程师：定位器失效时收到自愈建议，diff 预览确认后生效并可回滚 | FR-10 | M2 |
| US-06 | 开发：PR 上看到 Check Run 门禁结论，FAIL 时 CI 变红 | FR-13 | M2 |
| US-07 | Test Lead：失败用例一键创建 Jira 缺陷，附证据与复现步骤 | FR-14 | M2 |
| US-08 | 性能工程师：配置压测场景（白名单环境 + 审批 + 并发预算）并得到基线对比 | FR-11 | M3 |
| US-09 | Release Manager：基于 Jira 版本创建 Release Task，Readiness Gate 通过后经确认调用 Release 系统 | FR-15 | M3 |
| US-10 | 全员：Copilot 用自然语言查询测试资产（只读） | FR-16 | M3 |
| US-11 | 平台管理员：按部门设置 AI Token 预算并查看成本/质量看板 | FR-03 | M0 |
| US-12 | 平台管理员：在审批中心统一处理所有 HITL 请求（参数哈希绑定） | FR-04 | M0 |
| US-13 | 测试工程师：对难以脚本化的流程，用自然语言用例经 Skill+Agent 动态执行探索，成功轨迹一键固化为脚本入库 | FR-19 | M2/M4 |
| US-14 | 已有 Jenkins pipeline 的系统 Owner：在平台创建引用型用例绑定我的 Job，触发后平台采集日志/报告并进入统一分诊与门禁，零迁移获得平台能力 | FR-18 | M1/M2 |
| US-15 | 部门 Owner / 全体用户：用企业 SSO 账号登录，只能看到本部门与本项目的测试资产，越权访问一律不可达 | FR-01 | M0 |
| US-16 | 平台管理员 / 安全：任何 AI 调用都能在一处查到调用者、模型、prompt 版本、真实用量与成本，不存在绕过日志的调用路径 | FR-02 | M0 |
| US-17 | 测试工程师 / SRE：执行任务不会永久卡在运行中——重启、失联、超时都有确定的收敛状态，等待态可见且可人工取消 | FR-08 | M1 |
| US-18 | 性能工程师 / Test Lead：压测的 p95 与错误率与接口/Web 用同一套门禁阈值和结论对象，发布决策看到的是同一份质量口径 | FR-12 | M3 |
| US-19 | 安全工程师：每个有副作用的动作在执行前都经统一策略裁决（放行/拒绝/需审批/需重认证），未声明副作用等级的动作默认拒绝 | FR-17 | M0 |

### 2.2 功能需求与验收标准

**基座（M0）**

- **FR-01 多租户与身份**：组织（部门）→ 项目两级；SSO（OIDC）/LDAP 登录；角色 owner/admin/tester/viewer；租户隔离在 ORM/中间件强制。验收：双租户越权回归测试集 100% 阻断；无 SSO 账号无法登录。
- **FR-02 AI 调用日志与 Token 计量**：所有 AI 调用（无旁路）记录真实 usage、模型、prompt 版本、成本、延迟、数据分级；按部门归集。验收：代码审查确认无绕过 AIInvocationLog 的调用路径；看板可按部门出月账单。
- **FR-03 预算与看板**：部门级 Token 预算 + 超限熔断提示；成本/质量看板（采纳率、无据结论率、成功率）。验收：超预算后新 AI 调用被拒并通知 Owner。
- **FR-04 审批中心**：统一 HITL 队列；审批卡片九要素（动作/资源/diff/数据来源/模型与 Skill 版本/风险等级/成本估计/回滚能力/参数哈希）；参数哈希绑定。验收：审批后修改参数再执行 → 被拦截并要求重新审批（自动化测试覆盖）。
- **FR-17 副作用分级与 Policy Gate**：所有工具/动作声明 L0–L4；Gate 输出 ALLOW/DENY/REQUIRE_APPROVAL/REQUIRE_REAUTH。REQUIRE_REAUTH 触发条件（v1.4）：L3+ 动作且操作者会话超过再认证窗口（默认值由 08 后端架构配置项定义），或目标资源声明需强认证。验收：策略表驱动的单元测试全覆盖；默认拒绝未声明动作。

**接口自动化（M1）**

- **FR-05 用例生成（两步式）**：OpenAPI/Postman 导入 → 生成默认不落库 → 审阅 → 保存并打 `ai-generated` 标签；采纳率/修改幅度埋点。验收：不存在 save=true 直写路径（接口审查）；生成失败有显式告警（禁止静默返回空）。
- **FR-06 失败归因建议**：输入执行日志+响应 → 输出失败原因分类（A2 category 枚举 **7 值**：env_down / auth_expired / locator_stale / assertion_real_bug / flaky / data_issue / unknown，unknown 兜底——v1.4 与 §3.2 schema 对齐，旧表述「8 类」作废）+ confidence + fixes 建议；confidence ≥0.7 才显示「可应用」，应用必须走 FR-04 审批 + 快照 + 回滚端点。验收：快照失败则中止（fail-close）；有回滚 API 且自动化测试覆盖。
- **FR-07 run 级失败聚类报告**：归一化结果 → 聚类 + 阻塞判断 + 历史对比；显示证据链接、置信度、无法判断项、用户修改历史。验收：确定性解析准确率 ≥98%（对标注集）；无据结论率 <2%。
- **FR-08 执行引擎**：真队列（Temporal POC 或 Celery+状态机保底）+ 重试/熔断/fail-fast + 心跳 + 僵尸回收；六类断言；双层变量 `{{env}}`/`${func}`。验收：变量解析失败必报错；进程重启后无「永久 running」任务（混沌测试）。

**Web 自动化（M2）+ 跨域能力（FR-18 自 M1 起 / FR-19 自 M2 起）**

> 分组口径（v1.5 澄清）：FR-18（执行环境与引用型用例）与 FR-19（双执行模式）**不属于 Web 域**，而是跨三域的执行架构能力，因分期主体落在 M1 末–M2 而列于本组——FR-18 v1 在 **M1** 交付（Jenkins 触发 + JUnit 采集），M2 完善多格式适配器；FR-19 在 **M2** 试点、**M4** 完整（对齐 §6.5 阶段计划与 README 第 8 章，避免读者误认为二者均始于 M2）。

- **FR-09 Playwright 执行器**：容器化、独立于 API 进程；证据三件套（截图/视频/Trace）自动上传对象存储。验收：任一失败步骤 100% 有 Trace 可回放。
- **FR-10 定位器自愈建议**：主备定位器 + 健康度；失效时 AI 给修复建议（仅建议），落地走 diff→审批→快照→回滚。验收：自动改写路径不存在；回滚后用例可执行。
- **FR-13 GitHub Check Run 门禁**：PR/push 触发（changed_files 正确传递；仓库/分支 ↔ 测试计划触发绑定在「集成」页配置，05 §4.2 v1.2）→ 执行 → Check Run 三段式回写；门禁结论写入 CI exit code。**豁免（v1.4 定义）**：owner / Test Lead 发起，走 FR-04 审批（action_ref=gate_waiver，sideEffectLevel=L3，05 §2.3 冻结表），豁免记录（豁免人 / 理由 / 时效）入「门禁评估历史-豁免记录」并写 AuditEvent。**数据落点（v1.5 补）**：阈值与模式配置 = QualityGatePolicy，单次评估结论与逐阈值明细 = GateEvaluation（不可变，含策略快照，豁免以 waiver_approval_id 关联），二者见 05 §1.1 #22/#23 与 §2.5。验收：门禁 FAIL 时 CI 变红（E2E 测试）；Check Run 同步失败有重试与告警；未经审批的豁免不生效（自动化测试覆盖）。
- **FR-14 Jira 缺陷创建**：单向创建 + 链接回写；用例关联 story。验收：未经审批不得写入（渗透测试）；缺陷含证据附件。
- **FR-18 执行环境与引用型用例（企业 CI 接入，v1.2 扩展）**：执行环境为一等注册对象（Jenkins 等实例注册 + 凭证引用 + 健康检查 + Job 发现 + 参数 Schema）；**引用型用例（Mock 型）**不托管脚本，仅声明目标 Job / 触发参数 / 采集配置（报告路径与格式）/ 门禁阈值映射；执行链路 = 幂等触发 → 持久轮询 + webhook 双通道 → 日志分片拉取 → 报告适配器（JUnit/Allure/Playwright/Pytest）解析 → 归一化统一 TestRun（`execution_source=external_ci`）→ 与 FR-07 同一分诊、同权进门禁。验收：标注集解析准确率 ≥98%；触发带幂等键（重放不重复执行 Job）；参数不过 Job Schema 校验即拒绝（校验在 TestRun VALIDATING 态执行、落 `VALIDATING → FAILED`，05 §2.2 v1.2 口径）；外部 Job 排队超时状态可见且可幂等取消（超时仅告警，不自动取消外部 Job）。
- **FR-19 双执行模式（v1.1 新增，跨三域）**：Script Mode = 确定性脚本执行（进门禁 / 发布证据）；Agent Mode = 用例意图 → Skill → Agent → Tool/浏览器动态执行，manifest 约束（allowedTools 白名单 / max_steps / 超时 / sideEffectLevel ≤L1，L2+ 单独审批），每个动作过 Tool Router + Policy Gate，结果标记 `execution_source=agent` 不进门禁，执行轨迹（步骤 / 动作 / 截图 / 工具调用）全量留存并支持**一键转脚本草稿**（人工确认后入库，回到 Script Mode）。验收：越权工具调用 100% 阻断（注入测试集）；超步 / 超时强制终止且轨迹保存为 incomplete、Agent 任务无自动重试（系统主动终止走 `STOPPING → CANCELLED`，进程失联由心跳超时兜底转 TIMEOUT，05 §2.2 v1.2 口径）；终止信号服务端持久化（多 worker 下可停）；轨迹转脚本产物过 schema 校验。

**性能自动化（M3）**

- **FR-11 压测编排**：包装 Locust/k6；执行生命周期走**统一 TestRun 10 态状态机**（05 §2.2 为唯一事实源；v1.5 对齐，旧表述「8 态状态机」作废——TestHub 性能 8 态已合并入统一模型，见 README 7.10）+ 场景互斥 + 心跳 + 快照冻结 + 压力机自监控 + SLA 熔断；**目标环境白名单 + 高危审批 + 全局并发预算 + kill switch**。验收：白名单外目标 100% 被拒；kill switch 60s 内停止全部施压进程（演练）；压测任务无自动重试。
- **FR-12 性能门禁接入**：max_p95_ms / max_error_rate 作为门禁阈值，与 FR-13 **同一 QualityGatePolicy 模型、同一 GateEvaluation 结果对象**（05 §1.1 #22/#23，v1.5 补落点）；性能劣化判定以 PerfBaseline 对比 + 容忍度为输入。**验收（v1.5 补齐，原缺）**：性能阈值与接口/Web 阈值走同一策略表与同一评估管线（代码审查确认无独立门禁分支）；压测 run 的门禁结论可在「门禁评估历史」页与 Release 证据汇聚面板中检索到；阈值缺配时判定为「未评估」而非默认通过（禁止静默放行）。

**Release 与 Copilot（M3+，摘要级，详见 README 5.1/5.2）**

- **FR-15 Release 模块**：Jira 版本圈定 → 范围快照 → 质量证据汇聚 → Readiness Gate → AI 草稿（notes/检查单）→ 审批后调用 Release 系统准备 item。验收：全链路审计可查；AI 草稿禁止自动推送。
- **FR-16 Copilot 最小版**：只读技能 + 全量日志 + 权限感知 + 服务端会话。验收：越权测试集 100% 阻断；`AI_ASSISTANT_ENABLED` 类开关真实生效。

### 2.3 边界场景（必须设计的行为）

| 场景 | 期望行为 |
| --- | --- |
| 超大测试报告（>10 万用例结果） | 分片流式解析，进度可见；解析超时 → 已完成部分入库 + 显式失败标记，不静默截断 |
| 生成批次中单条 schema 校验失败 | 整批标记 partial，失败条目进入「生成失败」列表可见，不允许静默丢弃 |
| 模型网关整体不可用 | 平台功能（执行/报告/门禁）不受影响，仅 AI 增强降级（见第 7 章）；页面显式提示 AI 降级中 |
| 审批人休假 / 审批超时 | 超时策略：升级通知备审批人 → 仍未处理自动过期，任务停在 WAITING_APPROVAL，不自动放行 |
| 同一压测场景并发触发 | 场景级互斥：第二次请求进入排队并提示，不并行施压 |
| CI 触发后平台重启 | 幂等键保证不重复触发外部 Job；轮询从中断处恢复 |
| 跨租户引用（用例/报告/evidence_id） | 工具层强制租户校验，返回 404 而非 403（不泄露存在性） |
| 敏感数据（密钥/PII）出现在日志/报告 | 落库前脱敏管道（正则+字典）；AI 调用 prompt 不含 Restricted 级内容（路由层保证） |
| 用户在 Copilot 中诱导越权/注入 | Policy Gate 拦截 + 记录安全事件 + 注入测试集覆盖该模式 |
| Agent Mode 循环 / 超步数 | 达到 max_steps 或总超时即强制终止，轨迹保存为 incomplete；Agent 任务不自动重试 |
| Agent 请求白名单外工具 / 越权资源 | Policy Gate 拒绝并记录安全事件；连续 3 次拒绝自动终止任务 |
| 外部 Job 排队拥堵 / 长时间无响应 | WAITING_EXTERNAL 状态可见；超时阈值告警；可幂等取消（cancel 后已产生的构建记录照常采集入库） |
| 引用型用例绑定的 Job 被外部删除/改名 | 执行前 Job 存在性校验失败 → 用例标记失效（05 §2.1 v1.2：validity=invalid，系统标记、可逆，区别于人工 DEPRECATED）并通知 Owner，不进入执行队列 |
| 等待态长时间滞留（v1.5 补充，← 05 v1.3 裁定）| WAITING_APPROVAL / WAITING_EXTERNAL **不受心跳僵尸回收**（属等待态非活跃态），可长期滞留且不自动迁移（审批过期不放行、外部排队超时仅告警）。因此硬要求：①「进行中 TestRun」列表必须持续可见并显示滞留时长（Web 端与工作台均含）；②超阈值发系统告警（阈值归 08 配置项）；③人工可随时取消（WAITING_APPROVAL→CANCELLED / WAITING_EXTERNAL→CANCELLED 边，05 §2.2 已定义）。**STOPPING 态**（活跃态，受心跳治理）卡死时走 STOPPING→TIMEOUT 兜底边，不得永久停留 |

---

## 3. AI 能力规格与 Prompt Contract

### 3.1 AI 能力清单（输入/输出/质量阈值/模型策略/检索与工具调用/fallback）

| # | 能力 | 输入 | 输出（结构化） | 质量阈值 | 模型策略 | 检索/工具调用 | Fallback |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A1 | Swagger→用例生成（M1） | OpenAPI 规范片段 + 用例类型策略 | `GeneratedCase[]`（名称/步骤/断言/变量提取/前后置/标签），断言 ≥2 类 | 首次接受率 ≥80%（字段级）；schema 合法率 100% | 私有网关高精度路由；temperature 0.2；分批 ≤10 接口/次；数据分级 ≤ Confidential | 无工具调用（纯生成） | 解析失败重试 1 次 → 显式失败列表；网关不可用 → 功能置灰，导入本身不受影响 |
| A2 | 失败聚类与归因（M1，核心） | 归一化失败集 + 证据池（日志/响应/Trace 元数据）+ 历史相似失败 | `FailureCluster[]`（见 3.2 schema） | 离线：cluster 语义一致性（人工双人标注 Krippendorff α ≥0.6，阈值假设待校准）；top-1 归因命中 ≥75%；无据结论率 <2% | temperature 0；严格 JSON；CoT 先理由后结论 | 检索：历史失败向量库（pgvector）；无写工具 | JSON 失败重试 1 次 → 规则聚类（错误码/接口路径分组）+ confidence 0.3 |
| A3 | UI 定位器自愈建议（M2） | 失效定位器 + DOM 快照 + 失败截图（多模态可选） | `LocatorHealSuggestion`（候选定位器 + 理由 + confidence + diff） | 建议采纳率 ≥60%（假设，M2 校准）；候选不改变语义（人工抽检） | 视觉模型路由（Confidential 及以下）；temperature 0 | 无 | 生成失败 → 仅提示人工修复，附 DOM diff |
| A4 | 归因修复建议（M1，并入 A2） | A2 的 cluster + 用例定义 | `FixSuggestion`（field/current/suggested/reason/confidence） | 同 A2；confidence ≥0.7 才展示「可应用」 | 同 A2 | 读用例版本（只读工具） | 低置信 → 仅展示诊断，不出建议 |
| A5 | Release notes 草稿（M3+） | Jira 范围快照 + 质量证据 | `ReleaseNotesDraft`（分类变更摘要 + checklist + 缺失项） | 字段填充率 ≥90%；**缺失项召回率优先于文采**（漏 blocker = 关键缺陷） | 结构化生成路由；成本上限按 skill 声明 | Jira 只读工具 | 拉取失败 → 明确标注数据缺口，禁止编造 |
| A6 | Copilot 问答（M3+ 最小版只读） | 用户问题 + 权限上下文 + 会话历史 | 答案 + 引用 + 工具调用记录 | 引用precision ≥90%（抽检）；越权拦截 100% | 多轮对话路由；会话服务端持久化 | 只读技能白名单（Jira/GitHub/平台查询） | 工具失败 → 声明无法获取，不猜测 |
| A7 | LLM Judge 生成质量评估（M4） | 用例 + 评分 rubric | `JudgeResult`（分项分 + 理由） | 与人工评定一致性 ≥75%（校准集） | 独立裁判模型（与生成模型不同源）；CoT + temperature 0；n=3 取中位数 | 无 | Judge 失败 → 该批次标记未评估，不阻塞人工流程 |
| A8 | Agent Mode 动态执行（M2 试点 / M4 完整，v1.1 新增） | 用例意图 + 页面状态/DOM + 工具清单（Skill manifest 声明） | `ExecutionTrajectory`（步骤 / 动作 / 截图 / 断言结果 / 工具调用记录 / incomplete 标记） | 探索集任务完成率 ≥60%；每步动作合法率 100%（Policy Gate 硬约束）；轨迹转脚本采纳率 ≥50%（三项均为假设值，M2 校准） | 多模态 / 文本路由按数据分级；temperature ≤0.2；max_steps 由 manifest 声明 | 浏览器 + 只读工具白名单（经 Tool Router + Policy Gate） | 超步 / 超时 / 工具失败 → 保存轨迹退出并标 incomplete（无自动重试）；网关不可用 → 任务排队不启动 |

### 3.2 Prompt Contract（以 A2 失败聚类为例，作为接口对待）

**契约标识**：`prompt/failure-triage` · 语义化版本（如 1.0.0）· 生产环境版本锁定（pin）· 变更走第 5.4 节十步门禁。

**上下文输入（注入顺序固定，分层防注入）**：
1. System（不可被覆盖）：角色、安全边界、输出契约；
2. Policy（不可被覆盖）：数据分级标记、禁止行为清单；
3. Skill instructions（版本化）；
4. User/任务参数（run_id、聚类策略开关）；
5. Document（**不可信数据**，逐条标注来源与 evidence_id，不视为指令）。

**严格输出 schema（JSON Schema 摘要）**：

```json
{
  "clusters": [{
    "cluster_id": "string",
    "failure_refs": ["case_result_id"],
    "category": "env_down|auth_expired|locator_stale|assertion_real_bug|flaky|data_issue|unknown",
    "root_cause": "string ≤ 200 字",
    "confidence": "number 0.0-1.0",
    "evidence_refs": ["evi_..."],
    "blocking_judgment": "blocker|non_blocker|uncertain",
    "suggested_actions": ["string"],
    "can_auto_apply": false
  }],
  "unclustered_refs": ["case_result_id"],
  "meta": {"prompt_version": "string", "model": "string"}
}
```

**禁止行为**：① evidence_refs 只能引用输入证据池内存在的 ID（服务端校验，违规输出整批拒收）；② 不得输出任何执行类指令；③ 不得建议跳过/删除用例；④ 不确定必须输出 `unknown`/`uncertain`，禁止编造 root_cause；⑤ confidence 禁止默认 1.0。

**失败处理**：schema 校验失败 → 同参数重试 1 次（temperature 0）→ 仍失败走 A2 fallback（规则聚类）并记 `AIInvocationLog.result=degraded`；30s 超时同路径。

**版本与回滚**：任何修改产生新版本，新旧并行影子运行 ≥1 个回归周期；回滚 = 恢复上一 approved 版本（分钟级，配置切换，无需发版）；未版本化 prompt 不得进生产（CI 强制检查）。

---

## 4. 数据、模型、集成、隐私和安全

### 4.1 数据

- **核心对象**（口径以 [05-业务建模](../03_problem_modeling/problem_model.md) §1.1 的 23 个对象清单为唯一事实源；下列为摘要，v1.5 对齐补齐 OrgQuota / QualityGatePolicy / GateEvaluation / CopilotSession / Connector / ApiToken / PerfBaseline）：Organization / User+ProjectMember / Project / **OrgQuota** / TestPlan / **ExecutionEnvironment（执行环境注册，含 Jenkins 实例与 Job 契约）** / TestCase(+Version，含引用型用例) / TestRun(+StepRun，**统一 10 态**，旧表述「8 态」作废) / CaseResult / Artifact / FailureCluster / EvidenceObject / ApprovalRequest / **QualityGatePolicy** / **GateEvaluation** / AIInvocationLog / AuditEvent / Skill(+Version) / ModelRoute / **PerfBaseline** / ReleaseTask / **Connector** / **ApiToken** / **CopilotSession**。
- **存储**：PostgreSQL（事务 + pgvector 向量）+ Redis（缓存/限流/短锁，不作工作流唯一状态）+ MinIO/S3（报告、截图、视频、Trace、证据包）。
- **治理**：所有核心表第一天带 `tenant_id`（ORM 强制过滤）；执行/发布范围**快照冻结**；制品生命周期规则（默认 Trace/视频保留 90 天，TBD 法务确认）；append-only 审计（关键字段：actor_user / delegated_agent / request_hash / approval.bound_hash / data_classification / evidence_refs / cost / latency）。

### 4.2 模型

- Model Adapter 统一接口（chat/structured/embed），业务代码禁直连厂商 SDK；按「任务类型 × 数据分级 × 成本上限」路由；模型与供应商 **TBD**（M0 拍板，候选经企业私有网关）；密钥服务端 Vault 管理，明文只显示一次；**禁止 BYOK 前端明文**；`logPromptBody:false` 默认，落库走脱敏管道。

### 4.3 集成（连接器契约）

- Jira / GitHub / CI / Release 系统四连接器统一实现：Auth（OAuth/App Token，凭证只存引用）/ Reader / Action（声明 sideEffectLevel + supportsPreview/Idempotency/Compensation）/ Webhook（HMAC 强制验签无例外分支）/ Health / RateLimit-Retry / DataMapper / PermissionMapper；统一返回 `{status, resource_refs, evidence, external_request_id, warnings}`；写前 ETag/版本防并发覆盖。Jenkins 连接器按研究包 Job Contract 实现：Job Registry / 参数 Schema / Trigger / 队列与构建状态 / Artifact manifest / 报告适配器 / 日志分片 / Cancel / webhook 回调 + 轮询兜底。
- **Release 系统 API 能力 TBD**（M0 前完成 readiness 调研：是否支持幂等创建、状态回传 webhook）。

### 4.4 隐私与安全

- 数据四分级 Public/Internal/Confidential/Restricted；Confidential 禁缓存、Restricted 仅本地模型或禁止处理；AI 日志含脱敏选项。
- 副作用 L0–L4 分级裁决（7.9 / FR-17）；审批参数哈希绑定 + 执行前重校验（anti-TOCTOU）；Prompt Injection 分层防护（外部内容标记不可信、工具参数结构化构造、恶意注入测试集）；脚本沙箱 = rootless Docker 临时容器、只读镜像、默认无网、资源配额、镜像白名单、输出扫描；压测目标环境白名单 + kill switch；全部「竞品踩坑安全清单」（README 第 9 章 14 条）作为安全验收 negative checklist。

---

## 5. 离线评测、人工评测、线上指标和发布门槛

### 5.1 离线评测（M0 建集，持续维护）

- **Golden dataset**：30–50 个历史测试运行样本（含失败样本）+ 人工标注（双人标注 + 仲裁）——研究包 Discovery 建议直接采纳；
- 确定性解析器：字段级解析准确率 ≥98%；
- A2 聚类：语义一致性 α ≥0.6（假设阈值）；A7 Judge：与人工一致性 ≥75%；
- Prompt Injection 套件：恶意 Jira 描述/日志/评论样本，拦截率 100%；
- Schema validity 100%；越权测试集（双租户）100% 阻断。

### 5.2 人工评测

- 每迭代抽检：A1 生成用例可执行率（语法可跑 + 语义合理，抽检 50 条）；A3 建议「语义不变」抽检；标注一致性行动：α <0.6 时修订 rubric 而非放水。

### 5.3 线上指标（看板 + 告警）

| 指标 | 定义 | 目标 | 告警阈值 |
| --- | --- | --- | --- |
| 北极星 | 每周「成功完成 + 被接受 + 产生可验证结果」的受控工作流数。**计数口径（v1.5 补齐，原缺可测定义）**：一次计数 = 同时满足①工作流实例达终态 SUCCEEDED；②存在人工接受动作（用例采纳 / 分诊报告审阅通过 / 审批批准 / Release 确认之一）；③产出至少一个可验证外部结果或质量结论（Jira issue / Check Run 结论 / GateEvaluation / ReleaseTask item / 入库用例版本）。**去重规则**：同一 TestRun 的重跑、同一审批的重新提交只计 1 次；`execution_source=agent` 的 run 仅在其轨迹被固化为脚本并入库后计数（避免探索性执行虚增） | 试点 3 个月 ≥30/周（假设） | 连续 2 周环比 -20% |
| 首次接受率 | 生成字段未经修改被接受比例 | ≥80% | <60% 触发评审（研究包 kill 线） |
| 证据覆盖率 | 关键结论挂有效 evidence_ref 比例 | ≥95% | <90% |
| 无据结论率 | 关键结论无证据支撑比例 | <2% | ≥5% |
| 外部误写 | 无有效审批的外部写操作 | 0（硬性） | =1 即事故（P1） |
| 审批反悔率 | 已批准动作事后因错误回滚比例 | <1% | ≥3% |
| AI 降级率 | 走 fallback 的 AI 调用占比 | <5% | ≥15% |
| 每成功工作流成本 | （模型+执行可变成本）/成功工作流 | 计量并设预算（基线 TBD） | 超部门预算 |

### 5.4 发布门槛

- **阶段 Gate**：技术闭环 Gate（重启不重复副作用 / AI 结论全量挂证据 / 越权全阻断）+ 业务价值 Gate（BG-1/2/3）；
- **AI 资产十步门禁**（Prompt/Skill/ModelRoute 任何升级）：schema test → unit/contract → golden dataset → 注入套件 → 权限测试 → 成本/延迟回归 → shadow/canary → Owner+安全审批 → 版本锁定 → 回滚计划。

---

## 6. 成本、延迟、容量、依赖、阶段计划和 RACI

### 6.1 成本

- 全量 Token 计量（FR-02）；部门预算熔断；单价表随模型路由配置维护（单价 **TBD**，随 4.2 模型拍板）；目标：每成功工作流成本可度量且有预算上限（基线 **TBD**，M1 末回填）。

### 6.2 延迟（SLO，均为可测定义）

- 平台只读 API：P95 < 1s（不含模型任务）；
- AI 流式生成：首 token P95 ≤ 3s（交互场景）；A2 分诊：run 完成后 ≤5 分钟出报告（10k 用例级）；
- 执行类（UI 套件/压测）异步无用户等待 SLO，提供进度流（SSE）；
- Check Run 回写：CI 结束后 ≤2 分钟。

### 6.3 容量（假设值，M0 校准）

- 1000 注册 / 假设 200 DAU；并发执行：接口 50 run、UI 8 slot（TBD）、压测全局并发预算 TBD（压测引擎侧另计）；报告解析吞吐 ≥1000 用例结果/分钟；对象存储按 90 天保留估算（TBD 法务确认后精算）。

### 6.4 外部依赖

企业 SSO(IdP)、Jira REST/Webhook（版本 TBD）、GitHub App 权限、CI API（触发/产物读取）、Release 系统 API（**readiness TBD**）、企业模型网关、Vault、Temporal（POC 结论 TBD：自托管 vs 保底 Celery）。

### 6.5 阶段计划（对齐 README 第 8 章）

| 阶段 | 里程碑 | 放行条件 |
| --- | --- | --- |
| M0（1–2 月） | 基座：租户/SSO/AI 日志/审批中心/集成骨架/队列化 TestRun/执行环境注册中心（Jenkins 注册 + 健康检查 + Job 发现）+ **基线盘点与评测集建设** | 第 0 章 FAIL 项闭环；越权测试通过；注册 CI 实例健康检查与 Job 发现可用 |
| M1 | 接口自动化 + A1/A2/A4 + 执行环境抽象与引用型用例 v1（Jenkins 触发 + JUnit 采集） | Gate：解析 ≥98%；首次接受率开始计量；引用用例重放不重复触发外部 Job |
| M2 | Web 自动化 + 门禁 + Jira + CI 接入完善（多格式适配器 + 日志分片 + webhook 回调） | Gate：BG-2 覆盖 100% 核心项目 |
| M3 | 性能 + Release v1 + Copilot 最小版 | Gate：压测 kill switch 演练通过 |
| M4 | Prompt A/B + Judge + RAG + NL2Script + MCP | Gate：A7 一致性 ≥75% |

### 6.6 RACI（角色级，人名 M0 指派）

| 事项 | R | A | C | I |
| --- | --- | --- | --- | --- |
| 产品决策/优先级 | 平台产品负责人 | 平台负责人 | QA 负责人、各部门 Owner | 全员 |
| 架构与技术选型 | 平台架构师 | 平台负责人 | 安全、SRE | 工程 |
| 三域执行器/连接器 | 后端/工作流团队 | 平台架构师 | 连接器对应系统 Owner | 产品 |
| AI 能力与 Prompt | AI 工程师 | 平台产品负责人 | QA/评测 | 安全 |
| 评测集与标注 | QA/评测工程师 | QA 负责人 | AI 工程师 | 产品 |
| 安全/合规/隐私 | 安全工程师 | 安全负责人 | 法务（数据保留、外部系统写入条款） | 全员 |
| 成本与预算 | 平台管理员 | 平台负责人 | 财务（如涉） | 部门 Owner |
| 事故响应 | SRE 值班 | 平台负责人 | 安全、产品 | 全员 |

---

## 7. 失败模式、人工接管、降级、kill switch 和回滚

### 7.1 失败模式与处置矩阵

| 失败模式 | 检测 | 自动处置 | 人工接管点 |
| --- | --- | --- | --- |
| 模型超时/不可用 | 超时 30s、网关 5xx | AI 功能降级（fallback 见 3.1）；平台核心功能不受影响 | 无需（SRE 告警响应网关） |
| 低置信度输出 | confidence <0.7 | 不展示「可应用」；标注 uncertain | Test Lead 审阅报告 |
| 敏感输入进入 AI 请求 | 路由层分级校验 | 拦截 + 记录 + 提示改用本地路由 | 管理员审查分级规则 |
| 越权尝试（Copilot/工具） | Policy Gate + 越权测试集 | DENY + 安全事件记录 | 安全工程师周审 |
| Prompt Injection | 分层校验 + 注入模式检测 | 拒绝执行工具调用 | 安全工程师分析样本 |
| 解析失败/幻觉 | schema 校验、evidence_refs 校验 | 整批拒收 → fallback；无据结论计入指标 | 评测责任人修订 prompt |
| 执行器僵尸任务 | 心跳超时 | 自动转 TIMEOUT 并回收（← 05 §2.2 状态机口径，v1.4 对齐，旧表述「标记 FAILED」作废） | Test Lead 决定重跑 |
| 审批超时/过期 | TTL 计时 | 升级通知 → 过期不自动放行 | 备审批人 |
| 压测失控 | SLA 熔断 + 自监控 | abort_on_breach 自动停 + kill switch | 性能工程师确认 |
| 外部误写 | 审计对账 | — | **P1 事故流程**（7.3） |

### 7.2 降级顺序（总原则：先保平台、再保证据、最后保 AI 增强）

AI 增强（生成/归因/建议）→ 只读查询 → 平台执行/报告/门禁。任一层降级在 UI 显式横幅提示，不静默。

### 7.3 事故响应

分级：外部误写/数据泄露 = P1（立即 kill 相关连接器写入 + 通报 + 取证审计链）；AI 质量劣化（无据结论率 ≥5%）= P2（回滚 prompt 版本 + 灰度收量）；其他 P3。响应 SLO：P1 15 分钟启动、1 小时止血决策；事后 blameless 复盘进风险登记。

### 7.4 Kill Switch 与回滚

- **开关层级**（全部真实生效并有自动化测试验证，反面教材 FullScopeTest `AI_ASSISTANT_ENABLED` 采集不检查）：单能力（**A1–A8**，v1.5 修正——原表述 A1–A7 漏 A8 Agent Mode，而 Agent 动态执行恰是最需要单独 kill switch 的能力）→ 模块（Copilot/Release/压测）→ 连接器（Jira/GitHub/CI/Release 写入）→ 全局 AI。压测 kill switch：60s 内终止全部施压进程。开关操作入口 = 「AI 能力开关与降级」页（05 §4.2 v1.3）；**关停即时生效不走审批（L1），恢复走审批（L3，action_ref=kill_switch_restore）**（05 §2.3 v1.3 裁定）。
- **回滚**：Prompt/Skill = 版本切换分钟级；用例/定位器修改 = 快照恢复；外部写入 = compensation（如 CI Job cancel）+ Jira 缺陷关闭草稿（不自动删外部对象，人工确认）；平台发版 = 蓝绿 + 数据库迁移向前兼容。

---

## 8. 开放问题、假设、风险登记和变更日志

### 8.1 开放问题（TBD 登记，含负责人与期限）

| # | 问题 | 负责人（角色） | 期限 |
| --- | --- | --- | --- |
| Q1 | 测试分析耗时/采纳率/成本三项基线盘点（第 0 章 FAIL 项） | 平台负责人 + QA 负责人 | M0 第 2 周 |
| Q2 | 模型与供应商选型（含单价表、数据分级路由） | AI 工程师 + 安全 | M0 结束 |
| Q3 | Temporal POC 结论（vs Celery 保底） | 平台架构师 | M0 第 4 周 |
| Q4 | Release 系统 API readiness（幂等/webhook/权限） | 后端/集成 Owner | M2 中期（M3 前） |
| Q5 | Jira/GitHub/CI 的版本与权限边界确认 | 集成 Owner + 各系统 Owner | M0 结束 |
| Q6 | 制品保留期与审计留存期的法务确认 | 法务 + 安全 | M1 前 |
| Q7 | 压测环境白名单与全局并发预算数值 | 性能工程师 + SRE | M3 前 |
| Q8 | RACI 人名指派 | 平台负责人 | M0 启动会 |
| Q9 | 试点部门选择与北极星基线口径 | 平台负责人 + QA 负责人 | M0 第 2 周 |
| Q10 | A2/A3/A7 质量阈值假设值校准（评测集建成后） | QA/评测工程师 | M1/M2 末 |

### 8.2 假设

1. 研究包的目标值（-50%/≥80%/≥95%）可作为假设目标——**待基线校准**；
2. 企业模型网关可用且支持结构化输出与多模型；CI 系统提供触发与产物读取 API；
3. 试点部门愿意提供 30–50 个历史样本（否则评测集建设延期，M1 放行条件不成立）；
4. ≤1000 用户内部规模下 pgvector 满足检索需求（超载再演进 Qdrant）。

### 8.3 风险登记（概率/影响/负责人/缓解）

| # | 风险 | 概率 | 影响 | 负责人 | 缓解 |
| --- | --- | --- | --- | --- | --- |
| R1 | 连接器工作量失控（集成 > 三域执行器） | 高 | 高 | 后端/集成 Owner | 标准 Action Contract + contract test + 逐系统 readiness Gate |
| R2 | AI 输出正确但业务不采用 | 中 | 高 | 平台产品负责人 | 固定页面嵌入流程 + 首次接受率监控 + <60% 触发重定位评审 |
| R3 | 越权/误写事故 | 中 | 严重 | 安全工程师 | ORM 强制隔离 + 参数哈希审批 + 越权回归集 + negative checklist |
| R4 | GPL 污染（误抄 TestHub 代码） | 低 | 严重 | 平台架构师 | 机制借鉴纪律写入工程规范 + 代码评审检查项 |
| R5 | AI 成本失控 | 中 | 中 | 平台管理员 | 部门预算熔断 + 路由成本上限 + 每工作流成本看板 |
| R6 | Prompt/模型升级行为漂移 | 中 | 高 | AI 工程师 | 十步发布门禁 + shadow 运行 + 版本锁定回滚 |
| R7 | 基线缺失导致目标无法验收 | 高 | 中 | 平台负责人 | Q1 强制 M0 闭环，阻塞 M1 放行 |
| R8 | Release 系统 API 能力不足 | 中 | 中 | 集成 Owner | Q4 提前调研；不足则降级为「证据导出 + 人工创建」 |

### 8.4 变更日志

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1.0 | 2026-08-23 | 基于 README v1.2 与 03 借鉴文档（原编号 02），按 AI PRD 模板首版生成；含一致性检查（1 FAIL / 1 PARTIAL）与 10 项 TBD 登记 |
| v1.1 | 2026-08-23 | 新增双执行模式（Script Mode / Agent Mode）：US-13、FR-19、A8 能力规格、2 条边界场景；对齐 README v1.3 之 4.0 节 |
| v1.2 | 2026-08-23 | 执行架构增加执行环境维度（平台执行器 / 企业 CI）：US-14、FR-18 扩展为执行环境与引用型用例（Mock 型）、新增 ExecutionEnvironment 数据对象与 Jenkins Job Contract 集成契约、2 条边界场景、M0–M2 阶段计划调整；对齐 README v1.4 |
| v1.3 | 2026-08-23 | 文档编号对齐开发流程图（移至 Stage 12 槽位）；定位更新为终版 PRD 位——待 06 交互链与 07 原型完成后重生成 v2 终版 |
| v1.4 | 2026-08-24 | Stage 6.5 缺口回写（依据四条交互链「缺口上报」26 项裁定）：FR-06 归因分类对齐 §3.2 枚举 7 值；FR-13 补门禁豁免流程（gate_waiver，L3，走 FR-04 审批）与触发绑定页面指引；FR-17 补 REQUIRE_REAUTH 触发条件；FR-18 验收补校验落点（VALIDATING→FAILED）与排队超时行为；FR-19 验收补 Agent 终态归属；§2.3「Job 被删」补 validity 标记落点；§7.1 僵尸任务对齐 05 §2.2（TIMEOUT） |
| v1.5 | 2026-08-24 | 全链路一致性复核修复（Stage 3→6 反向核查，含 03/04/05/06/12 交叉验证）：① US-FR 映射补 5 个基座类 FR 无 US 承接（US-15~19：FR-01/02/08/12/17），现双向无孤儿；② 状态数口径统一（10 态，作废「8 态」旧表述）；③ 归因 category 枚举 7 值（作废「8 类」）；④ AI 能力编号 A1–A8（作废「A1–A7」漏 A8）；⑤ FR-12 补验收标准（原缺）与新门禁对象落点（QualityGatePolicy / GateEvaluation，对齐 05 v1.3）；⑥ FR-13 补数据落点（同前）与豁免审批链路；⑦ §7.4 开关层级改 A1–A8 并补开关方向不对称裁定（关停 L1 / 恢复 L3）与页面指引；⑧ §2.3 补等待态滞留可见性边界场景（← 05 v1.3 裁定）；⑨ §5.3 北极星指标补计数口径与去重规则（原缺可测定义）；⑩ §3 核心对象摘要补齐 8 个对象（对齐 05 §1.1 的 23 对象清单）；⑪ FR-18/19 分期澄清（自 M1/M2 起，非始于 M2）；⑫ §0 一致性检查更新（US-FR 双向核查、补「对齐 05 对象清单」条目） |
