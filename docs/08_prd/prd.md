# HuntAI Test PRD v2 综合交付版——企业内部 AI 自动化测试平台

> - **文档版本**：v2（2026-08-29）
> - **状态**：终版需求综合（可评审、可测试）
> - **仓库阶段**：Stage 8（`docs/08_prd`）；历史别名「12-PRD / 流程图 Stage 12 槽位」仅作溯源，不另起阶段
> - **替代**：v1.6 中期版
> - **评审对象**：产品、设计、工程、数据、安全、法务（含合规）
> - **吸收范围**：本文已吸收建模（problem_model.md v1.4）、C1–C4 交互链、前后端边界规范、API 挂钩与架构已定稿原则。`docs/05_prototype` 无约定产出，禁止虚构 `prototype_spec`；页面以 [frontend_design_spec](../06_architecture_design/frontend_design_spec-v1.0.md) P01–P25 为准

**输入优先级**（冲突不自行裁决，标 `[CONFLICT]` 并见第 8 章）：

1. 现行 US/FR 编号（本仓库原 `prd.md` v1.6）
2. `problem_model.md` v1.4（23 对象与状态机唯一事实源）
3. C1–C4 交互链
4. `frontend_backend_boundary_spec`（路径 v1.0 文件，文内 Draft v1.1）
5. `frontend_design_spec` P01–P25
6. `api_spec.md` 仅作验收挂钩，不把接口清单写成功能清单
7. `architecture.md` 已定稿原则

**编号纪律**：US-01…US-19、FR-01…FR-19 不得改号、不得删除另起；验收标准为新序列 `AC-001` 起（第 7 章）；禁止 `BR-xxx`、禁止编造 `API-xxx`。

**纪律**（验收与表述不得相反）：受理 ≠ 完成；SSE ≠ 命令通道；`APPROVED` ≠ `EXECUTED` + `execution_result=ok`；`execution_result=unknown` 须对账 / 人工接管，禁止盲重试或按成功放行；不得要求展示 Restricted 明文、token 明文、Prompt 原文。

**目录**：[0 一致性检查](#0-一致性检查相对-v2-七块重跑) · [1 背景与目标](#1-需求背景与用户目标) · [2 用户故事](#2-用户故事) · [3 功能清单](#3-功能清单) · [4 核心流程](#4-核心流程与关键交互) · [5 状态权限](#5-状态异常与权限) · [6 数据与接口](#6-数据与接口关联) · [7 验收标准](#7-验收标准) · [8 Out of Scope](#8-out-of-scope冲突登记) · [附录 A–E](#附录-a--ai-能力规格与-prompt-contract)

---

## 0. 一致性检查（相对 v2 七块重跑）

v2 正文按七块组织：① 需求背景与用户目标（第 1 章）；② 用户故事 + 功能清单（第 2–3 章）；③ 核心流程与关键交互（第 4 章）；④ 状态、异常、权限（第 5 章）；⑤ 数据与接口关联（第 6 章）；⑥ 验收标准 AC-xxx（第 7 章）；⑦ Out of Scope（第 8 章）。本检查相对七块重跑，**不假装 v1.6 的 FAIL / PARTIAL 已消失**。

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| ① 需求背景与用户目标（第 1 章） | ✅ PASS | 承接 v1.6 §1：P1–P5、目标用户、BG-1/2/3、非目标六条；未另起故事。基线仍 TBD，未把未批「90 天」写成默认 |
| ② 用户故事 + 功能清单（第 2–3 章） | ✅ PASS | US-01…US-19 故事原文未改；每个 US 对应 1 个 FR，反向 19 个 FR 均有 US。**FR-01…FR-19 全在第 3 章清单**，无改号、无删除另起、无 `BR-xxx` |
| ③ 核心流程与关键交互（第 4 章） | ✅ PASS | C1–C4 用户可感知步骤已标本地 vs 必调 API；权威成功对照边界 §6 |
| ④ 状态、异常、权限（第 5 章） | ✅ PASS | 状态 ⊆ problem_model；无第 24 对象；`not_evaluated` 仅 Proposed；角色四值；跨租户「资源不存在」 |
| ⑤ 数据与接口关联（第 6 章） | ✅ PASS | 每 FR 列对象与查询/命令/SSE；系统内部单独标注；未编造 `API-xxx` |
| ⑥ 验收标准 AC-xxx（第 7 章） | ✅ PASS | AC-001…AC-088，每 FR ≥1 条；可二元判定；LDAP 非 M0 必过 |
| ⑦ Out of Scope（第 8 章） | ✅ PASS | 含 §1.5、边界 §5.2、M4、Proposed、[GAP]、[CONFLICT] |
| 领域对象 ⊆ 05 §1.1（23 个） | ✅ PASS（本章） | 本草稿未新增对象。23 对象唯一事实源为 problem_model.md v1.4：Organization、User/ProjectMember、Project、ExecutionEnvironment、TestCase(+Version)、TestPlan、TestRun、CaseResult/StepRun/Artifact、FailureCluster、EvidenceObject、ApprovalRequest、AIInvocationLog、AuditEvent、Skill(+SkillVersion)、ModelRoute、PerfBaseline、ReleaseTask、ApiToken、Connector、CopilotSession、OrgQuota、QualityGatePolicy、GateEvaluation |
| 无 `not_evaluated` 已批准枚举 | ✅ PASS（本章） | FR-12 简述改为「缺配时无 GateEvaluation + 明确 reason，不得默认通过」；Proposed `not_evaluated` 不得写入已定需求（见第 8 章） |
| 页面 ⊆ P01–P25 | ✅ PASS | 第 2/3 章「主页面」均取 frontend_design_spec；无虚构页面、无 `prototype_spec`（`docs/05_prototype` 无约定产出） |
| 业务/用户目标 → 指标 | ✅ PASS | 第 1.4 节 BG-1/2/3 均配可测指标 + 目标值 + 时间范围 |
| 指标 → 基线 | ❌ **FAIL（3 项，同 v1.6）** | ① 测试分析中位耗时基线无我方数据；② AI 生成采纳率基线无数据；③ 每成功工作流成本基线无数据。全部标 **TBD**，由平台负责人 + QA 负责人在 M0 第 2 周前盘点回填（Q1）；本文目标值为假设目标，基线回填后须复核。**不阻塞评审，阻塞 M1 放行** |
| 风险 → 负责人 | ⚠️ **PARTIAL（同 v1.6）** | 风险已配角色级负责人（附录 / 第 8 章沿用）；**具体人名 TBD**（Q8，M0 启动会指派） |
| AI 能力编号完整性 | ✅ PASS（沿用） | A1–A8 连续无断号；正文迁入附录，本章不展开 |
| 「智能 / 准确 / 实时」禁用 | ✅ PASS（本章） | 未引入不可测形容词。US-03「15 分钟内决策」为故事原文，可测时效以附录 SLO / BG-1 为准，本章不发明新 SLO |
| 引用文档版本对齐 | ✅ PASS（v2 时点） | 输入按文首优先级：prd.md v1.6（编号）、problem_model.md v1.4、C1–C4、边界规范路径 v1.0 / 文内 Draft v1.1、frontend_design_spec P01–P25、api_spec.md（仅挂钩）、architecture.md 已定稿原则。各被引文档以文首版本头为唯一事实源 |

**结论：第 1–8 章与附录已齐。仍存在 1 项 FAIL（指标基线 TBD）与 1 项 PARTIAL（风险人名 TBD），不假装通过。不阻塞评审，但指标基线阻塞 M1 放行。**

---

## 1. 需求背景与用户目标

### 1.1 摘要

HuntAI Test 是企业内部自用（≤1000 用户、部门级多租户）的 AI 自动化测试平台：以接口 / Web / 性能三大自动化域为核心，用 AI 做用例生成、失败聚类与归因、自愈建议，用确定性工作流、副作用分级、审批与证据链约束一切有副作用的动作，并与既有 Jira / GitHub / Confluence / CI-CD / Release 系统打通形成端到端质量闭环。一期（M0–M3）聚焦 AI 自动化测试；Release 编排与全局 Copilot 为平台模块（M3 起），本 PRD 一并纳入但明确分期。

本 v2 已吸收建模、交互链、前后端边界与 API 挂钩；原型约定产出仍缺，页面以 frontend_design_spec P01–P25 为准。

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

### 1.4 业务目标（≤3，均配指标 / 基线 / 目标值 / 时间范围）

| # | 目标 | 指标（可测定义） | 基线 | 目标值 | 时间范围 |
| --- | --- | --- | --- | --- | --- |
| BG-1 | 回归分析提效 | 「CI/执行完成 → 分诊报告被审阅通过」中位耗时 | **TBD**（M0 第 2 周盘点） | 较基线下降 ≥50% | M2 上线后 3 个月 |
| BG-2 | 质量门禁普及 | 核心项目 CI 中门禁结论写入 exit code 的流水线占比；关键字段首次接受率（生成内容未经修改被接受的比例） | 0%（新平台）；接受率基线 **TBD** | 核心项目 100% 覆盖；首次接受率 ≥80% | M2 结束时；接受率 M1 起 3 个月 |
| BG-3 | 可审计质量证据链 | 证据覆盖率（关键结论挂有效 evidence_ref 的比例）；外部系统误写次数（未经有效审批的外部写操作） | 0%（新平台） | 覆盖率 ≥95%；误写 = 0（硬性） | M2 起 3 个月；误写永久 |

基线三项仍为 **TBD**（见第 0 章 FAIL / Q1）。目标值为假设目标，不得把未批「90 天」写成默认保留期。

### 1.5 非目标（明确不做什么）

1. 不替代 Jira / Confluence / GitHub / CI-CD / Release 系统——只做单向读取 + 审批后写入，不做双向全量同步；
2. 不自研压测引擎（包装 Locust/k6）、不做 APP 自动化、不做计费/白标/Workflow Builder/软件目录；
3. 不做无人审批的 AI 自动改写/自动应用（一切 L2+ 副作用必须 HITL）；
4. 不做对外 SaaS / 多租户计费；
5. 不复制 TestHub（GPL-3.0）任何源码——只借鉴机制；
6. 一期不做：视觉回归、语义去重、NL2Script、MCP 对外暴露（M4 评估）。

详见第 8 章 Out of Scope（含边界 §5.2 纯本地、M4、Proposed）。

---

## 2. 用户故事

故事原文取自 v1.6 §2.1，未改写。US-03「15 分钟内决策」保留故事原文；可测时效以附录 SLO / BG-1 为准，本章不发明新 SLO。主页面取 frontend_design_spec P01–P25；主流程取 C1–C4 或「无」。

| US | 故事（作为…我希望…以便…） | 映射 FR | 阶段 | 主页面 | 主流程 |
| --- | --- | --- | --- | --- | --- |
| US-01 | 测试工程师：导入 OpenAPI 后 AI 生成接口用例草稿，人工审阅后入库 | FR-05 | M1 | P07 / P05 | C1 |
| US-02 | 测试工程师：接口失败时得到带证据的归因与修复建议（不自动应用） | FR-06 | M1 | P09 / P13 | C4 |
| US-03 | Test Lead：一次执行后看到失败聚类 + 阻塞判断 + 历史对比，15 分钟内决策 | FR-07 | M1 | P09 | C4 |
| US-04 | 测试工程师：Web 用例执行自动留存截图/视频/Trace，可回放 | FR-09 | M2 | P13 / P09 | C1 |
| US-05 | 测试工程师：定位器失效时收到自愈建议，diff 预览确认后生效并可回滚 | FR-10 | M2 | P13 | C2 / C4 |
| US-06 | 开发：PR 上看到 Check Run 门禁结论，FAIL 时 CI 变红 | FR-13 | M2 | P12 / P03 / P25 | C1 |
| US-07 | Test Lead：失败用例一键创建 Jira 缺陷，附证据与复现步骤 | FR-14 | M2 | P09 | C4 / C1 |
| US-08 | 性能工程师：配置压测场景（白名单环境 + 审批 + 并发预算）并得到基线对比 | FR-11 | M3 | P16 | C2 / C3 |
| US-09 | Release Manager：基于 Jira 版本创建 Release Task，Readiness Gate 通过后经确认调用 Release 系统 | FR-15 | M3 | P17 / P06 | C1 |
| US-10 | 全员：Copilot 用自然语言查询测试资产（只读） | FR-16 | M3 | P18 | 无 |
| US-11 | 平台管理员：按部门设置 AI Token 预算并查看成本/质量看板 | FR-03 | M0 | P21 / P01 | 无 |
| US-12 | 平台管理员：在审批中心统一处理所有 HITL 请求（参数哈希绑定） | FR-04 | M0 | P10 | C2 |
| US-13 | 测试工程师：对难以脚本化的流程，用自然语言用例经 Skill+Agent 动态执行探索，成功轨迹一键固化为脚本入库 | FR-19 | M2 / M4 | P14 | C3 |
| US-14 | 已有 Jenkins pipeline 的系统 Owner：在平台创建引用型用例绑定我的 Job，触发后平台采集日志/报告并进入统一分诊与门禁，零迁移获得平台能力 | FR-18 | M1 / M2 | P15 / P08 | C3 |
| US-15 | 部门 Owner / 全体用户：用企业 SSO 账号登录，只能看到本部门与本项目的测试资产，越权访问一律不可达 | FR-01 | M0 | P04 | 无 |
| US-16 | 平台管理员 / 安全：任何 AI 调用都能在一处查到调用者、模型、prompt 版本、真实用量与成本，不存在绕过日志的调用路径 | FR-02 | M0 | P21 | 无 |
| US-17 | 测试工程师 / SRE：执行任务不会永久卡在运行中——重启、失联、超时都有确定的收敛状态，等待态可见且可人工取消 | FR-08 | M1 | P09 / P08 | C3 |
| US-18 | 性能工程师 / Test Lead：压测的 p95 与错误率与接口/Web 用同一套门禁阈值和结论对象，发布决策看到的是同一份质量口径 | FR-12 | M3 | P11 / P12 | C1 |
| US-19 | 安全工程师：每个有副作用的动作在执行前都经统一策略裁决（放行/拒绝/需审批/需重认证），未声明副作用等级的动作默认拒绝 | FR-17 | M0 | P10 | C2 |

---

## 3. 功能清单

FR 编号与含义冻结自 v1.6 §2.2，简述压缩为用户可感知能力。验收标准见第 7 章；领域对象与 API 挂钩见第 6 章。主页面 ⊆ P01–P25；主流程为 C1–C4 或「无」。

| FR | 简述 | US | 里程碑 | 主页面 | 主流程 |
| --- | --- | --- | --- | --- | --- |
| FR-01 | 组织（部门）→ 项目两级；SSO（OIDC）登录；角色 owner / admin / tester / viewer；租户隔离在 ORM / 中间件强制。LDAP **[CONFLICT]**（见第 8 章），不作为 M0 双登录必做 | US-15 | M0 | P04 | 无 |
| FR-02 | 所有 AI 调用（无旁路）记录真实 usage、模型、prompt 版本、成本、延迟、数据分级，按部门归集。不要求展示 token 明文或 Prompt 原文 | US-16 | M0 | P21 | 无 |
| FR-03 | 部门级 Token 预算 + 超限熔断提示；成本 / 质量看板（采纳率、无据结论率、成功率）。超预算后新 AI 调用被拒并通知 Owner | US-11 | M0 | P21 / P01 | 无 |
| FR-04 | 统一 HITL 队列；审批卡片九要素；参数哈希绑定。执行结果区分 ok / failed / unknown，unknown 进入对账 / 人工接管。`APPROVED` ≠ `EXECUTED` + `execution_result=ok` | US-12 | M0 | P10 | C2 |
| FR-05 | OpenAPI / Postman 导入 → 生成默认不落库 → 审阅 → 保存并打 `ai-generated` 标签；采纳率 / 修改幅度埋点。生成失败有显式告警，禁止静默返回空 | US-01 | M1 | P07 / P05 | C1 |
| FR-06 | 输入执行日志 + 响应 → 失败原因分类（7 值：env_down / auth_expired / locator_stale / assertion_real_bug / flaky / data_issue / unknown）+ confidence + fixes 建议；confidence ≥0.7 才显示「可应用」，应用必须走 FR-04 审批 + 快照 + 回滚 | US-02 | M1 | P09 / P13 | C4 |
| FR-07 | 归一化结果 → 聚类 + 阻塞判断 + 历史对比；显示证据链接、置信度、无法判断项、用户修改历史 | US-03 | M1 | P09 | C4 |
| FR-08 | 执行有确定收敛态（重启 / 失联 / 超时不永久卡在运行中）；等待态可见且可人工取消；变量解析失败必报错；受理回执 ≠ 业务完成 | US-17 | M1 | P09 / P08 | C3 |
| FR-09 | Playwright 执行器独立于 API 进程；证据三件套（截图 / 视频 / Trace）自动上传对象存储；失败步骤有 Trace 可回放 | US-04 | M2 | P13 / P09 | C1 |
| FR-10 | 主备定位器 + 健康度；失效时 AI 给出修复建议（仅建议），落地走 diff → 审批 → 快照 → 回滚。无自动改写路径 | US-05 | M2 | P13 | C2 / C4 |
| FR-11 | 包装 Locust / k6；执行走统一 TestRun 10 态；目标环境白名单 + 高危审批 + 全局并发预算 + kill switch。不自研压测引擎 | US-08 | M3 | P16 | C2 / C3 |
| FR-12 | max_p95_ms / max_error_rate 与 FR-13 同一 QualityGatePolicy、同一 GateEvaluation。缺配时无 GateEvaluation + 明确 reason，不得默认通过 | US-18 | M3 | P11 / P12 | C1 |
| FR-13 | PR / push 触发 → 执行 → Check Run 三段式回写；门禁结论写入 CI exit code。豁免须走 FR-04。阈值与模式 = QualityGatePolicy，单次结论 = GateEvaluation | US-06 | M2 | P12 / P03 / P25 | C1 |
| FR-14 | 单向创建 Jira 缺陷 + 链接回写；用例关联 story；未经审批不得写入；缺陷含证据附件 | US-07 | M2 | P09 | C4 / C1 |
| FR-15 | Jira 版本圈定 → 范围快照 → 质量证据汇聚 → Readiness Gate → AI 草稿 → 审批后调用 Release 系统。AI 草稿禁止自动推送 | US-09 | M3 | P17 / P06 | C1 |
| FR-16 | Copilot 最小版：只读技能 + 全量日志 + 权限感知 + 服务端会话。越权阻断；能力开关真实生效 | US-10 | M3 | P18 | 无 |
| FR-17 | 所有工具 / 动作声明 L0–L4；Gate 输出 ALLOW / DENY / REQUIRE_APPROVAL / REQUIRE_REAUTH。未声明副作用等级的动作默认拒绝 | US-19 | M0 | P10 | C2 |
| FR-18 | 执行环境为一等注册对象；引用型用例不托管脚本，仅声明目标 Job / 触发参数 / 采集配置 / 门禁阈值映射；归一化统一 TestRun 后与 FR-07 同一分诊、同权进门禁。M1 交付 Jenkins 触发 + JUnit 采集，M2 完善多格式适配器 | US-14 | M1 / M2 | P15 / P08 | C3 |
| FR-19 | Script Mode = 确定性脚本执行（进门禁 / 发布证据）；Agent Mode = 用例意图动态执行，结果不进门禁，轨迹可一键转脚本草稿（人工确认后入库）。M2 试点、M4 完整 | US-13 | M2 / M4 | P14 | C3 |

> **脚注（FR-08）**：实现选型见 `architecture.md`（Temporal 持久工作流等）；**选型 ≠ 生产就绪**（开放问题 Q3：托管 / 自托管、恢复、版本、容量、成本、值班 Gate）。不把 Temporal / Outbox / Worker 管理面写成用户功能。

---

## 4. 核心流程与关键交互

> 综合来源：交互链 C1–C4、前后端边界规范 §5.1 / §5.2 / §6 / §7、业务建模 §2.1–2.6、前端设计规范 P01–P25。不新增页面、对象、状态或 API。API 编号仅取自 `api_spec.md` §6 已列 ID。权威成功一律引用边界 §6，不以按钮反馈、跳转或 OpenAPI 回执为完成。

页面编号对照（前端设计规范 P01–P25 表；交互链原文只用名称）：

| 编号 | 页面 |
| --- | --- |
| P01 | 工作台 |
| P02 | 项目总览 |
| P03 | 集成 |
| P04 | 项目设置 |
| P05 | 用例库 |
| P06 | 测试计划 |
| P07 | 生成审阅页 |
| P08 | 执行发起页 |
| P09 | TestRun 列表/详情 |
| P10 | 审批中心 |
| P11 | 质量门禁策略 |
| P12 | 门禁评估历史 |
| P13 | Web 用例详情 |
| P14 | Agent 任务详情 |
| P15 | 环境管理 |
| P16 | 性能压测 |
| P17 | Release 任务 |
| P18 | Copilot 对话 |
| P19 | 技能管理 |
| P20 | 证据中心 |
| P21 | AI 成本看板 |
| P22 | 模型路由配置 |
| P23 | AI 能力开关与降级 |
| P24 | 审计检索 |
| P25 | 集成中心 |

**无一页面完全本地。** 即使以呈现为主的页，领域数据、状态、权限与结论均须经 §5.1 查询或写接口；§5.2 仅覆盖提示性校验与呈现层。

---

## 4.0 跨链交互纪律（权威成功与通道）

以下规则对 C1–C4 全部适用，后文步骤不再重复展开。

1. **命令回执 / API-071 ≠ 业务完成。** API-071 查询的是操作回执（协议面，非领域对象）。回执可查、命令「已受理」不等于领域进入权威成功态。对照边界 §6：「按钮反馈 ≠ 业务成功；前端在收到后端确认前只可呈现『受理 / 提交中』乐观态，不得将 UI 推进为『已完成』。」
2. **SSE API-210–213 是非命令通道。** 只订阅进度 / 解析 / 聚类 / 轻量 hint，不承载取消、批准等写意图。与 GET 资源冲突时 **以 GET 为准**。SSE **断连 ≠** TestRun `FAILED` / `TIMEOUT`，也 ≠ ApprovalRequest `EXPIRED`（断连属网络类，业务语义未知）。
3. **`APPROVED` ≠ `EXECUTED` + `execution_result=ok`。** 边界 §6-6：「操作回执」非权威；权威成功条件为「ApprovalRequest=APPROVED；**执行成功另判** EXECUTED + execution_result=ok（两段不同）。」`execution_result=unknown` 必须进入对账 / 人工接管，**禁止盲重试，禁止当成功放行**。
4. **发起执行的权威成功 = TestRun `PENDING` + `run_id`（边界 §6-3），不是跳转 P09。** 边界 §6-3：前端即时反馈是「跳转 P09」（非权威）；权威成功条件是「TestRun(PENDING) 创建返回 run_id」。
5. **取消：前端「信号已持久化」≠ `CANCELLED`（边界 §6-8）。** 即时反馈是「信号已持久化送达」；权威成功条件是「TestRun 到 CANCELLED（经 STOPPING）；已采集结果照常入库」。
6. **参数校验：本地通过不构成受理保证（边界 §6-4）。** 权威成功条件是「后端 VALIDATING→RUNNING」。
7. **执行结果不得由 SSE 进度推定终态（边界 §6-5）。** 权威成功条件是「后端终态（SUCCEEDED / FAILED / CANCELLED / TIMEOUT）」。

---

## 4.1 C1 北极星质量闭环

**名称：** 北极星质量闭环（端到端主链）。

**主 FR：** FR-05 / FR-13 / FR-14 / FR-15 / FR-18。交叉衔接 FR-01 / FR-02 / FR-03 / FR-04 / FR-06 / FR-07 / FR-08 / FR-09 / FR-10 / FR-11 / FR-12 / FR-19（细节归 C2 / C3 / C4）。

**页面主线（名称→编号）：** 项目总览（P02）→ 用例库导入（P05）→ 生成审阅（P07）→ 入库（P05）→ 执行发起（P08）→ TestRun（P09，Agent 分支 P14）→ 门禁策略 / 评估（P11 / P12）→ 审批 / Jira / Release（P10 / P17）→ 证据中心（P20）。支撑：工作台（P01）、环境管理（P15）、Web 用例详情（P13）、性能压测（P16）、审计检索（P24）等，均属 25 页清单，不新造页面。

### 4.1.1 用户可感知步骤

1. 打开项目总览（P02），确认工具连接状态与 Jira 映射后再进入用例生产。  
   **必须调 API（边界 §5.1）：** API-012。

2. 在用例库（P05）浏览 / 筛选（含 `ai-generated`）、查看版本历史。  
   **必须调 API（边界 §5.1）：** API-030、API-037。

3. 登记 OpenAPI / Postman / curl 导入源并发起 A1 生成（默认不落库）。  
   **必须调 API（边界 §5.1）：** API-205、API-180。  
   **权威成功（边界 §6-2）：** 「后端返回草稿 + failed_items；**partial 由后端判定**（失败条目显式呈现）。」生成中状态结束不是权威完成。

4. 订阅 A1 生成进度。  
   **必须调 API（边界 §5.1）：** API-211（SSE，非命令、非终态）。完成仍以 API-181 / API-182 GET 为准。

5. 在生成审阅页（P07）左右分栏审阅草稿：逐条采纳 / 编辑 / 弃用；partial 失败条目在「生成失败」列表可见，禁止静默丢弃。未点保存前的编辑。  
   **前端本地（边界 §5.2）：** P07 提交前暂存。

6. 保存为草稿（打 `ai-generated` 标签）。  
   **必须调 API（边界 §5.1）：** API-032。  
   **权威成功（边界 §6-1）：** 「TestCase(DRAFT) + Version 创建返回（含 id / 版本）。」

7. 提交评审。  
   **必须调 API（边界 §5.1）：** API-034（DRAFT → PENDING_REVIEW）。

8. 人工评审：通过（可关联 `jira_story_key`）或驳回。`ai-generated` 禁止直写 ACTIVE。  
   **必须调 API（边界 §5.1）：** API-035。通过 → ACTIVE；驳回 → DRAFT。

9. 在用例库选取 ACTIVE 用例，进入执行发起页（P08）。  
   **必须调 API（边界 §5.1）：** API-030（读可选性）。失效用例（`validity=invalid`）不可执行标识由后端下发，前端只渲染。

10. 执行发起页三层结构（顺序不可调换）：模式（Script / Agent，Agent 显示受限说明）→ 环境（仅 ACTIVE；选外部 CI 时仅 Script）→ 参数表单（引用型按 Job Schema 动态生成）+ 定时配置；联动置灰与即时校验。  
    **前端本地（边界 §5.2）：** 三层渲染、联动置灰、动态表单、表单即时校验。  
    可选环境、容量 / 配额、Job Schema、用例可选性：  
    **必须调 API（边界 §5.1）：** API-069、API-070。

11. 点击「发起执行」（手动 / 调度配置）。  
    **必须调 API（边界 §5.1）：** API-062（会话，`trigger_type=manual|schedule`）。Token 集成入口为 API-080（同路径，`trigger_type=api_token`，非页面主路径）。CI webhook 为系统入口 API-090，无前端交互。  
    **权威成功（边界 §6-3）：** 「TestRun(PENDING) 创建返回 run_id」——**不是**跳转 P09。

12. 打开 TestRun 列表 / 详情（P09）：页头 10 态进度条、用例结果、证据查看器、`execution_source` 徽标（agent 型「不进门禁」）。  
    **必须调 API（边界 §5.1）：** API-060、API-061、API-064；制品元数据 / 内容 API-220、API-221。  
    进度 / 解析进度：  
    **必须调 API（边界 §5.1）：** API-210（SSE，非终态）。  
    **权威成功（边界 §6-5）：** 「后端终态（SUCCEEDED / FAILED / CANCELLED / TIMEOUT）；前端不得由进度推定终态。」

13. Agent Mode 分支：打开 Agent 任务详情（P14）查看轨迹时间线、incomplete 标记、终止按钮。  
    **必须调 API（边界 §5.1）：** API-067。终止走 API-063，见 4.0 第 5 条与 C3。  
    **权威成功（边界 §6-16）：** 「A8 status + assertion_results（后端判 SUCCEEDED / FAILED；超步 / 超时 = incomplete）。」

14. 配置质量门禁策略（P11）：通过率 / p95 / 错误率，「仅报告 ⇄ 阻断」显式开启。  
    **必须调 API（边界 §5.1）：** API-140、API-141、API-142、API-143。

15. TestRun 终态后的门禁评估与 GitHub Check Run 三段式回写（仅 `execution_source ∈ {script, external_ci}`；agent 不生成 GateEvaluation）。  
    **系统内部，无产品 API。** 入站观察可经 API-090。  
    **权威成功（边界 §6-9）：** 「可评估时为 GateEvaluation.result（pass / fail / waived）+ 逐阈值明细；CANCELLED / TIMEOUT / 缺配 / partial 当前为无 GateEvaluation + 明确 reason，绝不默认通过。」

16. 查看门禁评估历史、Check Run 关联、豁免记录（P12）。  
    **必须调 API（边界 §5.1）：** API-144、API-145、API-146。豁免（`gate_waiver`）走 C2（Preview API-120）。  
    **权威成功（边界 §6-13）：** 「gate_waiver 审批 EXECUTED 且豁免记录可查。」

17. 从 P09 聚类簇一键创建 Jira 缺陷（附证据与复现步骤）→ 审批中心（P10）九要素卡片。  
    **必须调 API（边界 §5.1）：** API-120（Preview）。批准 / 拒绝 / 重提与 consume 见 C2。分诊细节见 C4。  
    **权威成功（边界 §6-7）：** 「连接器返回 {status, external_request_id}；issue 链接回显。」且须满足 §6-6 两段式（APPROVED 与 EXECUTED+ok 分判）。

18. Release 任务（P17）：Jira 版本圈定 → 范围快照 DRAFT → Readiness Gate 红黄绿 + A5 草稿（禁止自动推送）→ 推送预览 + 确认（`release_push`）。  
    **必须调 API（边界 §5.1）：** API-152、API-151、API-155；确认走 API-120 + C2。重试 / 取消：API-153、API-154。SUBMITTED → READY 的外部状态回传：  
    **系统内部，无产品 API**（观察入口 API-090）。  
    **权威成功（边界 §6-10）：** Readiness「后端评估结果数据（前端不自行汇总证据判定）。」  
    **权威成功（边界 §6-11）：** release_push「ReleaseTask SUBMITTED→READY（Release 系统 webhook 状态回传）。」提交回执不是 READY。

19. 证据中心（P20）检索与证据包导出（ZIP / MD / JSON）；审计检索（P24）追溯 Check Run / 外部写 / 审批。  
    **必须调 API（边界 §5.1）：** API-026、API-027、API-028；审计 API-024、API-025。导出进度可订 API-212（SSE，非命令）。

20. 工作台（P01）聚合：待审批、进行中 TestRun、门禁异常、部门预算余量。等待态必须持续可见、显示滞留时长，不得因长时间等待隐藏。  
    **必须调 API（边界 §5.1）：** API-020；预算余量 API-017。

### 4.1.2 异常与分支（浓缩）

| 用户可见情况 | 走向（已有状态 / 行为，不新造） |
| --- | --- |
| A1 单条失败 / 解析失败 | 显式 failed_items；批次 partial；禁止静默空返回。权威见 §6-2。 |
| 模型网关不可用 | 仅 AI 增强降级；执行 / 报告 / 门禁不受影响；横幅不静默；A1 入口可置灰，导入本身仍可用。 |
| 手动终止 | 见 4.0 第 5 条与 C3；PENDING 可直达 CANCELLED；RUNNING 经 STOPPING。 |
| 外部 Job 排队过久 | 停留 WAITING_EXTERNAL，可见 + 告警，可幂等取消；超时不自动迁移（阈值 **TBD**）。 |
| 审批超时 | ApprovalRequest → EXPIRED，**不自动放行**；关联 TestRun **停留 WAITING_APPROVAL**。 |
| 心跳超时（僵尸回收） | RUNNING → TIMEOUT；已产生结果照常入库。TTL / 心跳周期 **TBD**。 |
| 审批拒绝 | ApprovalRequest → REJECTED；执行中 L2+ 则 TestRun WAITING_APPROVAL → CANCELLED。过期不走此边。 |
| 审批后改参数 | anti-TOCTOU：哈希不一致则拦截，卡片「审批已失效」，须重新审批。 |
| 引用型 Job 被删 / 改名 | 不进执行队列；`validity=invalid`（系统标记，可逆，不是第五生命周期态）。 |
| Check Run 回写失败 | 重试 + 告警；门禁结论仍以评估结果为准，不默认通过。 |
| Release 调用失败 | SUBMITTED → FAILED_RETRYABLE；人工幂等重试 → SUBMITTED，或放弃 → CANCELLED。 |
| Readiness 不达标 | 允许带豁免说明发布，须 `gate_waiver`（C2），留痕可审计。 |
| 超大报告 | 分片解析进度可见；超时则已完成部分入库 + 显式失败标记，不静默截断。 |
| Agent 超步 / 总超时 | 强制终止，轨迹 incomplete，无自动重试。 |
| 跨租户引用 | 用户看到「资源不存在」（见第 5 章）。 |

---

## 4.2 C2 审批链

**名称：** 审批链（横切 C1 / C3 / C4 全部 L2+ 副作用点）。

**主 FR：** FR-04。关联 FR-01、FR-02、FR-06 / FR-10（`heal_apply`）、FR-11（`perf_high_risk`）、FR-14（`jira_write`）、FR-15（`release_push`）、FR-17（Policy Gate）、FR-18（`env_register`）、FR-19（`agent_tool_action`）。

**入口场景（已冻结 action_ref，不扩枚举）：** `jira_write`（P09）、`heal_apply`（P09 / P13）、`perf_high_risk`（P16 / P08）、`release_push`（P17）、`env_register`（P15）、`agent_tool_action`（P14）、`gate_waiver`（P12）、`kill_switch_restore`（P23，见第 5 章）。viewer 不能发起 L2+。四眼：`approver_id ≠ initiator_id`；发起人打开卡片时「批准」置灰仅为呈现，服务端强制复核。

### 4.2.1 用户可感知步骤

1. 在业务页提交 L2+ 动作的 Preview 参数（Policy Gate 裁决 REQUIRE_APPROVAL 才入队；九要素缺一不入队；`param_hash` 由后端生成）。  
   **必须调 API（边界 §5.1）：** API-120。回取 Preview：API-121。  
   L0 / L1 输出 ALLOW **不进本链**；DENY 不入队并留痕。

2. 发起页提示「已进入审批」；执行中触发时 P09 进度条 WAITING_APPROVAL 高亮。工作台（P01）待审批列表 / 进行中 run 感知。  
   **必须调 API（边界 §5.1）：** API-020（工作台）；P09 状态 API-061。卡片数据不在前端组装。

3. 审批中心（P10）审阅九要素卡片（顺序冻结：动作与目标资源 → 前后 diff → 数据来源与模型 / Skill 版本 → 风险等级 L0–L4 色标 + 成本估计 → 回滚能力 → 参数哈希默认折叠）。批量队列、超时升级提示。  
   **必须调 API（边界 §5.1）：** API-110、API-111。  
   **前端本地（边界 §5.2）：** 分区渲染、参数哈希折叠展开、发起人「批准」置灰（入口可见性）、确认对话。

4. 操作区三键：**批准 / 拒绝（附理由）/ 修改后重新提交**。  
   **必须调 API（边界 §5.1）：** API-112（批准 / 拒绝）；API-113（重提 = **新** ApprovalRequest、新 `param_hash`，`initiator_id` = 重新提交人，保留 origin 归因链）。  
   前端即时反馈是操作回执，**不是**执行完成。  
   **权威成功（边界 §6-6）：** 「ApprovalRequest=APPROVED；**执行成功另判** EXECUTED + execution_result=ok（两段不同）。」

5. 批准后的执行前复核（anti-TOCTOU：Execute 哈希重算 + 权限重校验）与行锁 consume。  
   **系统内部，无产品 API。** 浏览器没有 Execute / consume 端点。  
   仅 `execution_result=ok` 可推进目标聚合：`perf_high_risk` / `agent_tool_action` → TestRun WAITING_APPROVAL → RUNNING；`release_push` → ReleaseTask PENDING_CONFIRM → SUBMITTED；`env_register` → ExecutionEnvironment PENDING_APPROVAL → ACTIVE。`jira_write` / `heal_apply` **不迁移 TestRun**（run 已终态，见 C4）。`failed` 须重新发起审批；`unknown` 对账 / 人工接管，禁止盲重试或当成功。

6. 回跳发起页看状态回显（EXECUTED / REJECTED / EXPIRED；unknown 显示「结果待对账」）。证据中心 / 审计检索按 approval.bound_hash 追溯。  
   **必须调 API（边界 §5.1）：** 发起页对应 GET（如 API-061、API-151、API-101）；P20 API-026；P24 API-024。

7. TTL 到期：升级通知 `escalate_to`，仍未处理 → EXPIRED，**任何情况不自动放行**。撤回 / 上游取消 / APPROVED 后参数变更 → EXPIRED + reason（withdrawn / invalidated）。关联 TestRun 过期 **停留 WAITING_APPROVAL**（仅拒绝 / 人工取消走 CANCELLED）。  
   **系统内部，无产品 API**（TTL / 升级由后端计时）。数值 **TBD**。

### 4.2.2 九要素与自批约束（用户可见）

- 九要素 = 动作 / 资源 / diff / 数据来源 / 模型与 Skill 版本 / 风险等级 / 成本估计 / 回滚能力 / 参数哈希；分区顺序不得调换。
- `heal_apply`：应用前快照失败则 fail-close，不写新版本。  
  **权威成功（边界 §6-12）：** 「新 TestCaseVersion + current_version_id 更新（EXECUTED + execution_result=ok；快照失败 fail-close = 未成功）。」
- 第二次 consume：「该审批已被消费」，不产生第二次副作用（行锁，系统内部）。

---

## 4.3 C3 执行发起链

**名称：** 执行发起链（模式 × 环境 → TestRun 全路径 → 结果与证据）。

**主 FR：** FR-08 / FR-18 / FR-19。交叉 FR-01、FR-02、FR-03、FR-04、FR-05、FR-07、FR-09、FR-11、FR-13、FR-17。

**组合（不新造）：** Script × 平台执行器 → `execution_source=script`（进门禁）；Script × 外部 CI → `external_ci`（同权进门禁）；Agent × 平台执行器 → `agent`（**不进门禁**）；Agent × 外部 CI **一期不支持**（第二层外部 CI 时 Agent 置灰）。

前置：TestCase = ACTIVE 且（引用型）Job 存在性通过；环境 = ACTIVE；压测白名单外目标直接 DENY、不进审批。trigger_type 仅 `manual` / `schedule` / `ci_webhook` / `api_token`。

### 4.3.1 用户可感知步骤

1. 用例库（P05）按 ACTIVE 选取待执行用例，点「发起执行」。  
   **必须调 API（边界 §5.1）：** API-030。

2. 执行发起页（P08）三层配置：本地即时校验（未提交即可见）、模式 × 环境联动置灰、按 `params_schema_ref` 动态表单。  
   **前端本地（边界 §5.2）：** 表单即时校验、联动置灰、动态表单、确认对话与防抖。  
   **必须调 API（边界 §5.1）：** API-069、API-070。  
   **权威成功（边界 §6-4）：** 本地校验通过 **不是** 受理保证；权威为「后端 VALIDATING→RUNNING」。

3. 提交「发起执行」，冻结 snapshot（用例版本 / 环境 / 参数）；external_ci 写 `idempotency_key`。  
   **必须调 API（边界 §5.1）：** API-062 和 / 或 API-080。  
   **权威成功（边界 §6-3）：** 「TestRun(PENDING) 创建返回 run_id」，**不是**跳转 P09。命令回执 / API-071 可查 ≠ 执行完成。

4. 系统将 PENDING → VALIDATING（Job Schema / 双层变量 / Job 存在性）；通过 → RUNNING，失败 → FAILED（不进执行队列）。  
   **系统内部，无产品 API。** 用户在 P09 看到结果（API-061）。

5. P09 订阅执行 / 解析进度（WAITING_EXTERNAL 仅 external_ci 出现；WAITING_APPROVAL 高亮可跳 P10）。  
   **必须调 API（边界 §5.1）：** API-210（SSE，**非终态**）。终态只认 GET。断连不得标 FAILED / TIMEOUT。

6. 可选：Agent 型 run 打开 P14 轨迹。  
   **必须调 API（边界 §5.1）：** API-067。

7. 执行中遇 L2+（`perf_high_risk` / `agent_tool_action`）：TestRun → WAITING_APPROVAL，**走 C2**（API-120 → P01 / P10 → API-112 / API-113 → consume 系统内部）。审批过期不自动放行、不迁移出 WAITING_APPROVAL。

8. 外部 CI：幂等触发 → RUNNING → WAITING_EXTERNAL →（webhook 或轮询先到者）RUNNING → 终态；排队中可幂等取消。  
   **系统内部，无产品 API**（观察入口 API-090）。用户只见 P09 状态与滞留时长。

9. 人工终止 / 压测熔断 / kill switch：点取消或 P14 终止。  
   **必须调 API（边界 §5.1）：** API-063。  
   **前端本地（边界 §5.2）：** 确认对话。  
   **权威成功（边界 §6-8）：** 前端「信号已持久化送达」**≠** CANCELLED；权威为「TestRun 到 CANCELLED（经 STOPPING）」。STOPPING 卡死心跳超时可走 STOPPING → TIMEOUT（兜底）。

10. Agent 轨迹一键转脚本草稿（产物过 schema 校验）→ 人工确认后新 TestCase 以 DRAFT 入库，评审流归 C1。  
    **必须调 API（边界 §5.1）：** API-068。原 run 状态不变。

11. 工作台监控活跃 run；事后 P20 / P24 取证。  
    **必须调 API（边界 §5.1）：** API-020、API-026、API-024。

---

## 4.4 C4 失败分诊链

**名称：** 失败分诊链（终态之后：归一化 → 聚类 → 人工修正 → 建缺陷 / 自愈）。

**主 FR：** FR-06 / FR-07。交叉 FR-02、FR-04、FR-08、FR-09、FR-10、FR-13、FR-14、FR-17、FR-18。

**硬约束：C4 不迁移 TestRun 状态。** run 已处终态（终态吸收）。后续审批只作用于 ApprovalRequest；`WAITING_APPROVAL` 只出现在执行中 L2+（C2 / C3），本链不适用。自愈不迁移 TestCase 生命周期，只新增 TestCaseVersion 并更新 `current_version_id`。

主入口：终态 SUCCEEDED / FAILED 且含失败 CaseResult。旁路：CANCELLED / TIMEOUT 已入库失败结果同样归一化与聚类。无失败的 SUCCEEDED 不触发失败聚类。

既有 SLO（非新指标）：A2 在 run 完成后 **≤5 分钟**出报告（10k 用例级）。心跳 / 审批 TTL 等其它数值仍 **TBD**。

### 4.4.1 用户可感知步骤

1. 工作台（P01）发现终态失败 run / 门禁异常，进入列表。  
   **必须调 API（边界 §5.1）：** API-020。

2. TestRun 列表 / 详情（P09）按终态与 `execution_source` 定位 run。  
   **必须调 API（边界 §5.1）：** API-060、API-061。

3. 系统归一化（含 external_ci 适配器，确定性管道非 AI）并生成 FailureCluster（随 run 只读生成，无状态机）。  
   **系统内部，无产品 API。** 生成中进度：  
   **必须调 API（边界 §5.1）：** API-210（SSE，非命令；离开再进入不丢结果）。用户离开页面不取消聚类。

4. 阅读聚类报告：每簇五要素（类别 7 值枚举 / confidence / 阻塞判断 / 证据链接 / 人工修正入口）；「无法判断项」独立区块；修改历史；历史相似失败；agent 型「不进门禁」。  
   **必须调 API（边界 §5.1）：** API-130、API-131；相似失败 API-133；结果下钻 API-064、API-065、API-066；证据查看 API-220 / API-221。  
   **前端本地（边界 §5.2）：** 证据三件套切换、Trace 回放控件、URL 筛选状态。

5. 经簇卡片「人工修正入口」改正类别 / 阻塞判断等。  
   **前端本地（边界 §5.2）：** 提交前暂存（与 P07 同类：本地编辑，提交才调 API）。  
   提交留痕：  
   **必须调 API（边界 §5.1）：** API-132。未提交不写 `correction_history`。

6. 分支 A：一键创建 Jira 缺陷（自动附证据与复现步骤）。  
   **必须调 API（边界 §5.1）：** API-120，其后 **走 C2**（P10、API-112 / API-113；consume 系统内部）。  
   **C4 不迁移 TestRun。**  
   **权威成功：** 边界 §6-6 与 §6-7（两段式 + 连接器 `external_request_id` / issue 链接）。

7. 分支 B：自愈 / 定位器建议 diff 预览；**confidence ≥ 0.7 才显示「可应用」**（仅入口可见性；`can_auto_apply` 恒 false，无免审批路径）。  
   **前端本地（边界 §5.2）：** diff 查看器、入口可见性。  
   点击「可应用」：  
   **必须调 API（边界 §5.1）：** API-120，其后 **走 C2**（`heal_apply`）。快照失败 fail-close。回滚：API-039。  
   **权威成功（边界 §6-12）：** 「新 TestCaseVersion + current_version_id 更新（EXECUTED + execution_result=ok；快照失败 fail-close = 未成功）。」  
   **C4 不迁移 TestRun。** 应用结果在 P05 / P13 确认（API-030 / API-031 / API-037）。

8. P09 簇卡片回显审批结果：EXECUTED（Jira 链接 / 自愈已应用）/ REJECTED / EXPIRED / unknown「结果待对账」。  
   **必须调 API（边界 §5.1）：** API-061、API-111。

9. 证据中心 / 审计检索复用与追溯。Agent 型失败上下文在 P14（不进门禁，证据照常入链）。  
   **必须调 API（边界 §5.1）：** API-026、API-024；P14 为 API-067。

---

## 4.5 前端本地操作对照（边界 §5.2 全表）

下列为 **纯前端本地、无 API 调用** 的完整清单（对照 §5.1）。用于区分「提示」与「权威」，**不是**整页可离线工作的许可。

| # | 本地能力 | 说明 |
| --- | --- | --- |
| 1 | 七态渲染 | 默认 / 加载 / 空数据 / 无结果 / 错误 / 无权限 / 成功；另加链路特殊态（如 AI 降级横幅、WAITING_* 滞留）。状态值仍来自后端。 |
| 2 | 表单即时校验 | 格式 / 必填 / 类型，提示性；权威校验在后端。 |
| 3 | 联动置灰 | 模式 × 环境、非 ACTIVE 环境、角色只读呈现。 |
| 4 | 动态表单 | 按 `params_schema_ref` 渲染控件（Schema 本身由 API-070 供给）。 |
| 5 | 查看器 | diff、参数哈希折叠、Trace 回放、证据三件套切换。 |
| 6 | URL 状态 | 筛选 / 排序 / 分页进 URL。 |
| 7 | 响应式 | 布局降级，语义不变。 |
| 8 | 入口可见性 | confidence ≥ 0.7「可应用」、发起人「批准」置灰、里程碑入口隐藏——均仅呈现层。 |
| 9 | P07 / 聚类提交前暂存 | 草稿编辑、聚类修正：提交才调 API-032 / API-132。 |
| 10 | 确认对话与防抖 | 防重复点击；权威防重是幂等键 + 行锁。 |

SSE 订阅（API-210–213）属于边界 §5.1 进度订阅通道（SSE），**不在**本表。

---

## 5. 状态、异常与权限

状态与结果枚举 **必须是** 业务建模（problem_model §2.1–2.6）的子集，写法与枚举值与原文一致。不新增状态、不把 Proposed 写成已批准。

---

## 5.1 领域状态枚举（⊆ 业务建模）

### 5.1.1 TestCase（§2.1）

生命周期：**DRAFT、PENDING_REVIEW、ACTIVE、DEPRECATED**。

- 创建 / AI 审阅后保存 → DRAFT；提交评审 → PENDING_REVIEW；人工确认 → ACTIVE；驳回 → DRAFT；ACTIVE 废弃 / DRAFT 弃用 → DEPRECATED。
- `ai-generated` 必须经 PENDING_REVIEW → ACTIVE 人工确认，禁止生成直写 ACTIVE。
- **`validity`（`valid` / `invalid`）是系统标记，不是第五生命周期态。** 引用型 Job 被外部删除 / 改名 → `invalid`（可逆）；与人工 DEPRECATED 不同。

仅 ACTIVE 且 `validity=valid` 的用例可进入执行队列。

### 5.1.2 TestRun（§2.2）

十态：**PENDING、VALIDATING、RUNNING、WAITING_EXTERNAL、WAITING_APPROVAL、STOPPING、SUCCEEDED、FAILED、CANCELLED、TIMEOUT**。

- **终态 = 最后四态：** SUCCEEDED、FAILED、CANCELLED、TIMEOUT（终态吸收）。C4 在终态之后运行，**不迁移**本状态机。
- **无永久 RUNNING。** 活跃态必须心跳；无心跳超时自动转 TIMEOUT 并回收。不存在「永久 ACTIVE running」——TestRun 枚举中无 ACTIVE；活跃执行态是 RUNNING / STOPPING。
- **等待态（WAITING_APPROVAL / WAITING_EXTERNAL）不受心跳收割**，但必须：**持续可见**（工作台「进行中 TestRun」与列表，含滞留时长）、**可告警**（阈值 **TBD**）、**可人工取消**。以「可见 + 可告警 + 可取消」替代自动回收。「无永久 running」口径 = 活跃态无永久滞留。
- 审批过期：TestRun **停留 WAITING_APPROVAL**，不自动放行；仅拒绝 / 人工取消 → CANCELLED。
- WAITING_EXTERNAL 排队超时仅告警，不自动迁移、不自动取消外部 Job。
- STOPPING 为活跃态：停止流程卡死可走 STOPPING → TIMEOUT，不得永久停留 STOPPING。
- VALIDATING 无独立取消边；发起后立即取消落 PENDING → CANCELLED。

`execution_source`：**script / agent / external_ci**。仅 script / external_ci 可进门禁；**agent 永不产生 GateEvaluation**（`gate_evaluation_id` 恒空）。

`trigger_type` 仅：manual / schedule / ci_webhook / api_token。

### 5.1.3 ApprovalRequest（§2.3）

六态：**CREATED、PENDING、APPROVED、EXECUTED、REJECTED、EXPIRED**。

- CREATED = Policy Gate 判 REQUIRE_APPROVAL 时创建（瞬时态）；PENDING = 入队、通知审批人、TTL 启动。
- APPROVED → EXECUTED 之间是执行前哈希复核 + 行锁 consume（系统内部）。
- **`execution_result`（ok / failed / unknown）仅当状态为 EXECUTED 时有值。**
  - `ok`：已确认成功，才可推进目标聚合；
  - `failed`：已确认失败，再次动作必须新审批；
  - `unknown`：外部效果不可判定 → **对账 / 人工接管**；禁止当失败盲重试，禁止当成功放行。
- 撤回 / 上游取消 / APPROVED 后参数变更 → EXPIRED + reason（withdrawn / invalidated），不新增状态。
- 「修改后重新提交」生成新请求，不在原单上改 hash 继续批。

### 5.1.4 ExecutionEnvironment（§2.4）

**PENDING_APPROVAL、ACTIVE、DEGRADED、DISABLED。**

- 管理员审批：PENDING_APPROVAL → ACTIVE。
- ACTIVE → DEGRADED（健康检查失败）→ DISABLED。
- **DEGRADED / DISABLED 只阻断新发起**（选择器不可选）；**在途 run 不中断**（RUNNING 失败按 FAILED 落账；WAITING_EXTERNAL 继续幂等采集）。

### 5.1.5 ReleaseTask（§2.6）

**DRAFT、PENDING_CONFIRM、SUBMITTED、READY、FAILED_RETRYABLE、CANCELLED。**

- DRAFT（版本圈定 + 范围快照）→ PENDING_CONFIRM（Readiness + notes 草稿就绪）→ SUBMITTED（人工确认后调用 Release 系统）→ READY（item 创建成功、状态回传）或 FAILED_RETRYABLE（调用失败可重试）。
- FAILED_RETRYABLE → SUBMITTED（人工幂等重试）或 → CANCELLED（放弃）。
- PENDING_CONFIRM → CANCELLED。
- 平台只「准备」release item，不执行生产发布。

### 5.1.6 GateEvaluation.result

**仅 pass / fail / waived。** 对象不可变；重评估生成新记录。豁免不改写原评估。

**未评估 ≠ 第四种 result：** 当前兼容 = **无 GateEvaluation 行** + 查询投影 **`unevaluated_reason`**（API-146）。CANCELLED / TIMEOUT / 阈值缺配 / 报告 partial 不创建评估，**绝不默认通过**。agent 型 run 不生成本对象。

**Proposed（未批准，ADR 0003）：** 将 `not_evaluated` 扩进 `GateEvaluation.result` 枚举。获批前 **不得** 写入该枚举值，不得当作现行状态。

### 5.1.7 其它与执行相关的枚举（不升格为新状态机）

- FailureCluster：无生命周期；`category` 仅 7 值（env_down / auth_expired / locator_stale / assertion_real_bug / flaky / data_issue / unknown）；人工修正留痕，不新增状态。
- AIInvocationLog.result：ok / degraded / refused（唯一出口；对外不回传 Prompt 原文）。

---

## 5.2 角色与权限

项目内角色 **仅四值：owner / admin / tester / viewer。** 不发明第五角色。

- viewer：全局只读，不能发起执行、不能发起 L2+、不能审批。
- tester 及以上：可发起执行与 L2+ Preview（仍受 RBAC、租户、配额、Policy Gate）。
- env_register 激活：管理员审批。
- 四眼：审批人 ≠ 发起人；服务端强制。REQUIRE_REAUTH（L3+ 且会话超过再认证窗口，或目标资源要求强认证）走 API-004；窗口数值 **TBD**。

**前端置灰 / 隐藏入口不是安全边界。** 权限与租户过滤每请求由后端判定（边界 §6-14：「置灰 / 无权限态」非权威；权威为「后端每请求判定」）。隐藏入口 ≠ 已授权。

配额 / 预算：余量展示非权威；权威为 OrgQuota 后端计算与扣减（边界 §6-15）。

---

## 5.3 错误三类与跨租户呈现

错误分三类（边界 §7），判定与呈现如下。

| 类别 | 定义 | 对状态 | 用户可见 |
| --- | --- | --- | --- |
| **网络** | 未送达 / 超时 / 连接中断 / 5xx / SSE 断连——传输层故障，**业务语义未知** | 无业务状态变化 | 网络异常 + 可重试；**结果未决时以服务端查询为准，不得假定成功或失败**。SSE 断连不得标 FAILED / TIMEOUT / EXPIRED。 |
| **权限** | 401 会话失效 / REQUIRE_REAUTH；403 角色不足；跨租户引用统一 404 | 无领域迁移 | 401 引导重登 / 再认证；403 无权限态；跨租户 / 不可感知 **一律「资源不存在」**，不泄露存在性 |
| **业务** | 校验失败、前置状态不满足、配额超限、Policy Gate DENY、审批失效（param_hash）、外部调用失败 | 按状态机落账（如 VALIDATING→FAILED、ReleaseTask→FAILED_RETRYABLE） | 具体原因；不吞错、不静默；FAILED_RETRYABLE 才出现重试入口 |

**跨租户：** 用户看到 **「资源不存在」**（PRD v1.6 §2.3：返回 404 而非 403、不泄露存在性；边界 §7：404 呈现「资源不存在」）。业务建模只规定无组织上下文 = **拒绝而非放行**（ORM `tenant_id` 过滤），不规定对用户的文案；产品文案以 PRD + 边界为准。

失败不静默（failed_items、部分入库标记）；失败也审计；降级必须横幅，不静默。

---

## 5.4 Kill switch 与敏感信息

- **关停（收紧）= L1，即时生效，不走审批。** 产品 API：API-199。事故响应不得被审批阻塞。
- **恢复（放开）= L3，`kill_switch_restore`，经 Preview（API-120）与审批链。** 禁止用 tighten 接口放开。
- 两向均写 AuditEvent。开关层级：单能力 A1–A8 → 模块 → 连接器写入 → 全局 AI（P23）。
- 压测 kill switch 演练既有验收：**60s 内**停止全部施压进程（FR-11）。该 60s 为已有验收数字，不是新造 TTL。

**对外呈现禁止：** Restricted 明文、ApiToken / 会话 token 明文、Prompt 原文、凭证值、Webhook secret。环境只展示 `credential_present` 一类布尔；AI 日志（API-184 / API-185）无 Prompt；错误 / SSE / 审计投影同样禁止上述明文。

---

## 5.5 超时、TTL 与心跳数值

除下列 **已有** 数字外，审批 TTL、升级提前量、心跳周期、僵尸回收阈值、外部排队告警阈值、Agent 单步 / 总超时、再认证窗口等一律标 **TBD**（Q 类 / Stage 8 配置项表），本章不发明默认秒数或小时数。

| 项 | 数值 | 性质 |
| --- | --- | --- |
| 压测 kill switch 停止全部施压进程 | **60s** | 已有验收（FR-11），非新指标 |
| A2 分诊报告 | run 完成后 **≤5 分钟**（10k 用例级） | 已有 SLO（PRD §6.2），非新指标、非硬超时 |
| 其余 TTL / 心跳 / 排队告警 / 幂等时效 / SSE 心跳间隔 | **TBD** | 不得在 PRD 中填写未批数字 |

---

---

## 6. 数据与接口关联

本章把 FR-01…FR-19 接到 23 个领域对象（只读引用建模层）与 `api_spec.md` §6 已编号端点。列口径：

| 列 | 含义 |
| --- | --- |
| 领域对象 | 仅 05 §1.1 的 23 个；操作语义见 05 §3 CRUD 矩阵，此处不展开字段 |
| 查询 API | GET（及等价只读） |
| 命令 API | 浏览器会话下的写 / 状态迁移 / Preview / AI 受理；**不含** HMAC 入站 |
| SSE | `api_spec` §6.18 |
| 系统内部 / 无产品 API | 无浏览器会话命令：日志写入、Execute consume、Temporal / Outbox / Worker、Policy Gate 裁决、Check Run 回写、HMAC 入站 `API-090` 等 |

**API-090**：HMAC 入站观察入口，先验签再 Inbox；不是浏览器会话命令，一律记入「系统内部 / 无产品 API」。  
**API-222**：Proposed M2+ 短期授权，**不作为 M0 必过端点**，不列入下表查询列。  
**横切（不构成新 FR）**：`API-020` 工作台聚合；`API-024` / `API-025` 审计检索；`API-026`–`API-028` 证据检索与导出。另：`API-021`–`API-023` / `API-029` / `API-040` 通知与 SIEM 配置；`API-050`–`API-055` TestPlan；`API-170`–`API-172` ApiToken 管理；`API-196`–`API-198` ModelRoute——均无独立 FR 编号，验收挂到既有 FR（见第 7 章）。  
**M4 超出本期产品面必过**：`API-194` / `API-195`（技能三级发布）对 FR-16 M3 最小版为 Out of Scope。

### 6.1 FR → 对象 → API

| FR | 领域对象（只读引用建模） | 查询 API | 命令 API | SSE | 系统内部 / 无产品 API |
| --- | --- | --- | --- | --- | --- |
| FR-01 多租户与身份 | Organization、User/ProjectMember、Project | API-005、API-006、API-010–013 | API-001–004、API-014–016 | — | 无组织上下文拒绝（非放行）；租户过滤在 ORM/中间件 |
| FR-02 AI 日志计量 | AIInvocationLog | API-184、API-185 | — | — | 全量写入（LLM 工厂唯一出口）；无产品面「写日志」API |
| FR-03 预算与看板 | OrgQuota | API-017、API-018、API-183 | API-199（关停/收紧相关） | — | 超限拒绝经对应 AI 命令失败返回，无独立 reject API；配额扣减内部 |
| FR-04 审批中心 | ApprovalRequest、AuditEvent | API-110、API-111、API-121 | API-112、API-113、API-120 | — | Execute consume / execution intent；参数哈希复核与行锁 |
| FR-05 用例生成两步式 | TestCase(+Version)、AIInvocationLog | API-030、API-031、API-181、API-182、API-204 | API-205、API-180、API-032–035 | API-211 | 生成默认不落库；AIInvocationLog 写入内部 |
| FR-06 失败自愈 | FailureCluster、TestCase Version、ApprovalRequest、EvidenceObject | API-130、API-131 | API-120、API-112、API-039 | — | heal_apply 执行与应用前快照（失败 fail-close） |
| FR-07 失败聚类报告 | FailureCluster、EvidenceObject、CaseResult | API-130、API-131、API-133 | API-132 | API-210（聚类进度） | A2 聚类生成、归一化管道、evidence_refs 校验 |
| FR-08 执行收敛 | TestRun、CaseResult/StepRun/Artifact | API-060、API-061、API-064–066、API-071 | API-062、API-063、API-080 | API-210 | Temporal / Outbox / Worker、心跳与僵尸回收、状态机迁移 |
| FR-09 Playwright 执行器 | Artifact、ExecutionEnvironment | API-066、API-220、API-221 | 无额外命令（制品由 run 产出） | —（进度走 FR-08 的 API-210） | 容器执行与三件套上传对象存储 |
| FR-10 定位器自愈 | TestCase Version、ApprovalRequest | API-031、API-037、API-038 | API-120、API-112、API-039 | — | 建议生成（A3）；无自动改写路径 |
| FR-11 压测编排 | TestRun、PerfBaseline、ApprovalRequest、OrgQuota | API-056、API-059 | API-057、API-058、API-062、API-120 | — | 白名单外 DENY（不进审批）；场景互斥；kill 关停走 API-199 |
| FR-12 性能门禁 | QualityGatePolicy、GateEvaluation、PerfBaseline | API-140、API-141、API-144–146、API-056 | API-142、API-143 | — | 评估管线（与 FR-13 同一模型）；缺配不创建 GateEvaluation |
| FR-13 Check Run 门禁 | QualityGatePolicy、GateEvaluation、Connector、ApprovalRequest | API-144–146 | API-167、API-120、API-112 | — | Check Run 三段式回写；HMAC 入站 **API-090**（非会话命令） |
| FR-14 Jira 缺陷 | Connector、ApprovalRequest、EvidenceObject | —（读走横切 API-026 / API-160） | API-120、API-112 | — | 连接器 jira_write 执行（审批通过后） |
| FR-15 Release | ReleaseTask、EvidenceObject | API-150、API-151、API-155 | API-152–154、API-120 | — | `release_push` 执行（域仅准备）；Release webhook 观察走 API-090 |
| FR-16 Copilot | CopilotSession、Skill、AIInvocationLog | API-190、API-193 | API-191、API-192 | — | AIInvocationLog 写入内部；**API-194 / API-195 M4 Out of Scope** |
| FR-17 Policy Gate | AuditEvent（无独立门禁表） | —（审计读走横切 API-024） | API-120、API-004 | — | 四值裁决（ALLOW / DENY / REQUIRE_APPROVAL / REQUIRE_REAUTH）系统内部；产品面 Preview + 再认证 |
| FR-18 执行环境 / 引用型 | ExecutionEnvironment、TestCase（referenced）、TestRun | API-100、API-101、API-104、API-105、API-070 | API-102、API-103、API-106、API-062、API-080 | API-210（解析进度，同 FR-08 通道） | 外部 Job 幂等触发 / 轮询；HMAC 入站 **API-090** |
| FR-19 双执行模式 | TestRun（agent）、TestCase、Skill | API-067 | API-062、API-063、API-068 | — | Agent Worker；工具经 Policy Gate；不产生 GateEvaluation |

### 6.2 列使用说明

1. **查询 / 命令 / SSE 已拆分**；同一 ID 不在两列重复，除非语义确为不同入口（无此情况）。  
2. **FR-02** 写 AIInvocationLog、**FR-04** Execute consume、**FR-08** Temporal/Outbox/Worker、**FR-17** Policy Gate 裁决：均无产品面写 API。  
3. **API-080** 与 **API-062** 同路径、不同鉴权（Tok `execute` vs Sess），同属命令列。  
4. M0/M1 制品内容访问为 **API-221 代理下载**；**API-222 不出现在上表**。

---

## 7. 验收标准

编号 **AC-001** 起全局唯一、按 FR 分组、连续无断号。每条可二元判定（Pass / Fail）。LDAP 登录**不是** M0 必过项；M0 身份必过为 OIDC（API-001 / API-002 / API-005）。时间与比例只采用既有数字或 TBD。v1.6 §2.3 边界场景全部挂到既有 FR，不新开 FR。

判定写法：Given / When / Then，或「若…则…」。权威成功条件以后端结果为准（边界规范 §6）：回执 ≠ 终态；SSE 进度 ≠ 终态。

### FR-01 多租户与身份

**AC-001**
- **ID**：AC-001
- **FR**：FR-01
- **API 挂钩**：API-001、API-002
- **判定**：Given 企业 IdP 可用且账号已开通，When 走 OIDC Authorization Code + PKCE（API-001 启动、API-002 回调），Then 服务端签发会话，随后 API-005 可返回当前用户与租户。
- **里程碑**：M0

**AC-002**
- **ID**：AC-002
- **FR**：FR-01
- **API 挂钩**：API-005
- **判定**：Given 无有效服务端会话，When 调用 API-005 或任一 Sess 端点，Then 请求被拒绝，不能得到租户/角色上下文。无 SSO 账号无法完成 AC-001，因而无法登录。
- **里程碑**：M0

**AC-003**
- **ID**：AC-003
- **FR**：FR-01
- **API 挂钩**：无单一端点（所有带资源 ID 的 GET/命令）
- **判定**：Given 租户 A 的有效会话与租户 B 的用例/报告/`evidence_id`，When A 引用 B 的资源 ID，Then 一律 **404**（不得 403），不泄露资源存在性。双租户越权回归集须 100% 阻断。
- **里程碑**：M0

**AC-004**
- **ID**：AC-004
- **FR**：FR-01
- **API 挂钩**：API-062（代表会话命令；同类写接口同判）
- **判定**：Given 角色为 viewer 的有效会话，When 调用发起执行、审批决策或其他写/状态迁移命令，Then **后端拒绝**（前端置灰不构成 Pass）。Pass 条件是服务端拒绝，而非仅 UI 隐藏入口。
- **里程碑**：M0

**AC-005**
- **ID**：AC-005
- **FR**：FR-01
- **API 挂钩**：系统内部
- **判定**：Given 请求无法解析出组织（`tenant_id`）上下文，When 访问核心领域接口，Then 拒绝该请求，不得放行。
- **里程碑**：M0

**AC-006**
- **ID**：AC-006
- **FR**：FR-01
- **API 挂钩**：API-171、API-170
- **判定**：Given 管理员签发 ApiToken，When 调用 API-171，Then 响应体中的 `token` 明文**仅此一次**出现；此后 API-170 列表与再 GET 只含前缀 / scopes / `project_ids` / 过期与吊销投影，无明文、无 `token_hash`。
- **里程碑**：M0

> LDAP 登录可在后续里程碑评估，**不作为 M0 必过 AC**。

### FR-02 AI 调用日志与 Token 计量

**AC-007**
- **ID**：AC-007
- **FR**：FR-02
- **API 挂钩**：系统内部
- **判定**：Given 任意 A1–A8 调用路径，When 代码审查与运行抽检，Then 不存在绕过 AIInvocationLog 的调用路径；每条调用有真实 usage、模型、prompt 版本、成本、延迟、数据分级。
- **里程碑**：M0

**AC-008**
- **ID**：AC-008
- **FR**：FR-02
- **API 挂钩**：API-184、API-185
- **判定**：Given 已产生 AIInvocationLog，When 调用 API-184 列表或 API-185 详情，Then 响应**不含 Prompt 原文**（错误体、SSE、审计检索同样不得出现 Prompt 原文）。
- **里程碑**：M0

**AC-009**
- **ID**：AC-009
- **FR**：FR-02
- **API 挂钩**：API-183
- **判定**：Given 部门内已有计量日志，When 按部门与账期查询 API-183，Then 可汇总出该部门账单所需用量与成本（采纳率等质量聚合同源此出口）。
- **里程碑**：M0

**AC-010**
- **ID**：AC-010
- **FR**：FR-02
- **API 挂钩**：系统内部
- **判定**：Given 输入被标为 Restricted 或日志/报告含密钥与 PII，When 进入 AI 调用或落库，Then 路由层保证 Prompt 不含 Restricted 级内容；日志与报告经脱敏管道（正则 + 字典）后再落库。拦截可查且记日志。
- **里程碑**：M0

### FR-03 预算与看板

**AC-011**
- **ID**：AC-011
- **FR**：FR-03
- **API 挂钩**：API-180（代表 AI 命令；同类 API-192 同判）
- **判定**：Given 部门 Token 预算已耗尽，When 发起新的 AI 调用，Then 该命令失败（被拒），并通知 Owner；不得静默成功。
- **里程碑**：M0

**AC-012**
- **ID**：AC-012
- **FR**：FR-03
- **API 挂钩**：API-017、API-018
- **判定**：Given 已配置 OrgQuota，When 调用 API-017 / API-018，Then 返回组织余量与项目级配额视图，且以后端计算为准（前端不得本地扣减冒充成功）。
- **里程碑**：M0

**AC-013**
- **ID**：AC-013
- **FR**：FR-03
- **API 挂钩**：API-199
- **判定**：Given 管理员执行能力关停（收紧），When 调用 API-199，Then 关停 L1 即时生效、不走审批；不得用该接口做恢复（放开）。恢复须走 API-120（`kill_switch_restore`），见 FR-17/FR-04。
- **里程碑**：M0

### FR-04 审批中心

**AC-014**
- **ID**：AC-014
- **FR**：FR-04
- **API 挂钩**：API-110、API-111
- **判定**：Given 已创建 PENDING 的 ApprovalRequest，When GET 队列或详情，Then `card_payload` 含九要素：动作、资源、diff、数据来源、模型与 Skill 版本、风险等级、成本估计、回滚能力、参数哈希。缺任一要素为 Fail。
- **里程碑**：M0

**AC-015**
- **ID**：AC-015
- **FR**：FR-04
- **API 挂钩**：API-112、系统内部
- **判定**：Given 审批人（非发起人）对哈希一致的请求批准，When 系统内部 consume 且外部结果已确认，Then ApprovalRequest 进入 EXECUTED 且 `execution_result=ok`。仅 API-112 返回「已批准」不算执行成功（两段分判）。
- **里程碑**：M0

**AC-016**
- **ID**：AC-016
- **FR**：FR-04
- **API 挂钩**：API-112、API-120
- **判定**：Given 已 APPROVED 的请求，When 目标参数变化导致 `param_hash` 与 Preview/Execute 不一致，Then 原审批失效（EXPIRED + reason `invalidated`），执行被拦截，必须重新 Preview 与审批；不得继续执行。
- **里程碑**：M0

**AC-017**
- **ID**：AC-017
- **FR**：FR-04
- **API 挂钩**：系统内部
- **判定**：Given EXECUTED 且 `execution_result=unknown`（外部效果不可判定），When 系统或调用方处理该结果，Then **不得**当作失败盲目重试，也**不得**当作成功放行或推进目标聚合；必须进入对账或人工接管。再次动作须新审批。
- **里程碑**：M0

**AC-018**
- **ID**：AC-018
- **FR**：FR-04
- **API 挂钩**：API-112
- **判定**：Given 发起人与审批人为同一用户，When 发起人调用批准，Then 后端拒绝（四眼），并留痕；前端置灰不构成 Pass。
- **里程碑**：M0

**AC-019**
- **ID**：AC-019
- **FR**：FR-04
- **API 挂钩**：API-112
- **判定**：Given PENDING 审批，When 审批人拒绝，Then 状态为 REJECTED，不执行副作用；若关联 TestRun 处于 WAITING_APPROVAL，则走人工取消边至 CANCELLED（拒绝/人工取消，非过期）。
- **里程碑**：M0

**AC-020**
- **ID**：AC-020
- **FR**：FR-04
- **API 挂钩**：无 API（TTL 系统内部）；查询 API-110、API-061、API-020
- **判定**：Given 审批人未处理且超过 `expires_at`，When TTL 到期，Then 先升级通知备审批人；仍未处理则审批 EXPIRED，关联 TestRun **停留 WAITING_APPROVAL**，**不自动放行**。工作台与 TestRun 列表仍可见该等待态。
- **里程碑**：M0

**AC-021**
- **ID**：AC-021
- **FR**：FR-04
- **API 挂钩**：API-113
- **判定**：Given 需要对已失效或需改参的请求再提交，When 调用 API-113，Then 创建**新** ApprovalRequest（新 `param_hash`，`initiator_id` = 重新提交人，保留 origin 归因链）；四眼按新发起人校验。
- **里程碑**：M0

### FR-05 用例生成（两步式）

**AC-022**
- **ID**：AC-022
- **FR**：FR-05
- **API 挂钩**：API-180、API-030
- **判定**：Given 已登记导入源（API-205），When 仅调用 API-180 完成生成，Then **不创建** TestCase；API-030 不得因本次生成新增用例。TestCase 仅在 API-032 保存后出现。
- **里程碑**：M1

**AC-023**
- **ID**：AC-023
- **FR**：FR-05
- **API 挂钩**：API-180、API-032
- **判定**：Given 接口契约审查，When 检查生成/保存路径，Then **不存在** `save=true`（或等价开关）把生成结果直写持久化的路径。生成与保存必须是两个命令。
- **里程碑**：M1

**AC-024**
- **ID**：AC-024
- **FR**：FR-05
- **API 挂钩**：API-182
- **判定**：Given 批次中部分端点生成或 schema 失败，When GET API-182，Then `failed_items` 显式列出（endpoint + reason），整批标记 partial；禁止静默丢弃失败条目或返回空列表冒充成功。
- **里程碑**：M1

**AC-025**
- **ID**：AC-025
- **FR**：FR-05
- **API 挂钩**：API-180、API-181
- **判定**：Given 模型或 schema 导致生成失败，When 查询任务状态，Then 有显式失败/告警，禁止静默返回空草稿当作成功。
- **里程碑**：M1

**AC-026**
- **ID**：AC-026
- **FR**：FR-05
- **API 挂钩**：API-032、API-034、API-035
- **判定**：Given 审阅后的草稿，When API-032 保存，Then 创建 TestCase（DRAFT）+ Version 并打 `ai-generated`。When 再经 API-034 / API-035，Then 须走 PENDING_REVIEW 后由人工确认才 ACTIVE；禁止生成直写 ACTIVE。
- **里程碑**：M1

**AC-027**
- **ID**：AC-027
- **FR**：FR-05
- **API 挂钩**：API-182
- **判定**：Given 生成批次中单条输出未通过 schema 校验，When 返回草稿，Then 整批为 partial，该条进入失败列表可见（与 AC-024 同纪律，覆盖 §2.3「生成批次单条失败」）。
- **里程碑**：M1

### FR-06 失败归因建议

**AC-028**
- **ID**：AC-028
- **FR**：FR-06
- **API 挂钩**：API-130、API-120、API-112
- **判定**：Given 修复建议 `confidence < 0.7`，When 渲染与命令，Then 不展示「可应用」入口；即便调用应用，亦不得绕过 heal_apply 审批。`confidence ≥ 0.7` 仅放开呈现，实际落地必须 API-120 Preview + API-112 审批。
- **里程碑**：M1

**AC-029**
- **ID**：AC-029
- **FR**：FR-06
- **API 挂钩**：系统内部
- **判定**：Given 审批通过后准备应用自愈，When 应用前快照失败，Then **fail-close 中止**，不改写 TestCase 生效版本。
- **里程碑**：M1

**AC-030**
- **ID**：AC-030
- **FR**：FR-06
- **API 挂钩**：API-039
- **判定**：Given 自愈已写出新 Version，When 调用 API-039 回滚指针，Then `current_version_id` 恢复快照版本，且该用例此后可被执行发起受理（非 DEPRECATED / invalid）。
- **里程碑**：M1

**AC-031**
- **ID**：AC-031
- **FR**：FR-06
- **API 挂钩**：API-130
- **判定**：Given 聚类/归因输出，When 检查 `category`，Then 取值 ⊆ {env_down, auth_expired, locator_stale, assertion_real_bug, flaky, data_issue, unknown}，不确定须用 unknown，不得编造根因。
- **里程碑**：M1

### FR-07 run 级失败聚类报告

**AC-032**
- **ID**：AC-032
- **FR**：FR-07
- **API 挂钩**：API-130、API-131
- **判定**：Given 含失败 CaseResult 的终态 run 且报告已生成，When GET 聚类，Then 每簇含类别、confidence、阻塞判断、证据链接；`unclustered_refs` 显式；人工修正进入 `correction_history`。缺证据链接的关键结论计入无据（见 AC-034）。
- **里程碑**：M1

**AC-033**
- **ID**：AC-033
- **FR**：FR-07
- **API 挂钩**：系统内部（归一化管道）
- **判定**：Given 标注集，When 跑确定性解析器（非模型），Then 字段级命中比例 ≥98%。
- **里程碑**：M1

**AC-034**
- **ID**：AC-034
- **FR**：FR-07
- **API 挂钩**：API-130
- **判定**：Given 线上或评测窗口内的关键结论集合，When 统计无有效 `evidence_ref` 的比例，Then 无据结论率 **<2%**。
- **里程碑**：M1

**AC-035**
- **ID**：AC-035
- **FR**：FR-07
- **API 挂钩**：API-210、API-064
- **判定**：Given 超大测试报告（>10 万用例结果），When 分片流式解析，Then 进度经 API-210 可见；若解析超时，则**已完成部分入库**且带**显式失败标记**，禁止静默截断后当作完整成功。
- **里程碑**：M1

**AC-036**
- **ID**：AC-036
- **FR**：FR-07
- **API 挂钩**：API-210、API-130
- **判定**：Given 正在生成聚类，When 客户端只收到 SSE 进度帧，Then 不得将进度当作报告终态；报告可读以 API-130 有数据（或明确失败/降级）为准。
- **里程碑**：M1

### FR-08 执行引擎

**AC-037**
- **ID**：AC-037
- **FR**：FR-08
- **API 挂钩**：API-062、API-061
- **判定**：Given 用例 ACTIVE、环境 ACTIVE、配额允许，When 会话调用 API-062，Then 返回 TestRun 且初始受理为 PENDING（含 snapshot 冻结）；权威存在以 API-061 为准。
- **里程碑**：M1

**AC-038**
- **ID**：AC-038
- **FR**：FR-08
- **API 挂钩**：API-071、API-061
- **判定**：Given 刚发起的执行命令，When 仅 GET API-071 回执为已受理，Then **不等于** TestRun 终态。终态集合仅 {SUCCEEDED, FAILED, CANCELLED, TIMEOUT}，须以 API-061 为准。
- **里程碑**：M1

**AC-039**
- **ID**：AC-039
- **FR**：FR-08
- **API 挂钩**：系统内部
- **判定**：Given TestRun 处于活跃态（RUNNING / STOPPING 等受心跳治理的状态），When 心跳超时，Then 不得永久停留；须转入 TIMEOUT（STOPPING 卡死走 STOPPING→TIMEOUT）。口径是**活跃态**无永久滞留，等待态见 AC-043。
- **里程碑**：M1

**AC-040**
- **ID**：AC-040
- **FR**：FR-08
- **API 挂钩**：API-063、API-061
- **判定**：Given 运行中的 TestRun，When 调用 API-063，Then 立即持久化终止/取消信号并返回受理；**受理成功 ≠ 状态已是 CANCELLED**。须待状态机经 STOPPING（若适用）落到 CANCELLED 后，API-061 才算取消完成。
- **里程碑**：M1

**AC-041**
- **ID**：AC-041
- **FR**：FR-08
- **API 挂钩**：API-062、API-061
- **判定**：Given 双层变量 `{{env}}` / `${func}` 无法解析，When 进入 VALIDATING，Then 必报错并拒绝进入执行队列（VALIDATING→FAILED），不得带着未解析变量 RUNNING。
- **里程碑**：M1

**AC-042**
- **ID**：AC-042
- **FR**：FR-08
- **API 挂钩**：系统内部
- **判定**：Given 进程重启或 Outbox/Activity 重放，When 恢复工作流，Then 无永久 RUNNING 僵尸；同一业务副作用不因重放而重复执行（混沌/重放测试覆盖）。
- **里程碑**：M1

**AC-043**
- **ID**：AC-043
- **FR**：FR-08
- **API 挂钩**：API-020、API-060、API-063
- **判定**：Given TestRun 为 WAITING_APPROVAL 或 WAITING_EXTERNAL，When 滞留超过配置阈值（阈值 TBD，归配置项），Then：① 工作台「进行中 TestRun」与列表持续可见并显示滞留时长（不得因久等隐藏）；② 超阈值告警；③ 人工可 API-063 取消（WAITING_APPROVAL→CANCELLED / WAITING_EXTERNAL→CANCELLED）。等待态**不适用**心跳僵尸回收，且不自动迁移。
- **里程碑**：M1

**AC-044**
- **ID**：AC-044
- **FR**：FR-08
- **API 挂钩**：API-210、API-061
- **判定**：Given 执行中的 SSE 订阅，When 收到进度事件，Then 前端/测试不得由进度推定 SUCCEEDED/FAILED 等终态；终态只认 API-061（或等价资源 GET）。
- **里程碑**：M1

### FR-09 Playwright 执行器

**AC-045**
- **ID**：AC-045
- **FR**：FR-09
- **API 挂钩**：API-220、API-221、API-066
- **判定**：Given Web 用例某步骤失败且 `execution_source=script`，When 查询该步骤制品，Then 100% 存在可回放 Trace（经 API-220 元数据 + API-221 代理内容，M0/M1）。
- **里程碑**：M2

**AC-046**
- **ID**：AC-046
- **FR**：FR-09
- **API 挂钩**：API-221
- **判定**：Given M0/M1 环境，When 访问非 Restricted 制品内容，Then 走 API-221 代理下载；`object_key` 不得当作授权令牌。
- **里程碑**：M2

**AC-047**
- **ID**：AC-047
- **FR**：FR-09
- **API 挂钩**：API-222
- **判定**：Given M0/M1，When 调用 API-222，Then **不要求成功**（Proposed M2+；未启用须按契约拒绝）。本条用于防止把 API-222 误列为 M0 必过。
- **里程碑**：M0（负向：不得作为放行条件）

### FR-10 定位器自愈建议

**AC-048**
- **ID**：AC-048
- **FR**：FR-10
- **API 挂钩**：无 API
- **判定**：Given 定位器失效，When 审查写路径，Then **不存在**不经审批的自动改写 ACTIVE 定位器路径；A3 只产出建议。
- **里程碑**：M2

**AC-049**
- **ID**：AC-049
- **FR**：FR-10
- **API 挂钩**：API-120、API-112、API-039
- **判定**：Given 建议落地，When 走 diff → Preview → 审批 → 快照 → 写新 Version，Then 与 FR-06 同一审批与回滚端点；快照失败则中止（同 AC-029）。
- **里程碑**：M2

**AC-050**
- **ID**：AC-050
- **FR**：FR-10
- **API 挂钩**：API-039、API-062
- **判定**：Given 已回滚定位器版本，When 再次发起执行，Then 用例可被受理执行（回滚后可执行）。
- **里程碑**：M2

### FR-11 压测编排

**AC-051**
- **ID**：AC-051
- **FR**：FR-11
- **API 挂钩**：API-062、API-120
- **判定**：Given 目标环境不在白名单，When 发起压测，Then 100% DENY，**不创建** perf_high_risk 审批。
- **里程碑**：M3

**AC-052**
- **ID**：AC-052
- **FR**：FR-11
- **API 挂钩**：API-199
- **判定**：Given 压测正在施压，When 触发压测 kill switch 演练，Then **60s 内**停止全部施压进程。
- **里程碑**：M3

**AC-053**
- **ID**：AC-053
- **FR**：FR-11
- **API 挂钩**：系统内部
- **判定**：Given 压测 TestRun 失败或中断，When 观察重试策略，Then **无自动重试**（禁止引擎侧自行再拉起施压）。
- **里程碑**：M3

**AC-054**
- **ID**：AC-054
- **FR**：FR-11
- **API 挂钩**：API-062
- **判定**：Given 同一压测场景已有在途执行，When 第二次触发，Then 进入排队并提示，**不并行施压**。
- **里程碑**：M3

### FR-12 性能门禁接入

**AC-055**
- **ID**：AC-055
- **FR**：FR-12
- **API 挂钩**：API-140、API-144
- **判定**：Given 性能阈值 max_p95_ms / max_error_rate，When 对照接口/Web 门禁，Then 走**同一** QualityGatePolicy 与**同一** GateEvaluation 管线；代码审查确认无独立门禁分支。
- **里程碑**：M3

**AC-056**
- **ID**：AC-056
- **FR**：FR-12
- **API 挂钩**：API-144、API-145、API-155
- **判定**：Given 已评估的压测 run，When 在门禁评估历史与 Release 证据汇聚中检索，Then 能查到该次 GateEvaluation（或明确的未评估 reason，见 AC-057）。
- **里程碑**：M3

**AC-057**
- **ID**：AC-057
- **FR**：FR-12
- **API 挂钩**：API-146
- **判定**：Given 阈值缺配（策略不可评估），When GET API-146，Then **不创建** GateEvaluation，投影含明确 reason（如 `unevaluated_reason`）；**不得默认通过**；**不得**使用 `not_evaluated` 作为 GateEvaluation.result 枚举（结果枚举仅 pass / fail / waived）。
- **里程碑**：M3

### FR-13 GitHub Check Run 门禁

**AC-058**
- **ID**：AC-058
- **FR**：FR-13
- **API 挂钩**：系统内部（Check Run 回写）；查询 API-146
- **判定**：Given `execution_source∈{script,external_ci}`、可评估且结论为 fail，When 回写 GitHub Check Run，Then CI 侧呈现失败（变红）。E2E 覆盖。agent 型 run 不适用本条（见 AC-086）。
- **里程碑**：M2

**AC-059**
- **ID**：AC-059
- **FR**：FR-13
- **API 挂钩**：系统内部
- **判定**：Given Check Run 同步失败，When 观察治理，Then 有重试与告警，不得静默丢回写。
- **里程碑**：M2

**AC-060**
- **ID**：AC-060
- **FR**：FR-13
- **API 挂钩**：API-120、API-112
- **判定**：Given 门禁 fail，When 未经 gate_waiver 审批（或审批未 EXECUTED+ok）尝试豁免，Then 豁免不生效；原 GateEvaluation 不可变。
- **里程碑**：M2

**AC-061**
- **ID**：AC-061
- **FR**：FR-13
- **API 挂钩**：API-146
- **判定**：Given TestRun 为 CANCELLED / TIMEOUT、报告 partial、或策略缺配，When 查询门禁，Then **无** GateEvaluation 行 + 明确 reason，**绝不默认通过**（与 AC-057 同一纪律；不用 `not_evaluated` 枚举）。
- **里程碑**：M2

**AC-062**
- **ID**：AC-062
- **FR**：FR-13
- **API 挂钩**：API-143
- **判定**：Given 策略当前为 report_only，When 切到 blocking，Then 必须经显式开启的更新命令；禁止隐式升为阻断。历史 GateEvaluation 不被策略修改改写。
- **里程碑**：M2

### FR-14 Jira 缺陷创建

**AC-063**
- **ID**：AC-063
- **FR**：FR-14
- **API 挂钩**：API-120、API-112
- **判定**：Given 无有效 jira_write 审批（EXECUTED + `execution_result=ok`），When 尝试向 Jira 创建缺陷，Then 不得写入。渗透/负向测试覆盖。
- **里程碑**：M2

**AC-064**
- **ID**：AC-064
- **FR**：FR-14
- **API 挂钩**：API-120、API-112
- **判定**：Given 审批通过且连接器执行成功，When 查看创建的缺陷，Then 含证据附件与复现步骤，并有链接回写。
- **里程碑**：M2

### FR-15 Release 模块

**AC-065**
- **ID**：AC-065
- **FR**：FR-15
- **API 挂钩**：API-024、API-152、API-120
- **判定**：Given 一次 ReleaseTask 从圈定到确认推送，When 按 AuditEvent 检索，Then 关键动作（创建、确认、审批、调用准备）可审计追溯。
- **里程碑**：M3

**AC-066**
- **ID**：AC-066
- **FR**：FR-15
- **API 挂钩**：API-151
- **判定**：Given A5 草稿已生成，When 未完成 release_push 审批与确认，Then **禁止自动推送**到 Release 系统；草稿只读可查。
- **里程碑**：M3

**AC-067**
- **ID**：AC-067
- **FR**：FR-15
- **API 挂钩**：API-120、API-153
- **判定**：Given 已确认推送，When 观察执行，Then `release_push` 实际调用为**系统内部**（无「执行生产发布」产品 API）；调用失败进入 FAILED_RETRYABLE 后，API-153 人工幂等重试不得重复创建外部 item。
- **里程碑**：M3

### FR-16 Copilot 最小版

**AC-068**
- **ID**：AC-068
- **FR**：FR-16
- **API 挂钩**：API-192
- **判定**：Given 越权测试集（跨项目/跨租户查询与白名单外工具），When 发送 Copilot 消息，Then 100% 阻断（DENY / refused_policies），不得返回越权数据。
- **里程碑**：M3

**AC-069**
- **ID**：AC-069
- **FR**：FR-16
- **API 挂钩**：API-199、API-010、API-192
- **判定**：Given 对应 AI 能力/模块开关已关停，When 调用 API-192（或 A6 路径），Then 开关真实生效（命令失败或能力不可用），不得只改展示文案仍放行调用。
- **里程碑**：M3

**AC-070**
- **ID**：AC-070
- **FR**：FR-16
- **API 挂钩**：API-010
- **判定**：Given 模型网关整体不可用，When 使用执行 / 报告 / 门禁，Then 平台这些功能仍可用；仅 AI 增强降级，且页面/API-010 降级投影显式提示，禁止静默。
- **里程碑**：M0（降级骨架）/ M3（Copilot 横幅）

**AC-071**
- **ID**：AC-071
- **FR**：FR-16
- **API 挂钩**：API-192、系统内部
- **判定**：Given 用户在 Copilot 中诱导越权或注入，When 消息到达后端，Then Policy Gate 拦截、记录安全事件；注入测试集覆盖该模式。M3 最小版**不要求** API-194 / API-195 作为必过。
- **里程碑**：M3

### FR-17 副作用分级与 Policy Gate

**AC-072**
- **ID**：AC-072
- **FR**：FR-17
- **API 挂钩**：API-120
- **判定**：Given 动作未声明 sideEffectLevel，When Preview（API-120）或等价内部裁决，Then **默认拒绝（DENY）**，不得 ALLOW。
- **里程碑**：M0

**AC-073**
- **ID**：AC-073
- **FR**：FR-17
- **API 挂钩**：API-120
- **判定**：Given 策略表驱动的用例集，When 对已声明 L0–L4 动作 Preview，Then 输出为 ALLOW / DENY / REQUIRE_APPROVAL / REQUIRE_REAUTH 四值之一；单元测试全覆盖策略表。
- **里程碑**：M0

**AC-074**
- **ID**：AC-074
- **FR**：FR-17
- **API 挂钩**：API-004、API-120
- **判定**：Given L3+ 且会话超过再认证窗口（窗口数值 TBD），When Preview 返回 REQUIRE_REAUTH，Then 必须完成 API-004 step-up 后再重放命令；模型或客户端声称「已获批准」不构成授权。
- **里程碑**：M0

### FR-18 执行环境与引用型用例

**AC-075**
- **ID**：AC-075
- **FR**：FR-18
- **API 挂钩**：API-062、API-061、API-070
- **判定**：Given 引用型用例参数未通过 Job Schema（API-070 所供 schema），When 发起执行，Then 校验在 VALIDATING 完成，状态 **VALIDATING→FAILED**，不进执行队列、不触发外部 Job。
- **里程碑**：M1

**AC-076**
- **ID**：AC-076
- **FR**：FR-18
- **API 挂钩**：API-080、API-090
- **判定**：Given 同一 `idempotency_key`（或等价稳定键）已触发过外部 Job，When CI/Token 重放发起，Then **不重复**创建外部 Job；平台侧仍落同一业务受理语义。
- **里程碑**：M1

**AC-077**
- **ID**：AC-077
- **FR**：FR-18
- **API 挂钩**：API-031、系统内部
- **判定**：Given 引用型用例绑定的 Job 被外部删除或改名，When 执行前存在性校验失败，Then TestCase.`validity=invalid`（系统标记，可逆，区别于 DEPRECATED），通知 Owner，**不进入执行队列**。
- **里程碑**：M1

**AC-078**
- **ID**：AC-078
- **FR**：FR-18
- **API 挂钩**：API-061、API-063、API-020
- **判定**：Given 外部 Job 排队或长时间无响应，When 观察 TestRun，Then 状态为 WAITING_EXTERNAL 且可见滞留时长；超时**仅告警、不自动取消**外部 Job；人工 API-063 幂等取消后，已产生的构建记录仍采集入库。
- **里程碑**：M1

**AC-079**
- **ID**：AC-079
- **FR**：FR-18
- **API 挂钩**：系统内部；查询 API-061
- **判定**：Given `trigger_type=ci_webhook` 已受理后平台进程重启，When 恢复，Then 幂等键保证不重复触发外部 Job；轮询从中断处恢复（先到者：webhook 或轮询）。
- **里程碑**：M1

**AC-080**
- **ID**：AC-080
- **FR**：FR-18
- **API 挂钩**：API-090
- **判定**：Given 入站 webhook，When 签名缺失或错误，Then 拒绝（不得当会话命令处理、不得跳过验签）。HMAC 无例外分支。
- **里程碑**：M1

**AC-081**
- **ID**：AC-081
- **FR**：FR-18
- **API 挂钩**：API-032、API-102
- **判定**：Given 引用型用例，When 读取定义，Then 不托管脚本（`script_ref` 空），仅 Job 绑定 / 参数 / 采集配置 / 门禁映射；新环境须 API-102 经审批后 ACTIVE 才可选。
- **里程碑**：M0（环境）/ M1（引用型用例）

### FR-19 双执行模式

**AC-082**
- **ID**：AC-082
- **FR**：FR-19
- **API 挂钩**：系统内部
- **判定**：Given Agent 请求白名单外工具或越权资源，When Tool Router + Policy Gate，Then 100% DENY 并记录安全事件（注入测试集）。
- **里程碑**：M2

**AC-083**
- **ID**：AC-083
- **FR**：FR-19
- **API 挂钩**：API-067
- **判定**：Given 达到 manifest `max_steps` 或总超时，When 系统终止，Then 轨迹保存且 A8 `status` 为 incomplete（或等价 incomplete 标记），**无自动重试**；系统主动终止走 STOPPING→CANCELLED。
- **里程碑**：M2

**AC-084**
- **ID**：AC-084
- **FR**：FR-19
- **API 挂钩**：API-063、API-061
- **判定**：Given Agent 任务终止请求，When API-063 受理，Then 终止信号在服务端持久化，多 worker 均可停下；受理 ≠ 已 CANCELLED（同 AC-040）。
- **里程碑**：M2

**AC-085**
- **ID**：AC-085
- **FR**：FR-19
- **API 挂钩**：系统内部
- **判定**：Given 连续 3 次工具/资源 DENY，When 计数达到 3，Then 自动终止该 Agent 任务（轨迹 incomplete，无自动重试）。
- **里程碑**：M2

**AC-086**
- **ID**：AC-086
- **FR**：FR-19
- **API 挂钩**：API-146
- **判定**：Given `execution_source=agent` 的 TestRun 已终态，When GET API-146，Then **不存在** GateEvaluation（`gate_evaluation_id` 空），不得把 Agent 结果写入门禁或 Check Run 资格集。
- **里程碑**：M2

**AC-087**
- **ID**：AC-087
- **FR**：FR-19
- **API 挂钩**：API-068、API-030
- **判定**：Given 轨迹转脚本，When API-068 成功，Then 产物通过 schema 校验并创建新 TestCase（DRAFT）；校验失败则不入库。原 run 状态不变。
- **里程碑**：M2

**AC-088**
- **ID**：AC-088
- **FR**：FR-19
- **API 挂钩**：系统内部；查询 API-061
- **判定**：Given Agent 进程失联，When 心跳超时，Then RUNNING→TIMEOUT（与系统主动超步的 STOPPING→CANCELLED 区分）。不得永久 RUNNING。
- **里程碑**：M2

---

## 7.1 覆盖核对

| 项 | 结果 |
| --- | --- |
| AC 编号 | AC-001 … AC-088，连续无断号，共 **88** 条 |
| FR-01…FR-19 | 每一 FR 至少 1 条（见各节标题） |
| LDAP | 未列为 M0 必过 |
| API-222 | 仅 AC-047 负向：非 M0 必过 |
| Gate 缺配 | AC-057 / AC-061：无 GateEvaluation + reason，不用 `not_evaluated` 枚举 |
| 制品保留 | 无默认天数；保留期 TBD / Q6 |
| §2.3 边界 | 超大报告 AC-035；生成 partial AC-027；AI 降级 AC-070；审批超时不放行 AC-020；压测互斥 AC-054；CI 重启幂等 AC-079；跨租户 404 AC-003；脱敏 / Restricted AC-010；Agent 超步 AC-083；Job 失效 AC-077；等待态可见 AC-043 / AC-078；注入 AC-071 / AC-082 |

**关键 FR 路径对照**：FR-04 含批准成功（AC-015）、拒绝（AC-019）、过期等待（AC-020）、哈希失效（AC-016）、unknown（AC-017）；FR-05 含生成不落库（AC-022）与失败/partial（AC-024/027）；FR-08 含受理（AC-037）、回执非终态（AC-038）、取消受理非 CANCELLED（AC-040）；FR-12/13 含缺配不放行；FR-18 含 VALIDATING→FAILED 与幂等；FR-19 含 DENY、incomplete 无重试、无 GateEvaluation。

---

## 8. Out of Scope、冲突登记

> HuntAI Test PRD v2 · 第 8 章 + 附录 A–E  
> 综合自中期版 v1.6 §1.5、§3–§8，以及架构 / 边界 / API 契约已冻结口径。  
> **本章不发明新产品功能。** 不把 MCP、LangGraph checkpoint、WebSocket 写成产品需求。  
> M0–M3 **不采用** MCP（架构 §15.3）。制品保留期 **不得** 把 90 天写成已批默认（架构 §13.3）。`not_evaluated` 保持 **Proposed**（ADR 0003）。

---

## 8.1 非目标（沿用 v1 §1.5，六条原文）

1. 不替代 Jira / Confluence / GitHub / CI-CD / Release 系统——只做单向读取 + 审批后写入，不做双向全量同步；
2. 不自研压测引擎（包装 Locust/k6）、不做 APP 自动化、不做计费/白标/Workflow Builder/软件目录；
3. 不做无人审批的 AI 自动改写/自动应用（一切 L2+ 副作用必须 HITL）；
4. 不做对外 SaaS / 多租户计费；
5. 不复制 TestHub（GPL-3.0）任何源码——只借鉴机制；
6. 一期不做：视觉回归、语义去重、NL2Script、MCP 对外暴露（M4 评估）。

---

## 8.2 纯本地操作（边界 §5.2，验收不为其编造 API）

下列操作属于前端 UI，**无服务端状态变更、无 API 调用**。验收标准不为这些条目发明接口、资源或 OpenAPI 路径。对照 [frontend_backend_boundary_spec-v1.0.md](../06_architecture_design/frontend_backend_boundary_spec-v1.0.md) §4.2 / §5.2。

| # | 纯本地操作 | 说明（不构成后端事实） |
| --- | --- | --- |
| 1 | 七态渲染 | 七态基线 + 链路特殊态的页面呈现（`frontend_design_spec` §5.1）；终态只认后端下发 |
| 2 | 表单即时校验 | 格式 / 必填 / 类型的提示性校验；权威校验在后端（Job Schema / 双层变量 / 存在性 / 配额） |
| 3 | 联动置灰 | 模式 × 环境组合、非 ACTIVE 环境、角色只读；置灰 ≠ 安全边界 |
| 4 | 动态表单 | 按后端下发的 `params_schema_ref` 渲染控件，前端不自造 schema |
| 5 | 查看器控件 | diff 查看器、参数哈希折叠、Trace 回放、证据三件套切换 |
| 6 | URL 状态 | 列表筛选 / 排序 / 分页进 URL，可分享可回溯；不落库 |
| 7 | 响应式 | 布局降级，语义不变 |
| 8 | 入口可见性 | confidence ≥0.7 的「可应用」、发起人「批准」置灰、M3+/M4 里程碑入口隐藏——**均仅呈现层** |
| 9 | P07 草稿 / 聚类提交前暂存 | P07 草稿编辑、聚类修正的本地内存暂存；**提交才调 API** |
| 10 | 确认对话与防抖 | 确认对话框、按钮 loading / 防抖；权威防重是幂等键 + 行锁 |

**补充（属 §4.2，不为本地操作编造 API）**：SSE **订阅与渲染**只展示进度与变化提示，不是命令通道或状态机。断线重连、降级轮询、保留窗口的协议细节登记为 [GAP] G3，不在本章发明产品接口。

---

## 8.3 M4 未启用（不得当作本阶段必须交付）

下列能力保留在阶段计划 M4 行（见附录 B），**本阶段不启用为产品需求**：

| 项 | 口径 |
| --- | --- |
| Prompt A/B | M4；一期不交付 |
| A7 LLM Judge | 规格见附录 A；**交付范围 = M4 Out of Scope** |
| RAG / Confluence 回流 | M0–M3 以证据包导出承接知识回流，不擅自实现 M4 Confluence/RAG（架构 C1） |
| NL2Script | 与 §1.5 第 6 条一致；M4 评估 |
| MCP 对外 | **M0–M3 不采用**（不引入 client/server、SDK、传输或对外承诺）；M4 仅条件只读 POC 候选，**不是**本 PRD 的必须需求 |
| Copilot 写操作 `copilot_write` | M4 预留 action_ref；M0–M3 调用一律拒绝、不得入队 |
| P19 技能管理（API-194 / API-195） | P19 为 M4 页；技能列表与三级发布不作为本阶段必须交付 |
| Agent Mode 完整闭环 | FR-19：**M2 仅试点**，M4 才完整；探索结果不进门禁（`execution_source=agent`） |

---

## 8.4 Proposed（已标注，非本阶段必须）

下列为候选 / 待上游批准，**不得写成已批准实现或本阶段验收必须项**：

| 项 | 状态与出处 |
| --- | --- |
| GateEvaluation `not_evaluated` | **Proposed**（[ADR 0003](../06_architecture_design/adr/0003_canonical_state_and_gate_semantics.md)）。现行枚举仅 `pass / fail / waived`。当前兼容：无 GateEvaluation + 查询投影明确 reason，**绝不默认 pass** |
| API-222 制品短期授权 | **Proposed M2+**（`api_spec` §14.2 / ADR 0007 混合预签名）。M0/M1 调用视为能力未启用。Restricted 永不走普通预签名 |
| ADR 0003–0008 | 全部 **Proposed**。Accepted 仅为 ADR 0001（模块化单体控制面）与 ADR 0002（Temporal 运行时选型）。Proposed 不得指导实现为最终定论 |
| 环境恢复边 `DEGRADED→ACTIVE` / `DISABLED→PENDING_APPROVAL` | **Proposed**。现行状态仅 `PENDING_APPROVAL → ACTIVE → DEGRADED → DISABLED`。批准前不得后台改库或把建议边当已存在迁移 |
| L2 作用域化持续授权（standing authorization） | **Proposed**（ADR 0004 / `api_spec` §8）。不新增第 24 对象、不提供独立 API 资源；未批准前不得做成绕过审批的通道 |
| LDAP 独立端点 | **Proposed**（`api_spec` §14.2）。当前契约不另列 LDAP 产品端点。见下方 [CONFLICT] |

---

## 8.5 [GAP] 仅登记、建议阶段，不写入 FR 正文

缺口只登记，**不升格为 FR、不编造验收必须项**。TTL / heartbeat 等数值一律 **TBD**，禁止把未批数字写成默认。

| ID | 缺口 | 建议阶段 / 归属 | 本 PRD 处置 |
| --- | --- | --- | --- |
| G1 | AI 生成草稿（默认不落库）的暂存与获取：同步 vs 轮询、暂存生命周期（TTL）、多端续审 | 07 API 契约 | **不入 FR**。M0/M1 已有生成挂钩，TTL 数值 TBD |
| G2 | Excel 导入的格式契约与导入用例初始态（DRAFT 还是 PENDING_REVIEW）、是否复用两步式审阅 | 05 §2.1 或后续 FR-05 补充 | **不入 FR**。初始态 TBD |
| G3 | SSE 断线重连、降级轮询、无 SSE 页面的自动刷新 | 07 推送契约 | **不入 FR**。协议细节 TBD；不为本地渲染编造 API |
| G4 | 通知的前端呈现形态与获取方式（站内中心 / 角标 / 列表） | 05 组件或原型确认 | **不入 FR**。通知产生与投递仍属后端，形态 TBD |
| G5 | Artifact / 证据包 / 导出的访问形态（直链 / 预签名 / 代理） | 07 API 契约 | **不入 FR**。M0/M1 **以 API-221 代理下载为已有挂钩**；API-222 见 §8.4 Proposed |
| — | 审批 TTL / 心跳周期 / 僵尸回收阈值 / 排队超时告警 / Agent 超时等数值 | 配置项表（架构开放问题） | **TBD**。禁止隐式默认 |

---

## 8.6 明确不作为产品需求的技术面

| 项 | 口径 |
| --- | --- |
| MCP | M0–M3 关闭；不作为产品功能、对外承诺或验收项 |
| LangGraph checkpoint | 架构调研结论，**不是**产品需求；是否采用、存储/加密/清理仍未决定 |
| WebSocket | **不**作为产品推送通道。进度流沿用既有 SSE 原则（展示-only）；不为 WebSocket 编写 FR / AC |

---

## [CONFLICT]（只登记，本章不作裁定）

下列冲突已存在于上游文档之间。**v2 不在此裁决**；可测主路径与兼容行为如下标注，供评审使用。

### CONFLICT-1 · LDAP / 身份主路径

| 来源 | 表述 |
| --- | --- |
| 旧 PRD FR-01 | 「SSO（OIDC）/LDAP 登录」并列 |
| `api_spec` API-001 / API-002 | **仅** OIDC Authorization Code + PKCE 的 start / callback；契约不另列 LDAP 端点 |
| 架构 §13.1 | OIDC 为主认证**候选**；LDAP 仅在企业无 OIDC 时作为**兼容候选**，优先经企业身份代理；IdP、claim、MFA、JIT、会话时长、禁用传播仍为 **TBD** |
| `api_spec` §14.2 | LDAP 独立端点列为 **Proposed**，不得当已批准实现 |

**可测主路径**：OIDC（API-001 / API-002）为当前可测试的登录主路径。  
**不新增 Q11。** IdP 细节指向架构 §13.1 TBD；外部系统版本与权限边界仍走既有 **Q5**（Jira/GitHub/CI）。LDAP 独立产品端点保持 Proposed，不写入本阶段 FR 必须项。

### CONFLICT-2 · 90 天制品保留

| 来源 | 表述 |
| --- | --- |
| 旧 PRD §4.1 / §6.3 | 「默认 Trace/视频保留 90 天」；容量「按 90 天保留估算」 |
| 架构 §13.3 / ADR 0007 | **禁止**把未批准的 90 天写成默认；保留期、扫描器、下载次数、Legal Hold 均 TBD |

**处置**：制品保留期 **TBD**（附录 D **Q6** 法务 + 安全）。禁止把 90 天当已批默认。容量估算同步改为 TBD（附录 B）。

### CONFLICT-3 · 「未评估」 vs `not_evaluated`

| 来源 | 表述 |
| --- | --- |
| 旧 PRD FR-12 | 阈值缺配判定为「未评估」而非默认通过 |
| ADR 0003 / 架构 §7.5 | `not_evaluated` 为 **Proposed** 上游枚举变更，获批前不得写入不存在的枚举值 |
| 当前兼容 | **无 GateEvaluation + 查询投影明确 reason**；CANCELLED / TIMEOUT / 缺配 / partial **不得默认 pass** |

**处置**：产品语义「不得静默放行」保留；枚举名 `not_evaluated` 保持 Proposed，不写入本阶段必须验收的结果值。

### CONFLICT-4 · v1.6 文首「尚未吸收 05/06/07」已过时

v1.6 文首声称「尚未吸收 05 业务建模 / 06 核心交互链 / 07 产品原型」。该声明对 **v2 已失效**：v2 综合交付已对齐建模、交互、边界、P01–P25 与 API 挂钩。本 CONFLICT 只纠正文档状态，不改变 US/FR 编号稳定性。

---

## 附录 A · AI 能力规格与 Prompt Contract

> 几乎原文迁移自中期版 §3.1 / §3.2。不新增 AI 能力。A2 category 保持 **7 值**枚举。`can_auto_apply` 恒为 **false**。  
> **A7 交付范围 = M4 Out of Scope**（规格保留供评测门槛引用，不作为本阶段必须交付）。

## A.1 AI 能力清单（输入 / 输出 / 质量阈值 / 模型策略 / 检索与工具调用 / fallback）

| # | 能力 | 输入 | 输出（结构化） | 质量阈值 | 模型策略 | 检索/工具调用 | Fallback |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A1 | Swagger→用例生成（M1） | OpenAPI 规范片段 + 用例类型策略 | `GeneratedCase[]`（名称/步骤/断言/变量提取/前后置/标签），断言 ≥2 类 | 首次接受率 ≥80%（字段级）；schema 合法率 100% | 私有网关高精度路由；temperature 0.2；分批 ≤10 接口/次；数据分级 ≤ Confidential | 无工具调用（纯生成） | 解析失败重试 1 次 → 显式失败列表；网关不可用 → 功能置灰，导入本身不受影响 |
| A2 | 失败聚类与归因（M1，核心） | 归一化失败集 + 证据池（日志/响应/Trace 元数据）+ 历史相似失败 | `FailureCluster[]`（见 A.2 schema） | 离线：cluster 语义一致性（人工双人标注 Krippendorff α ≥0.6，阈值假设待校准）；top-1 归因命中 ≥75%；无据结论率 <2% | temperature 0；严格 JSON；CoT 先理由后结论 | 检索：历史失败向量库（pgvector）；无写工具 | JSON 失败重试 1 次 → 规则聚类（错误码/接口路径分组）+ confidence 0.3 |
| A3 | UI 定位器自愈建议（M2） | 失效定位器 + DOM 快照 + 失败截图（多模态可选） | `LocatorHealSuggestion`（候选定位器 + 理由 + confidence + diff） | 建议采纳率 ≥60%（假设，M2 校准）；候选不改变语义（人工抽检） | 视觉模型路由（Confidential 及以下）；temperature 0 | 无 | 生成失败 → 仅提示人工修复，附 DOM diff |
| A4 | 归因修复建议（M1，并入 A2） | A2 的 cluster + 用例定义 | `FixSuggestion`（field/current/suggested/reason/confidence） | 同 A2；confidence ≥0.7 才展示「可应用」 | 同 A2 | 读用例版本（只读工具） | 低置信 → 仅展示诊断，不出建议 |
| A5 | Release notes 草稿（M3+） | Jira 范围快照 + 质量证据 | `ReleaseNotesDraft`（分类变更摘要 + checklist + 缺失项） | 字段填充率 ≥90%；**缺失项召回率优先于文采**（漏 blocker = 关键缺陷） | 结构化生成路由；成本上限按 skill 声明 | Jira 只读工具 | 拉取失败 → 明确标注数据缺口，禁止编造 |
| A6 | Copilot 问答（M3+ 最小版只读） | 用户问题 + 权限上下文 + 会话历史 | 答案 + 引用 + 工具调用记录 | 引用precision ≥90%（抽检）；越权拦截 100% | 多轮对话路由；会话服务端持久化 | 只读技能白名单（Jira/GitHub/平台查询） | 工具失败 → 声明无法获取，不猜测 |
| A7 | LLM Judge 生成质量评估（**M4 · 交付 Out of Scope**） | 用例 + 评分 rubric | `JudgeResult`（分项分 + 理由） | 与人工评定一致性 ≥75%（校准集） | 独立裁判模型（与生成模型不同源）；CoT + temperature 0；n=3 取中位数 | 无 | Judge 失败 → 该批次标记未评估，不阻塞人工流程 |
| A8 | Agent Mode 动态执行（M2 试点 / M4 完整；完整闭环见 §8.3） | 用例意图 + 页面状态/DOM + 工具清单（Skill manifest 声明） | `ExecutionTrajectory`（步骤 / 动作 / 截图 / 断言结果 / 工具调用记录 / incomplete 标记） | 探索集任务完成率 ≥60%；每步动作合法率 100%（Policy Gate 硬约束）；轨迹转脚本采纳率 ≥50%（三项均为假设值，M2 校准） | 多模态 / 文本路由按数据分级；temperature ≤0.2；max_steps 由 manifest 声明 | 浏览器 + 只读工具白名单（经 Tool Router + Policy Gate） | 超步 / 超时 / 工具失败 → 保存轨迹退出并标 incomplete（无自动重试）；网关不可用 → 任务排队不启动 |

**A2 category 枚举（7 值，禁止改回「8 类」）**：`env_down` / `auth_expired` / `locator_stale` / `assertion_real_bug` / `flaky` / `data_issue` / `unknown`（unknown 兜底）。

## A.2 Prompt Contract（以 A2 失败聚类为例，作为接口对待）

**契约标识**：`prompt/failure-triage` · 语义化版本（如 1.0.0）· 生产环境版本锁定（pin）· 变更走附录 B 十步门禁。

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

**禁止行为**：① `evidence_refs` 只能引用输入证据池内存在的 ID（服务端校验，违规输出整批拒收）；② 不得输出任何执行类指令；③ 不得建议跳过/删除用例；④ 不确定必须输出 `unknown`/`uncertain`，禁止编造 root_cause；⑤ confidence 禁止默认 1.0。

**失败处理**：schema 校验失败 → 同参数重试 1 次（temperature 0）→ 仍失败走 A2 fallback（规则聚类）并记 `AIInvocationLog.result=degraded`；30s 超时同路径。

**版本与回滚**：任何修改产生新版本，新旧并行影子运行 ≥1 个回归周期；回滚 = 恢复上一 approved 版本（分钟级，配置切换，无需发版）；未版本化 prompt 不得进生产（CI 强制检查）。

---

## 附录 B · 评测、指标、发布门槛、SLO / 容量

> 迁移自中期版 §5 与 §6.1–§6.5。  
> **变更**：废除「默认 Trace/视频保留 90 天」与「按 90 天保留估算」；改为 **TBD（Q6 法务）**。既有编号 SLO 与北极星计数口径（v1.5）保持不变。

## B.1 离线评测（M0 建集，持续维护）

- **Golden dataset**：30–50 个历史测试运行样本（含失败样本）+ 人工标注（双人标注 + 仲裁）——研究包 Discovery 建议直接采纳；
- 确定性解析器：字段级解析准确率 ≥98%；
- A2 聚类：语义一致性 α ≥0.6（假设阈值）；A7 Judge：与人工一致性 ≥75%（A7 本身为 M4 Out of Scope，该门槛仅在 M4 若启动时适用）；
- Prompt Injection 套件：恶意 Jira 描述/日志/评论样本，拦截率 100%；
- Schema validity 100%；越权测试集（双租户）100% 阻断。

## B.2 人工评测

- 每迭代抽检：A1 生成用例可执行率（语法可跑 + 语义合理，抽检 50 条）；A3 建议「语义不变」抽检；标注一致性行动：α <0.6 时修订 rubric 而非放水。

## B.3 线上指标（看板 + 告警）

| 指标 | 定义 | 目标 | 告警阈值 |
| --- | --- | --- | --- |
| 北极星 | 每周「成功完成 + 被接受 + 产生可验证结果」的受控工作流数。**计数口径（v1.5）**：一次计数 = 同时满足①工作流实例达终态 SUCCEEDED；②存在人工接受动作（用例采纳 / 分诊报告审阅通过 / 审批批准 / Release 确认之一）；③产出至少一个可验证外部结果或质量结论（Jira issue / Check Run 结论 / GateEvaluation / ReleaseTask item / 入库用例版本）。**去重规则**：同一 TestRun 的重跑、同一审批的重新提交只计 1 次；`execution_source=agent` 的 run 仅在其轨迹被固化为脚本并入库后计数（避免探索性执行虚增） | 试点 3 个月 ≥30/周（假设） | 连续 2 周环比 -20% |
| 首次接受率 | 生成字段未经修改被接受比例 | ≥80% | <60% 触发评审（研究包 kill 线） |
| 证据覆盖率 | 关键结论挂有效 evidence_ref 比例 | ≥95% | <90% |
| 无据结论率 | 关键结论无证据支撑比例 | <2% | ≥5% |
| 外部误写 | 无有效审批的外部写操作 | 0（硬性） | =1 即事故（P1） |
| 审批反悔率 | 已批准动作事后因错误回滚比例 | <1% | ≥3% |
| AI 降级率 | 走 fallback 的 AI 调用占比 | <5% | ≥15% |
| 每成功工作流成本 | （模型+执行可变成本）/成功工作流 | 计量并设预算（基线 TBD） | 超部门预算 |

## B.4 发布门槛

- **阶段 Gate**：技术闭环 Gate（重启不重复副作用 / AI 结论全量挂证据 / 越权全阻断）+ 业务价值 Gate（BG-1/2/3）；
- **AI 资产十步门禁**（Prompt/Skill/ModelRoute 任何升级）：schema test → unit/contract → golden dataset → 注入套件 → 权限测试 → 成本/延迟回归 → shadow/canary → Owner+安全审批 → 版本锁定 → 回滚计划。

## B.5 成本

- 全量 Token 计量（FR-02）；部门预算熔断；单价表随模型路由配置维护（单价 **TBD**，随模型拍板）；目标：每成功工作流成本可度量且有预算上限（基线 **TBD**，M1 末回填）。

## B.6 延迟（SLO，均为可测定义）

既有编号 SLO **保持不变**：

- 平台只读 API：P95 < 1s（不含模型任务）；
- AI 流式生成：首 token P95 ≤ 3s（交互场景）；
- A2 分诊：run 完成后 ≤5 分钟出报告（10k 用例级）；
- 执行类（UI 套件/压测）异步无用户等待 SLO，提供进度流（SSE）；
- Check Run 回写：CI 结束后 ≤2 分钟；
- 压测 kill switch：60s 内停止全部施压进程（见附录 C）。

## B.7 容量（假设值，M0 校准）

- 1000 注册 / 假设 200 DAU；
- 并发执行：接口 50 run、UI 8 slot（TBD）、压测全局并发预算 TBD（压测引擎侧另计）；
- 报告解析吞吐 ≥1000 用例结果/分钟；
- **对象存储容量：按制品保留期估算，保留期 TBD（Q6 法务确认后精算）。禁止按 90 天作为已批默认做容量承诺。**

## B.8 制品保留期

- 制品（Trace / 视频 / 截图 / 报告 / 证据包）保留期 **TBD**（附录 D **Q6** 法务 + 安全确认）。
- **禁止**把「90 天」写成已批准默认，也禁止把 90 天写进验收标准或配置默认值。
- 审计留存期与制品保留期分开确认；Legal Hold / 删除 / WORM 同步 TBD。

## B.9 外部依赖

企业 SSO(IdP)、Jira REST/Webhook（版本 TBD）、GitHub App 权限、CI API（触发/产物读取）、Release 系统 API（**readiness TBD**）、企业模型网关、Vault、Temporal（持久工作流运行时已选定；托管/自托管、生产容量、成本、RPO/RTO 与值班方案待 Gate）。**选型不等于生产就绪**，见 Q3。

## B.10 阶段计划（M0–M4，对齐 README 第 8 章）

| 阶段 | 里程碑 | 放行条件 |
| --- | --- | --- |
| M0（1–2 月） | 基座：租户/SSO/AI 日志/审批中心/集成骨架/队列化 TestRun/执行环境注册中心（Jenkins 注册 + 健康检查 + Job 发现）+ **基线盘点与评测集建设** | 一致性检查 FAIL 项闭环；越权测试通过；注册 CI 实例健康检查与 Job 发现可用 |
| M1 | 接口自动化 + A1/A2/A4 + 执行环境抽象与引用型用例 v1（Jenkins 触发 + JUnit 采集） | Gate：解析 ≥98%；首次接受率开始计量；引用用例重放不重复触发外部 Job |
| M2 | Web 自动化 + 门禁 + Jira + CI 接入完善（多格式适配器 + 日志分片 + webhook 回调） | Gate：BG-2 覆盖 100% 核心项目 |
| M3 | 性能 + Release v1 + Copilot 最小版 | Gate：压测 kill switch 演练通过 |
| M4 | Prompt A/B + Judge + RAG + NL2Script + MCP | Gate：A7 一致性 ≥75% |

M4 行是阶段愿景，**不等于本 PRD 已启用**。MCP / A7 / Prompt A/B / RAG / NL2Script / P19 / `copilot_write` / Agent 完整闭环见 §8.3。

---

## 附录 C · 失败模式、降级、kill switch、RACI

> 迁移自中期版 §7 与 §6.6。A1–A8 kill switch、关停 L1 / 恢复 L3 保持不变。Temporal **选型 ≠ 生产就绪**，生产形态仍走 **Q3**。

## C.1 失败模式与处置矩阵

| 失败模式 | 检测 | 自动处置 | 人工接管点 |
| --- | --- | --- | --- |
| 模型超时/不可用 | 超时 30s、网关 5xx | AI 功能降级（fallback 见附录 A）；平台核心功能不受影响 | 无需（SRE 告警响应网关） |
| 低置信度输出 | confidence <0.7 | 不展示「可应用」；标注 uncertain | Test Lead 审阅报告 |
| 敏感输入进入 AI 请求 | 路由层分级校验 | 拦截 + 记录 + 提示改用本地路由 | 管理员审查分级规则 |
| 越权尝试（Copilot/工具） | Policy Gate + 越权测试集 | DENY + 安全事件记录 | 安全工程师周审 |
| Prompt Injection | 分层校验 + 注入模式检测 | 拒绝执行工具调用 | 安全工程师分析样本 |
| 解析失败/幻觉 | schema 校验、evidence_refs 校验 | 整批拒收 → fallback；无据结论计入指标 | 评测责任人修订 prompt |
| 执行器僵尸任务 | 心跳超时 | 自动转 TIMEOUT 并回收（对齐 05 §2.2；旧表述「标记 FAILED」作废） | Test Lead 决定重跑 |
| 审批超时/过期 | TTL 计时 | 升级通知 → 过期不自动放行 | 备审批人 |
| 压测失控 | SLA 熔断 + 自监控 | abort_on_breach 自动停 + kill switch | 性能工程师确认 |
| 外部误写 | 审计对账 | — | **P1 事故流程**（C.3） |

## C.2 降级顺序（总原则：先保平台、再保证据、最后保 AI 增强）

AI 增强（生成/归因/建议）→ 只读查询 → 平台执行/报告/门禁。任一层降级在 UI 显式横幅提示，不静默。

## C.3 事故响应

分级：外部误写/数据泄露 = P1（立即 kill 相关连接器写入 + 通报 + 取证审计链）；AI 质量劣化（无据结论率 ≥5%）= P2（回滚 prompt 版本 + 灰度收量）；其他 P3。响应 SLO：P1 15 分钟启动、1 小时止血决策；事后 blameless 复盘进风险登记。

## C.4 Kill Switch 与回滚

- **开关层级**（全部真实生效并有自动化测试验证）：单能力（**A1–A8**）→ 模块（Copilot/Release/压测）→ 连接器（Jira/GitHub/CI/Release 写入）→ 全局 AI。压测 kill switch：60s 内终止全部施压进程。开关操作入口 = 「AI 能力开关与降级」页（P23）。
- **关停即时生效不走审批（L1），恢复走审批（L3，action_ref=`kill_switch_restore`）**。
- **回滚**：Prompt/Skill = 版本切换分钟级；用例/定位器修改 = 快照恢复；外部写入 = compensation（如 CI Job cancel）+ Jira 缺陷关闭草稿（不自动删外部对象，人工确认）；平台发版 = 蓝绿 + 数据库迁移向前兼容。

## C.5 Temporal 选型与生产就绪

Temporal 已作为持久工作流运行时选型（ADR 0002 Accepted）。**选型不等于生产就绪。** 恢复、版本、容量、成本、托管/自托管与值班 Gate 仍须通过，登记于附录 D **Q3**。未通过不得放量。

## C.6 RACI（角色级，人名 M0 指派）

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

## 附录 D · 开放问题与假设

> 保持中期版 Q1–Q10 与 §8.2 / §8.3。不新增 Q11。LDAP 见第 8 章 [CONFLICT]-1（OIDC 可测主路径 + 架构 §13.1 TBD IdP）。90 天见 Q6 与 [CONFLICT]-2。

## D.1 开放问题（TBD 登记，含负责人与期限）

| # | 问题 | 负责人（角色） | 期限 |
| --- | --- | --- | --- |
| Q1 | 测试分析耗时/采纳率/成本三项基线盘点（一致性检查 FAIL 项） | 平台负责人 + QA 负责人 | M0 第 2 周 |
| Q2 | 模型与供应商选型（含单价表、数据分级路由） | AI 工程师 + 安全 | M0 结束 |
| Q3 | Temporal 生产形态与就绪 Gate（托管/自托管、恢复、版本、容量、成本、值班） | 平台架构师 + SRE | M0 第 4 周 |
| Q4 | Release 系统 API readiness（幂等/webhook/权限） | 后端/集成 Owner | M2 中期（M3 前） |
| Q5 | Jira/GitHub/CI 的版本与权限边界确认 | 集成 Owner + 各系统 Owner | M0 结束 |
| Q6 | 制品保留期与审计留存期的法务确认 | 法务 + 安全 | M1 前 |
| Q7 | 压测环境白名单与全局并发预算数值 | 性能工程师 + SRE | M3 前 |
| Q8 | RACI 人名指派 | 平台负责人 | M0 启动会 |
| Q9 | 试点部门选择与北极星基线口径 | 平台负责人 + QA 负责人 | M0 第 2 周 |
| Q10 | A2/A3/A7 质量阈值假设值校准（评测集建成后） | QA/评测工程师 | M1/M2 末 |

## D.2 假设

1. 研究包的目标值（-50%/≥80%/≥95%）可作为假设目标——**待基线校准**；
2. 企业模型网关可用且支持结构化输出与多模型；CI 系统提供触发与产物读取 API；
3. 试点部门愿意提供 30–50 个历史样本（否则评测集建设延期，M1 放行条件不成立）；
4. ≤1000 用户内部规模下 pgvector 满足检索需求（超载再演进 Qdrant）。

## D.3 风险登记（概率 / 影响 / 负责人 / 缓解）

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

---

## 附录 E · 变更日志

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1.0 | 2026-08-23 | 基于 README v1.2 与 03 借鉴文档（原编号 02），按 AI PRD 模板首版生成；含一致性检查（1 FAIL / 1 PARTIAL）与 10 项 TBD 登记 |
| v1.1 | 2026-08-23 | 新增双执行模式（Script Mode / Agent Mode）：US-13、FR-19、A8 能力规格、2 条边界场景；对齐 README v1.3 之 4.0 节 |
| v1.2 | 2026-08-23 | 执行架构增加执行环境维度（平台执行器 / 企业 CI）：US-14、FR-18 扩展为执行环境与引用型用例（Mock 型）、新增 ExecutionEnvironment 数据对象与 Jenkins Job Contract 集成契约、2 条边界场景、M0–M2 阶段计划调整；对齐 README v1.4 |
| v1.3 | 2026-08-23 | 文档编号对齐开发流程图（移至 Stage 12 槽位）；定位更新为终版 PRD 位——待 06 交互链与 07 原型完成后重生成 v2 终版 |
| v1.4 | 2026-08-24 | Stage 6.5 缺口回写（依据四条交互链「缺口上报」26 项裁定）：FR-06 归因分类对齐 §3.2 枚举 7 值；FR-13 补门禁豁免流程（gate_waiver，L3，走 FR-04 审批）与触发绑定页面指引；FR-17 补 REQUIRE_REAUTH 触发条件；FR-18 验收补校验落点（VALIDATING→FAILED）与排队超时行为；FR-19 验收补 Agent 终态归属；§2.3「Job 被删」补 validity 标记落点；§7.1 僵尸任务对齐 05 §2.2（TIMEOUT） |
| v1.5 | 2026-08-24 | 全链路一致性复核修复（Stage 3→6 反向核查，含 03/04/05/06/12 交叉验证）：① US-FR 映射补 5 个基座类 FR 无 US 承接（US-15~19：FR-01/02/08/12/17），现双向无孤儿；② 状态数口径统一（10 态，作废「8 态」旧表述）；③ 归因 category 枚举 7 值（作废「8 类」）；④ AI 能力编号 A1–A8（作废「A1–A7」漏 A8）；⑤ FR-12 补验收标准（原缺）与新门禁对象落点（QualityGatePolicy / GateEvaluation，对齐 05 v1.3）；⑥ FR-13 补数据落点（同前）与豁免审批链路；⑦ §7.4 开关层级改 A1–A8 并补开关方向不对称裁定（关停 L1 / 恢复 L3）与页面指引；⑧ §2.3 补等待态滞留可见性边界场景（← 05 v1.3 裁定）；⑨ §5.3 北极星指标补计数口径与去重规则（原缺可测定义）；⑩ §3 核心对象摘要补齐 8 个对象（对齐 05 §1.1 的 23 对象清单）；⑪ FR-18/19 分期澄清（自 M1/M2 起，非始于 M2）；⑫ §0 一致性检查更新（US-FR 双向核查、补「对齐 05 对象清单」条目） |
| v1.6 | 2026-08-29 | 架构复审回写：FR-08 从 Temporal/Celery 候选收口为 Temporal 持久工作流 + 隔离 Activity Task Queue；明确 PostgreSQL 权威状态机、Outbox relay 与业务幂等，且选型不等于生产就绪；FR-04 增加 external result unknown 的对账/人工接管与禁止盲重试要求；Q3 改为托管方式、恢复、版本、容量、成本与值班 Gate。 |
| v2 | 2026-08-29 | 综合交付：对齐建模/交互/边界/P01–P25/API 挂钩；US/FR 编号稳定；验收改为 AC-001 起；LDAP/90天/not_evaluated 登记 CONFLICT 或 Proposed；FR-08 用户可感知化，实现细节不作为用户功能 |
