# HuntAI Test · 企业内部 AI 测试平台建设决策建议

> - **日期**：2026-08-24
> - **状态**：v1.5（全链路一致性复核修复：05 v1.3 补 3 对象 + 4 页面 + 状态机消歧，12-PRD v1.5 补 US-FR 双向映射 + 北极星计数口径，本文对齐 10 态 / 25 页口径；未含我方现状盘点，建议补充后复核）
> - **输入**：本仓库三份竞品拆解（WHartTest / FullScopeTest / TestHub，含源码级证据）+ 平台负责人需求草稿 + 企业研发 AI 助手研究包（2026-07-28）
> - **决策范围**：企业内部自用 AI 测试平台，≤1000 用户，部门级多租户，重点建设 Web 自动化、接口自动化、性能自动化、Release 编排与全局 Copilot，并与既有 Jira / GitHub / Confluence / CI-CD / Release 系统打通
> - **文档编号（对齐开发流程图 Stage）**：README = 决策总纲 · 03 市场调研（Stage 3）· 04 竞品功能拆解（Stage 4）· 05 业务建模（Stage 5）· 06 核心交互链（Stage 6，占位待生成）· 07 产品原型（Stage 7，占位待生成）· 08 后端架构（Stage 8，占位待生成）· 12 PRD（Stage 12 终版收口位，当前为中期版）
> - **迁移注记（2026-08-24）**：本文档集迁自 `opensource-product-analysis` 仓库 `decision/huntai/huntai-test/`，文件已按本仓库目录规范重命名。文内沿用原「开发流程图」编号（03–08 / 12），与本仓库路径映射：03 → `01_market_research/market_research.md` · 04 → `02_competitor_analysis/competitor_analysis.md` · 05 → `03_problem_modeling/problem_model.md` · 06 及 `interaction-design/` → `04_interaction_design/interaction_flows.md` 与 `chains/` · 07 → `05_prototype/prototype_spec.md` · 08 → `06_architecture_design/architecture.md` · 12 → `08_prd/prd.md` · CONSISTENCY-FIXES → `13_changes/consistency_fixes_20260824.md`。文中提到的 `competitors/`（三份竞品源码级拆解）与 `references/`（研发助手研究包）仍留在源仓库，未随迁。

---

## 1. 背景与建设目标

| 维度 | 约束 / 目标 |
| --- | --- |
| 使用规模 | 1000 人以内，企业内部自用（无商业化、无计费） |
| 租户模型 | 多租户 = 部门 / 事业部级隔离 |
| 既有系统 | Jira（项目/缺陷）、GitHub（代码/PR）、Confluence（文档/需求）、CI/CD 平台 |
| 三大重点域 | 接口自动化、Web 自动化、性能自动化 |
| 核心诉求 | AI 自动化测试，把各系统测试链路尽可能打通 |

**产品北极星（端到端闭环）**——三个竞品均未跑通、我方独有的价值主线：

```
Confluence 需求文档
   →（RAG + AI 生成用例 + 人工确认）
用例库（关联 Jira story）
   →（CI 触发 / 定时执行：接口 · Web · 性能）
执行结果
   → GitHub Check Run 回写 PR + 质量门禁
   → 失败自动归因 + 一键创建 Jira 缺陷（附截图/Trace 证据）
发布编排
   → Release Task（Jira 版本圈定范围 + 质量证据汇聚 + 就绪度门禁）
   → 调用企业 Release 系统准备 release item（人工确认）
执行结论回流知识库（RAG）
```

> **分期注记（v1.5）**：北极星首尾两端的 RAG 能力——起点「Confluence 需求文档（RAG）」与终点「执行结论回流知识库（RAG）」——属 **M4 里程碑**（见第 8 章）。一期起点以 OpenAPI / Postman / curl 导入承接（FR-05），终点以证据中心证据包导出（ZIP / MD / JSON）人工归档 Confluence 承接；Confluence 连接器与知识回流对象建模（Connector.type 扩展 + 回流机制：触发时机 / 内容范围 / 租户边界 / 是否人工确认）在 M4 启动时补入 05。

所有模块的优先级围绕这条闭环排列。

**产品原则**（v1.2 借鉴研发助手研究包，`docs/03_产品战略与PRD.md` §1）：

1. **Workflow first, Chat second**：固定业务页面承载确定流程，Chat 用于意图表达、解释与辅助操作；
2. **AI 提议、策略裁决、工作流执行**：模型只做理解、分类、生成与候选计划，不决定业务控制流、重试、幂等和权限；
3. **执行面与治理面分离**：测试执行（平台自建执行器 / CI 存量 Job）与治理（工作流/策略/证据/审批）解耦，两类执行面共用同一套归一化与 AI 分诊；
4. **每个副作用可归因**：任何外部写入可追溯到用户、工作流、模型、输入证据与审批；
5. **Evidence over eloquence**：关键结论必须引用具体 Jira/PR/Build/Test 证据，无据结论率 < 2%；
6. **渐进自治**：先草稿、再单步审批、后按低风险场景授权自动执行。

---

## 2. 三个核心结论

### 结论一：WHartTest 没有性能测试能力（需求草稿误读修正）

全部证据（Release 记录、官网、模块拆解）中无任何负载/压测功能，连 JMeter / Locust / k6 的提及都没有。它是「需求→用例→执行→失败分析」的 AI 链路型产品（Django + Vue + LangGraph + MCP + RAG），三大域中只覆盖 Web 与接口。**性能域不能从 WHartTest 获得任何参考。**

### 结论二：三个竞品都只能当「设计参考 + 验收反面清单」，不可直接依赖或二开

三份源码级分析的证据高度一致：

| 竞品 | 不可依赖的关键证据 |
| --- | --- |
| WHartTest | v2.1.0 破坏性升级明确丢 UI 脚本库数据；安全默认值系统性偏弱（弱口令、SSL verify=false）；无任何 AI 质量量化数据；出品方为公司实验室，自述学习研究用途 |
| FullScopeTest | README 宣称与 main 分支源码系统性差距：CI 门禁 FAIL 不影响 exit code、语义去重前端未接线、自愈无回滚端点、计费配额未接线、视觉管线疑似前后端键不匹配；单人冲刺项目 |
| TestHub | **GPL-3.0 传染性协议——机制可借鉴、代码严禁复制**；无多租户概念；对 Jira/GitHub/CI-CD 集成为零；API Key 明文入库等安全问题 |

**执行策略：吸收三家验证过的设计模式，按我方工程标准重建。**

### 结论三：真正的差异化机会是三个项目全都没有的「集成打通」

- WHartTest、TestHub：对 CI/CD、Jira、GitHub 集成**为零**；
- FullScopeTest：有集成设计（GitHub OAuth、Check Run、Quality Gate、API Token），但闭环在源码层断裂（PR 触发链路无 Check Run 创建、门禁不阻断、HMAC 验签三处可绕、跨租户仓库错配）。

我方平台的核心价值不是再造一个测试工具，而是第 1 节的端到端闭环。

---

## 3. 竞品资产总表：各借什么、各防什么

### 3.1 WHartTest（借鉴重点：AI 链路与信任机制）

| 借鉴 | 说明 |
| --- | --- |
| 接口先行的路径 | 它自身也是接口成熟后 v2.1.0 才补 UI——「接口先行、UI 后行」是被验证的路径 |
| 执行证据链 + AI 归因 | 截图/视频/Playwright Trace + 失败归因（日志+截图+Trace → 原因分类 → 修复建议），把「测试失败」变成「可行动的修复建议」 |
| Agent 工具审批闭环 | HITL 审批卡片 + 工具「始终拒绝」黑名单 + 全程审计——企业信任 AI 执行的第一前提 |
| Token 成本可观测 | 真实 usage_metadata 计量（非估算）+ 缓存命中 + 工具定义开销拆分，第一天就埋点 |
| 混合检索 RAG | Qdrant 稠密 + BM25 稀疏 + Reranker，一个知识底座供用例生成/需求评审/对话三场景复用 |
| 审计日志七字段 | 用户名/模块/操作类型/路径/IP/耗时/UA + 慢请求高亮 |
| UI 执行器独立进程 | Actuator 独立进程 + 能力上报 + Redis slot 租约（规模化后采用，MVP 留抽象） |

**防**：Skills 高权限技能商店（安全模型未解决）、11 种导入格式（长尾负担）、ONLYOFFICE 在线编辑（有 Confluence）、执行器集群过早建设。

### 3.2 FullScopeTest（借鉴重点：AI 工程化与门禁设计）

| 借鉴 | 说明 |
| --- | --- |
| AI 调用全量可观测 | AIInvocationLog + 统计看板（约 1 表 + 5 接口量级），全项目性价比最高的部件；必须保证无旁路（它的 Copilot 主路径绕过了日志） |
| Prompt 数据库版本化 + 加权 A/B | feature 版本自增 + traffic_weight 分流 + 从日志回算统计（它只接了 3 个端点，我方全量接入） |
| 失败自愈三段式 | 「建议（confidence≥0.7）→ 确认 → 应用前版本快照」；我方补齐：服务端复核 confidence、快照失败 fail-close、**回滚端点** |
| Quality Gate 三阈值 | min_pass_rate / max_p95_ms / 视觉差异上限——恰好对齐接口/Web/性能三域 |
| Swagger 生成两步式 | 生成默认不落库 → 人工审阅 → 保存，自动打 `ai-generated` 标签；严禁 save=true 绕过审阅 |
| API Token 细粒度 | 4 操作 × project_ids 白名单 + 有效期 + 可吊销——CI 集成刚需 |
| 性能安全护栏四件套 | SSRF 校验 + 参数上限（users 1–2000 / spawn_rate / duration）+ AST 脚本检查 + 进程硬超时 |
| ai_calls 一等配额资源 | 内部场景转化为「部门级 AI Token 预算」 |

**防**（即我方验收负面清单）：门禁 FAIL 不影响 exit code、`threading.Thread(daemon)` 假异步任务永久卡 running、Mock 端点匿名可访问 + CORS 回显、AST 黑名单自称沙箱实为 RCE 面、变量解析失败静默保留原文（假绿）、压测套用功能测试自动重试。

### 3.3 TestHub（借鉴重点：安全执行范式与数据建模；GPL——只借机制不抄代码）

| 借鉴 | 说明 |
| --- | --- |
| MCP 危险操作两段式 | preview → confirm + 可选人工审批 + 签名令牌（TTL、单次消费）+ 五态状态机——可推广到一切有副作用的 AI 动作。我方补齐：四眼原则（禁自批）、consume 行锁、审批窗口独立 TTL |
| 按角色模型配置 | 单表多角色（writer/reviewer/browser_use）+ 测试连接 + 启用禁用单活确认——企业接私有模型的门槛 |
| LLM-as-a-Judge | CoT 先理由后打分 + temperature=0 + 多裁判中位数聚合 + rubric 双源模板——衡量 AI 生成质量的基座 |
| AI 生成反馈闭环 | SSE 流式 → 采纳前编辑 → 批量采纳/弃用——「把 AI 功能变成可信 AI 功能的最短路径」 |
| 双层变量模型 | `{{env_var}}` 环境变量 + `${func(args)}` 动态函数职责分离 |
| 性能数据模型 | 执行生命周期走**统一 10 态模型**（与接口 / Web 同状态机，v1.5 对齐 05 §2.2，旧表述「8 态」作废）、场景级执行互斥、heartbeat 僵尸检测、配置快照冻结、压力机自监控、SLA abort_on_breach 熔断——直接当需求清单建模 |
| 主备定位器 + 健康度 | UI 元素主定位 + backup_locators + 健康度四态 + 使用统计 |
| 用例评审四态机 | 待评审/评审中/通过/拒绝 + 评审模板 + AI 评审员角色 |
| Excel 导入导出 | 企业迁移刚需，Celery 异步导入 |
| 通知子系统 | Fernet 加密 + 主备渠道容灾 + 告警 episode 状态机（其全平台工程质量最高的部分之一） |

**防**：视觉模式声称支持实则零实现、裸 daemon 线程执行进程重启即丢、`--no-sandbox`/CDP 绑 0.0.0.0、API Key 明文入库 + 日志打印、跨用户消耗他人 Key、`{{var}}` 失败静默回退。**GPL-3.0 纪律：严禁复制/改写其任何代码入我方库。**

---

## 4. 三大重点域逐域建议

### 4.0 执行架构：双执行模式 × 双执行环境（v1.3 新增，v1.4 扩展）

执行架构有两个正交维度：**执行模式**（Script / Agent）与**执行环境**（平台执行器 / 企业 CI）。所有组合共用同一治理面（TestRun 状态机、证据链、副作用分级、审计）：

```
                 Test Case（统一用例模型）
                     │
          ┌──────────┴──────────┐
          │                     │
       Script Mode          Agent Mode
          │                     │
          ▼                     ▼
    固定脚本执行              Skill（版本化技能包）
  （版本化脚本 + 数据驱动）          ↓
          │                Agent（受限推理节点）
          ▼                     ↓
   确定性结果 + 证据      Tool / Browser（经 Tool Router + Policy Gate）
          │                     ↓
          ▼                  动态执行（全程轨迹留存）
  回归 / 门禁 / 发布证据          ↓
                     轨迹一键转脚本草稿（人工确认入库 → 回到 Script Mode）
```

| 维度 | Script Mode | Agent Mode |
| --- | --- | --- |
| 定位 | 回归主力、质量门禁、发布证据 | 探索性测试、脆弱流程辅助执行、脚本生成前驱 |
| 输入 | 版本化脚本 + 数据驱动 | 用例意图 + Skill（manifest 声明约束） |
| 执行 | 确定性引擎（接口执行器 / Playwright / Locust-k6） | Agent 动态编排步骤，逐步调用 Tool / 浏览器 |
| 治理 | 标准 TestRun 治理 | 同一治理面 + **每个工具动作**过 Tool Router + Policy Gate |
| 结果 | `execution_source=script`，进门禁 | `execution_source=agent`，**默认不进门禁** |
| 可重复性 | 可重放 | 不保证；每步动作 / 截图 / 工具调用记录全量留存 |
| 价值闭环 | — | **执行轨迹一键转为 Script Mode 脚本草稿**（人工确认后入库） |

**执行环境维度（v1.4 新增）**：企业普遍复用已有 CI/CD（Jenkins 等），全部执行跑平台本地 Docker 既不现实也不科学——平台执行器只承接**需要平台能力**的场景（平台托管用例、Playwright 证据链、Agent Mode、Locust/k6 压测编排）；存量系统已在自家 Jenkins 部署测试 pipeline 的，走**引用接入**。执行环境是**一等注册对象**，用例/计划执行时绑定具体环境：

| 组合 | 支持与形态 |
| --- | --- |
| Script Mode × 平台执行器（本地容器） | 平台托管脚本/用例，容器化确定性执行（接口执行器 / Playwright / Locust-k6） |
| Script Mode × 企业 CI（Jenkins 等） | **引用型用例（Mock 型）**：不迁移脚本——用例实体 = 外部 Job 引用 + 触发参数 + 结果采集配置（报告路径/格式）+ 门禁阈值映射；平台职责 = 幂等触发 → 轮询/webhook 双通道 → 日志分片拉取 → 报告解析归一化 → 统一分诊与门禁 |
| Agent Mode × 平台执行器 | 上图 Skill → Agent → Tool/浏览器动态执行 |
| Agent Mode × 企业 CI | **一期不支持**（Agent 依赖平台侧工具与浏览器控制面） |

**引用型用例（Mock 型）设计要点**：

1. 用例不含执行脚本，仅声明：目标执行环境与 Job、触发参数（过 Job 参数 Schema 校验）、产物/报告位置与格式、超时与门禁映射；
2. 执行链路走 Connector Contract：幂等键触发、持久轮询 + webhook 回调兜底、日志分片拉取（log chunking）、报告适配器（JUnit/Allure/Playwright/Pytest）解析入统一 TestRun 模型；
3. 结果与平台原生执行**同权**进入失败聚类、质量门禁与发布证据——对下游（门禁/Release/证据链）完全透明，标记 `execution_source=external_ci`；
4. **执行环境注册中心**（M0 骨架）：注册 Jenkins 等实例（凭证只存引用 + 健康检查 + Job 发现 + 参数 Schema 读取）——直接采纳研究包 Jenkins Job Contract：Job Registry / 参数 Schema / Trigger / 队列与构建状态 / Artifact manifest / 报告适配器 / 日志分片 / Cancel / 回调与轮询兜底；
5. 组织/项目级环境绑定 + 使用配额（防止平台把企业 CI 打爆，也防外部环境滥用平台调度）。

**设计边界（与产品原则 2 的关系）**：

1. Agent 的动态性**限于单用例内的步骤执行层**；流程编排、重试、幂等、取消与权限仍由治理面管理——「模型不决定业务控制流」原则不变，Agent Mode 是「受限推理节点」向执行层的延伸；
2. Skill manifest 强制声明：allowedTools 白名单、max_steps、单步 / 总超时、sideEffectLevel 上限（Agent Mode 内默认 ≤ L1，L2+ 动作单独走审批中心）；
3. 浏览器与工具调用全部经 Tool Router（输入 schema 校验 + 租户 / 角色校验）+ Policy Gate（借鉴 TestHub MCP 两段式与 WHartTest agent-browser 的经验）；
4. **Agent Mode 结果不作为门禁与发布证据输入**（可重复性不足——TestHub BrowserUse 的定位结论：真实可用但不能当回归主力）；证据照常入证据链；固化为脚本后按 Script Mode 规则进门禁；
5. 终止与开关：模块级 kill switch + 单任务终止，**终止信号必须服务端持久化**（TestHub 单进程内存停止信号在多 worker 下失效的教训）；
6. 试点顺序：M2 Web 域先行（探索性场景），M4 扩展 API 域意图编排与「轨迹 → 脚本」完整闭环；
7. **执行环境边界**：Agent Mode 一期仅支持平台执行环境；企业 CI 环境仅承载 Script Mode（引用型用例）；压测（Locust/k6）一期仅平台执行环境（压测引擎需要平台侧资源治理与 kill switch）。

### 4.1 接口自动化（第一优先 · MVP 主力）

1. **资产入口以 OpenAPI/Swagger 为主**：导入格式只做 OpenAPI + Postman + curl 三种，其余按需求渐进。
2. **AI 生成走两步式**：生成（默认不落库）→ 人工审阅 → 保存，自动打标；生成必须带「采纳率 / 人工修改幅度」埋点——三个竞品全都拿不出 AI 质量数据，我方不重蹈。
3. **双层变量模型**：`{{env}}` + `${func(args)}` 分离；**变量解析失败必须报错中止**，杜绝静默保留原文的「假绿」。
4. **执行引擎自建且达标**：真任务队列（Celery/Arq）+ 重试/熔断/fail-fast 策略 + 心跳与超时治理；断言至少六类（status_code / response_time / contains / json_path / header / equals）。
5. **AI 失败自愈按「建议-确认-快照-回滚」四段式**：8 类失败原因枚举 + confidence 门控；MVP 只做「建议」，不做自动应用。
6. **Mock Server 可选**：注意鉴权（竞品的 Mock 匿名端点是硬伤），mock 用例在集合回归中不得直接判 passed。

### 4.2 Web 自动化（第二优先）

1. **引擎 Playwright，执行器独立进程/容器**；MVP 单执行器 + 抽象接口，规模化后再上 slot 租约集群（WHartTest Actuator 模式）。
2. **执行证据链是生命线**：截图/视频/Trace 三件套 + 失败 AI 归因（原因分类 + 修复建议）。
3. **定位器工程**：主备定位 + 健康度 + 使用统计；AI 自愈**只做建议**，落地必须 diff 预览 → 人工确认 → 快照 → 可回滚。
4. **脚本沙箱必须容器级隔离**：用户/AI 生成脚本一律独立容器执行，限制网络出口与文件系统（FullScopeTest 的 AST 黑名单 + subprocess「伪沙箱」是 RCE 教训）。
5. **录制不做服务端 codegen**：竞品在服务器跑 `playwright codegen` 无 GUI 环境不可用；优先客户端录制/插件方案。
6. **视觉回归后置（M3+）**：只借鉴「人工批准基准 + 历史趋势线」流程，算法另行选型；基准创建不得默认 active 且可原地覆盖（防洗白）。

### 4.3 性能自动化（第三优先 · 设计参考最丰富）

竞品现状：WHartTest 零能力；FullScopeTest 闭环可用但资源模型粗糙（单进程 Locust + CSV 2s 轮询，宣称的分布式与实时告警未实现）；TestHub 未发版但数据模型三者最佳。

1. **不自研引擎，包装 Locust 或 k6**：平台价值在场景管理、编排、安全护栏、基线对比、门禁联动；k6 + Grafana 生态亦可评估直接集成。
2. **照 TestHub 模型建数据层**（照建模、不抄代码）：
   - **统一 10 态执行模型**（v1.5 对齐 05 §2.2，旧表述「8 态」作废）+ 终态 / 活跃态集合常量；
   - **场景级执行互斥**（同场景不允许并发压测）；
   - **heartbeat 僵尸执行检测** + process_pid/worker_host；
   - 执行时 load/steps **快照冻结**（保证基线对比配置一致）；
   - **压力机自监控**（CPU/内存时序采样，区分「目标慢」vs「压力机饱和」）；
   - SLA 阈值 + **abort_on_breach 熔断**；验收判定（max_p95_rt/min_tps/max_error_rate）与 SLA 过程质量分离。
3. **必须补上所有竞品都缺的两道闸**：
   - ① 压测**目标环境白名单**（只允许打指定测试环境）；
   - ② 高危配置（大并发/长时长）**人工审批** + 全局并发预算 + 一键停止 kill switch。
4. **安全护栏照搬 FullScopeTest 四件套思路**：SSRF 校验 + 参数上限 + 脚本检查 + 进程硬超时；stop 失败时状态不得与真实进程脱节。
5. **压测任务严禁套用功能测试的自动重试**（语义错误）。
6. **结果接入质量门禁**：max_p95_ms / max_error_rate 作为门禁阈值，与接口/Web 同一套门禁模型。

---

## 5. Release 模块与全局 Copilot（v1.1 新增平台模块）

> 依据平台负责人 2026-08-23 补充需求：基于已完成的 Jira 项目创建 release task；调用企业已有 Release 系统准备 release item；提供通用 Copilot AI 聊天窗口并内置通用 skills。

### 5.1 Release 模块（发布编排层）

**定位**：不重建发布系统。企业已有 Release 系统，平台做的是「**质量证据 → 发布决策**」的编排层：从 Jira 圈定发布范围、汇聚测试质量证据、生成 Release Task、调用 Release 系统准备 item。

**核心流程**：

```
Jira 项目 / 版本（Resolved/Done 的 issue，按 fixVersion 或 JQL 圈定）
   → 发布范围快照（冻结当时 issue 清单，防事后漂移）
   → 汇聚质量证据（测试计划结果 · 质量门禁结论 · 性能基线对比 · 未关闭缺陷清单）
   → 发布就绪度门禁（Readiness Gate，红黄绿分区）
   → AI 生成 Release Notes / 发布检查单（草稿 → 人工确认）
   → 创建 Release Task
   → 调用企业 Release 系统准备 release item（预览 → 人工确认 → 审计）
   → Release 系统状态回传（webhook）→ Release Task 生命周期跟踪
```

**关键设计点**：

1. **范围从 Jira 来，单向读取**：与裁定表一致，不做双向全量同步；Release Task 记录**范围快照**（借鉴 TestHub 性能模块的「配置快照冻结」——避免 Jira 后续变动导致发布范围漂移、无法追溯）。
2. **质量证据汇聚是本模块的独有价值**：该版本关联的测试计划执行结果、门禁评估、性能基线对比、未关闭缺陷（区分 blocker / 非 blocker）自动挂接到 Release Task——这是测试平台对发布流程别处拿不到的输入。
3. **Readiness Gate 复用质量门禁模型**：阈值示例——回归通过率、门禁结论、blocker 缺陷数 = 0、性能劣化在容忍度内；红黄绿分区呈现（借鉴 TestHub LLM Judge 的门禁分区设计）；不达标时允许「带豁免说明发布」，但豁免必须留痕可审计。
4. **Release 系统作为集成中心的新连接器**：与 Jira / GitHub 同级——专用 API Token、出站调用日志、失败重试与告警。**创建 release item 属高危操作**：preview→confirm 两段式 + 人工确认 + 审计；发布执行权永远留在 Release 系统 / 流水线，平台只「准备」不「执行」。
5. **AI 只做草稿**：release notes 汇总（issue 变更分类归纳）、发布检查单生成、就绪度异常解读；一律「草稿 → 人工编辑确认」后才允许进入推送流程。
6. **Release Task 状态机**：草稿 / 待确认 / 已提交（item 已创建）/ 已就绪 / 已取消 / 失败可重试；状态迁移全审计。

### 5.2 全局 Copilot（AI 聊天窗口 + 内置 Skills）

**定位**：面向全员的统一 AI 入口，降低平台使用门槛；同时是平台能力的自然语言界面（NL → 查询与操作）。

**架构基线**（均有竞品源码级参考）：

- Agent 编排采用 LangGraph `create_agent()` 式循环 + 中间件三件套（上下文压缩 Summarization / HITL 审批 / 工具自动拒止黑名单）——WHartTest 已验证形态；
- 模型接入走「按角色多模型配置中心 + 测试连接」——TestHub 已验证形态，密钥服务端管理；
- 危险操作 preview→confirm + 可选人工审批 + 签名令牌——TestHub MCP 模式，并补齐其三处缺口：四眼原则（发起人不可自批）、consume 加行锁、审批窗口独立 TTL。

**必须做对的六件事（FullScopeTest Copilot 的反面清单）**：

| # | 要求 | 反面案例 |
| --- | --- | --- |
| 1 | 所有对话与工具调用走 AIInvocationLog，无旁路 | 其 Copilot 主路径裸 `requests.post` 绕过日志体系，不计成本不进统计 |
| 2 | kill switch 必须真正生效 | 其 `AI_ASSISTANT_ENABLED` 开关被采集但从不检查 |
| 3 | 密钥服务端管理，禁 BYOK localStorage 明文 | 其 BYOK api_key 明文存前端并随请求体回传 |
| 4 | 会话历史服务端持久化 | 其对话历史仅存前端内存，刷新即丢 |
| 5 | 权限感知 + 工具层强制租户校验 | 防止聊天入口成为越权通道（上下文注入参考 WHartTest v1.2.0 模式） |
| 6 | 写操作工具一律两段式确认，默认只读起步 | 其写库工具无人工确认直接 INSERT+commit |

**Skills 体系**：

- **形态**：**版本化 Skill 包**（v1.2 融合研究包 manifest 模型 + WHartTest 分发形态）——manifest 含输入/输出 JSON Schema、allowedActions 白名单、sideEffectLevel、modelPolicy（成本上限 / 数据分级 / 供应商白名单）、超时重试、沙箱策略、**金标准测试集**与发布审批人；三级发布：个人（项目内可用）→ 团队（Owner 审核）→ 组织（管理员 + 安全审核）。先做平台原生工具 + 低权限；技能沙箱隔离、权限最小化、可配置「始终拒绝」黑名单；安全模型验证后再开放自定义技能包扩展（高权限技能商店的教训：安全模型未解决前是负资产）。
- **内置通用 skills（首批建议，全部只读起步）**：
  - 测试域：用例生成 / 评审助手、失败归因解读、测试报告摘要、flaky 用例分析；
  - 集成域：Jira 查询（issue / 版本 / 缺陷）、GitHub PR / Check Run 查询、API 文档（OpenAPI）解读；
  - 工具域：SQL 只读查询（白名单库）、正则 / JSONPath / cron 编写、测试数据生成；
  - 平台域：环境与配置查询、release notes 草稿生成。
- **MCP 双向生态位**（WHartTest / TestHub 已验证）：平台作为 MCP server 对外暴露能力给 IDE / 内部 Agent；Copilot 同时是 MCP client，可接企业内其他 MCP 服务——Copilot 的能力上限是「企业工具生态」而不是单个对话框。
- **成本归属**：Copilot 对话计入部门 AI Token 配额（M0 底座），按技能维度统计采纳率。
- **双消费者**：Skill 同时供 Copilot（对话调用）与 Agent Mode（动态执行，见 4.0）消费，manifest 与权限模型一致。

**分期**：M3 最小版（只读 Q&A + 查询类技能，跑通日志 / 成本 / 权限三件事）→ M4 完整版（写操作 + 审批 + 技能框架 + NL2Script）。

---

## 6. 平台功能裁定表（对需求草稿问号点的逐条决策）

| 草稿条目 | 裁定 | 理由与要点 |
| --- | --- | --- |
| 质量门禁？ | **做，关键钩子** | 三阈值模型对齐三域；必须保证门禁结论写进 CI exit code（竞品 FAIL 仍绿是反面教材）；上线初期「仅报告」模式，稳定后显式开启阻断 |
| Token 管理？ | **做（CI 集成定位）** | read/write/execute/delete 四操作 + project_ids 白名单 + 有效期 + 可吊销；哈希用 bcrypt/argon2；last_used_at 异步更新避免高频写库 |
| 健康监控放 AIOps？ | **基本同意** | 基础设施监控交企业监控体系；但压力机自监控（归因判别）与任务状态治理（心跳/僵尸回收/超时熔断）留在平台内——三家全缺，必须反向做对 |
| Webhook 调试统一管理？ | **正确，建「集成中心」** | 入站 webhook 接收 + 出站通知渠道 + 调试（测试事件/投递历史/失败重试）一处管理；强制 HMAC 验签无例外、绑定仓库归属校验、记录投递日志 |
| 限流放 gateway？ | **同意，但留两个业务配额在平台内** | HTTP 限流归网关；① 部门级 AI Token 预算（挂 AI 调用日志）；② 执行资源配额（UI slot 数、压测并发预算） |
| GitHub 集成（Check Run 回写 PR） | **做** | 借 FullScopeTest 三段式设计（create→update→complete），修复其断点：PR 事件 changed_files 必须传值、同步失败重试、仓库归属校验 |
| Jira 集成（自动创建/同步缺陷） | **做，单向为主** | 失败用例一键建 Jira 缺陷（附证据+复现步骤）、用例关联 story、计划关联 fixVersion；**不做双向全量同步**（复杂度高一个量级） |
| 定时任务跑用例 + 定制报告模板 | **做** | APScheduler/Celery Beat + 通知；报告模板后置 |
| 通知设置（渠道/事件类型/webhook） | **做，纳入集成中心** | 参考 TestHub 通知子系统（加密 + 主备容灾 + episode 状态机）；飞书/钉钉/企微按需 |
| 全局 Copilot（聊天窗口 + 内置 Skills） | **做，一等模块**（M3 最小版 / M4 完整版） | 竞品实现浅且多处硬伤，其教训反而是现成规格：全量日志无旁路、kill switch、服务端密钥、权限感知、写操作两段式（详见 5.2） |
| Release 模块（基于已完成 Jira 项目创建 release task） | **做**（M3 v1 / M4 深化） | 「质量证据 → 发布决策」编排层，测试平台对发布流程的独有价值，详见 5.1 |
| 对接企业 Release 系统（准备 release item） | **做，集成中心新连接器** | 与 Jira/GitHub 同级：专用 Token + 调用日志 + 失败重试；高危操作预览+确认+审计；平台只准备 item、不触发实际发布 |
| 审计日志 | **做，M0 就有** | 借 WHartTest 七字段 + @audit_action 声明式 DX；修复竞品缺陷：失败操作也要审计、查询必须带租户过滤 |
| 系统设置（分页/语言/外观/安全） | **裁剪** | 外观/i18n 砍；安全设置保留；限流归网关（见上） |
| 测试用例 Excel 导入导出 | **做** | 企业迁移刚需；用例模板 + Celery 异步导入 |
| 项目管理 / 版本管理（TestHub 草稿） | **不自建，Jira 只读同步** | 项目/版本/成员从 Jira 同步，测试计划挂 Jira fixVersion；缺陷管理、文档中心同样砍掉（vs Jira/Confluence 完全重叠） |
| 测试计划（项目/版本/用例/报告） | **做（测试域内）** | 只建测试域闭环：用例库 + 评审 + 计划 + 执行 + 报告；用例评审四态机 + AI 评审员可借鉴 |
| 语义去重 | **后置（M4+）** | 竞品为孤儿链路；中文效果需自测；如做需向量缓存 + 异步化（竞品 O(n²) 同步阻塞请求线程） |
| 双执行模式（固定脚本 / Skills+Agent 动态执行） | **做**（M2 试点 / M4 完整） | Script Mode = 回归与门禁主力；Agent Mode = 探索与脚本生成前驱，受 Skill manifest + Policy Gate 约束、结果不进门禁、轨迹可固化回脚本；详见 4.0 |
| 执行环境自定义（平台本地 Docker / 企业 Jenkins 等 CI） | **做**（M0 注册中心 / M1 引用型用例 v1） | 企业普遍复用已有 CI/CD，平台执行器只承接需要平台能力的场景；引用型用例（Mock 型）让存量 pipeline 零迁移接入统一分诊与门禁；详见 4.0 执行环境维度 |

---

## 7. 多租户与平台底座（1000 人内部场景）

1. **租户模型**：组织 = 部门/事业部；**砍掉计费、白标、支付**（内部场景无意义，竞品这三块也全是未接线死代码）；保留「配额」概念（AI Token 预算、执行资源）。
2. **隔离在中间件/ORM 层强制**：租户上下文 + row-level `organization_id` + 强制 queryset 过滤；**不学 FullScopeTest 的「上下文注入 + 端点手动过滤」两段式**（其审计查询至今无组织过滤）。上线前跑「双租户互访越权」回归测试集。
3. **SSO（OIDC）/ LDAP 第一天就有**：企业内部平台准入门槛；三家竞品在此全不合格（明文 Key、默认弱口令 admin/admin123、Key 明文入库）。
4. **AI 可观测底座第一天就建**：AIInvocationLog 全量日志（真实 usage 非估算、按部门归集成本、prompt/response 落库带脱敏选项）+ 基础看板；**所有 AI 调用无旁路**（竞品 Copilot 绕过日志是教训）。
5. **统一角色模型**：owner / admin / tester / viewer 一套词汇到底（竞品两套 RBAC 并存是混乱之源）。
6. **任务执行状态治理**：队列 + 心跳 + 僵尸回收 + 超时熔断（三家全缺，任务永久卡 running 是通病）。
7. **制品存储与保留策略**：截图/视频/Trace 入对象存储（MinIO/S3）+ 生命周期规则。
8. **Copilot / Agent 是新的越权面**：对话上下文注入用户的项目/租户/角色（WHartTest v1.2.0 已验证模式），但**工具层强制租户与角色校验，不依赖 prompt 约束**——防止聊天入口成为绕过权限的通道。
9. **副作用五级分级（L0–L4）**：L0 只读 / L1 平台内草稿 / L2 外部系统非生产写 / L3 触发正式测试或变更审批 / L4 生产发布·邮件·删除。裁决规则：L0 默认允许、L1 允许可追溯、L2/L3 必须审批、L4 禁止或仅生成草稿；所有工具/技能/动作声明 sideEffectLevel，Policy Gate 按级输出 ALLOW/DENY/REQUIRE_APPROVAL/REQUIRE_REAUTH。
10. **持久工作流执行模型**：TestRun 统一状态机以 [05-业务建模](03_problem_modeling/problem_model.md) §2.2 为唯一事实源（v1.5 对齐：PENDING 起点 + **10 态全集** `PENDING→VALIDATING→RUNNING→{WAITING_EXTERNAL / WAITING_APPROVAL / STOPPING}→终态 {SUCCEEDED / FAILED / CANCELLED / TIMEOUT}`；本节旧表述「DRAFT 起点 / 8 态」作废），每个步骤声明 type/timeout/retry/idempotency_key/side_effect/compensation/approval_policy/evidence_requirements——三域执行（接口 / Web / 性能）走同一状态机（TestHub 原「性能 8 态」已合并入统一模型）；**故障重启不得重复副作用**（技术 Gate 硬要求）。
11. **Evidence 一等对象**：`claim → evidence_link → source_object(连接器/资源/版本/时间戳)`——把执行证据链从 UI 域（截图/视频/Trace）升级为全域：AI 的一切关键结论（归因、聚类、门禁解读、release notes 字段）一律挂证据引用；核心指标：证据覆盖率 ≥ 95%、无据结论率 < 2%。
12. **模型路由与数据分类**：数据四分级（Public/Internal/Confidential/Restricted）；模型路由声明可处理数据等级、成本上限、供应商白名单与 fallback；Confidential 禁缓存、Restricted 仅本地模型或禁止处理；prompt 版本必填、敏感正文不落普通日志。
13. **技术底座选型注记（v1.2）**：执行编排 POC Temporal（长审批/轮询/中断恢复，「重启不重复副作用」表达力强），保底方案 Celery + 自建状态机 + 幂等键纪律；RAG 向量层 MVP 用 PostgreSQL + pgvector 起步（内部规模够用、少一个组件），Qdrant+BM25+Reranker 混合检索保留为演进方向——裁定细节见 [market_research.md](01_market_research/market_research.md) 第 4 节。

---

## 8. 分期路线图

| 阶段 | 周期 | 内容 | 关键验收点 |
| --- | --- | --- | --- |
| **M0 基座** | 约 1–2 月 | 多租户 + SSO + RBAC；AI 调用日志与 Token 计量；集成中心骨架（API Token + GitHub webhook 接收）；队列化 TestRun 模型；执行环境注册中心（Jenkins 实例注册 + 健康检查 + Job 发现 + 参数 Schema 读取） | 越权回归测试集通过；AI 调用无旁路；任务无永久 running；注册 CI 实例健康检查与 Job 发现可用 |
| **M1 接口自动化** | — | OpenAPI/Postman 导入；用例库（关联 Jira story）；执行引擎 + 六类断言；报告；定时回归；Swagger→AI 生成（两步式+人工确认）；失败聚类（run 级）+ AI 归因（仅建议）；质量门禁 v1（仅报告）；执行环境抽象（TestRun 与环境解耦）+ **引用型用例 v1（绑定 Jenkins Job：幂等触发 + JUnit 采集 + 统一分诊）** | 生成采纳率/修改幅度有数据；变量解析失败必报错；报告归一化解析准确率 ≥ 98%；引用用例重放不重复执行外部 Job |
| **M2 Web 自动化** | — | Playwright 容器化执行器；证据链三件套 + AI 归因；定位器主备 + 自愈建议（diff+确认+回滚）；GitHub Check Run 回写；Jira 一键建缺陷；存量 CI 接入完善（引用型用例多格式适配器：JUnit/Allure/Playwright/Pytest + 日志分片 + webhook 回调）；**Agent Mode v1 试点（Skill+Agent+浏览器探索执行，不入门禁）** | 门禁从「仅报告」切「阻断」；脚本沙箱渗透测试通过；CI 存量报告解析准确率 ≥ 98%；Agent 任务终止信号持久化验证（多 worker 可停） |
| **M3 性能自动化 + Release v1 + Copilot 最小版** | — | 性能：Locust/k6 包装；TestHub 式数据模型；环境白名单 + 审批两道闸；基线对比 + 劣化阈值；接入质量门禁。Release v1：Jira 版本圈定 + 质量证据汇聚 + Readiness Gate + 调用 Release 系统准备 item。Copilot 最小版：只读技能 + 全量日志 + 权限感知 | kill switch 演练通过；压力机自监控可区分目标慢/压力机饱和；Release 推送全链路可审计；Copilot 越权测试集通过 |
| **M4 AI 深化 + Release/Copilot 完整版** | — | Prompt 版本化 + 加权 A/B；LLM Judge 评生成质量；RAG（**Confluence/Jira 作为知识源**）；NL2Script；MCP 对外暴露平台能力给 IDE Agent；Release 深化（AI release notes / 发布检查单）；Copilot 完整版（写操作两段式 + 审批 + 技能框架 + 技能包沙箱）；**Agent Mode 完整版（轨迹→脚本固化闭环 + API 域意图编排）** | A/B 统计可回算；Judge 与人工评定一致性达标；Copilot 写操作全程可回滚可审计；轨迹转脚本采纳率有数据 |

**依赖关系**：M1 依赖 M0；M2/M3 可并行（不同子团队）；Release v1 依赖 M2 的 Jira 集成；Copilot 最小版只依赖 M0 的 AI 日志底座，可提前到 M2；M4 各项可穿插前置（如 Prompt 版本化可提前到 M1）。

**验收采用 Gate 制**（v1.2 借鉴研究包）：每阶段设「技术闭环 Gate」（故障重启不重复副作用、AI 结论全量挂证据引用、越权测试全阻断）与「业务价值 Gate」（测试分析中位耗时下降 ≥ 50%、关键字段首次接受率 ≥ 80%、外部误写 0 次）；**北极星指标采用「每周被接受且产生可验证结果的受控测试工作流数量」**，不以对话量 / Token 数 / 生成字数衡量价值。

---

## 9. 必须反向做对的安全清单（三家踩过的坑）

1. 用户/AI 生成脚本只在容器沙箱执行，禁止 `node -e` / 裸 subprocess（FullScopeTest RCE 教训）。
2. Mock 端点、SSE 端点、webhook 全部鉴权；禁止 Mock 匿名可访问 + CORS 回显任意 Origin。
3. webhook 强制 HMAC 验签，无「SECRET 为空跳过 / GET 跳过」例外分支；每租户独立密钥。
4. 密钥/Token 加密存储，明文只显示一次；日志禁打印 Key 片段；BYOK 场景禁 localStorage 明文。
5. TLS 校验默认开启（竞品普遍 `verify=False`）。
6. SQL 类工具只读 + 白名单 + 全局 kill switch。
7. AI 一切写操作（改用例/改定位器/建缺陷/自愈应用）：**diff 预览 → 人工确认 → 快照 → 可回滚**；快照失败即中止（fail-close）。
8. 压测：目标环境白名单 + 高危审批 + 全局并发预算 + 一键停止。
9. 默认账号强制改密；上传端点鉴权 + 大小/类型校验；`ALLOWED_HOSTS` 不用通配符。
10. 数据保留策略：截图/视频/Trace/日志定义生命周期。
11. Release 类高危动作：平台只「准备」不「执行」发布；对 Release 系统的调用一律预览 → 人工确认 → 审计；AI 生成的 release notes / 检查单只是草稿，禁止自动推送。
12. 审批绑定参数哈希（anti-TOCTOU）：Preview 与 Execute 的参数生成哈希、审批绑定该哈希，**参数变化则审批失效**；审批后执行前重新校验权限；审批界面展示动作 / 目标资源 / 前后 diff / 数据来源 / 模型与 Skill 版本 / 风险等级 / 成本估计 / 回滚能力 / 参数哈希。
13. Prompt Injection 防护：外部系统内容（Jira 描述 / PR 评论 / Confluence / 测试日志）标记为不可信数据，不视为系统指令；System/Policy/Skill/User/Document 分层提示；工具参数由结构化对象生成而非文档指令；高风险工具不由模型直接执行；建立恶意内容注入测试集。
14. 外部写操作幂等与补偿：幂等键 + external request id + 响应快照；可补偿动作必须定义 compensation（如 CI Job cancel）；重试不得造成重复触发 / 重复写入。
15. Agent Mode 动态执行约束：Skill manifest 声明 allowedTools / max_steps / 超时 / 副作用上限；每个工具动作过 Policy Gate，L2+ 动作单独审批；终止信号服务端持久化；结果标记 `execution_source=agent` 且不进门禁（详见 4.0）。
16. 外部执行环境安全：CI 凭证只存引用（运行时从 Vault 取）；触发前参数过 Job 契约 Schema 校验，不合规即拒绝；日志/报告拉取限速与大小上限；外部 Job 触发幂等（重放不重复执行）；egress 白名单限定已注册 CI 域；环境注册有管理员审批。

---

## 10. 明确不做清单

| 项 | 理由 |
| --- | --- |
| APP 自动化 | 三个竞品自己都只做管理不做执行，重资产，等真实需求 |
| 计费 / 白标 / 支付 | 内部场景无商业化，竞品实现也全是死代码 |
| 11 种 API 导入格式 | 长尾维护负担，只做 OpenAPI/Postman/curl |
| 在线文档编辑（ONLYOFFICE） | 已有 Confluence |
| 自研压测引擎 | 包装 Locust/k6 即可，Grafana 生态现成 |
| 无人审批的 AI 自动改写/自动应用 | 企业信任红线，一律 HITL |
| 缺陷管理 / 文档中心 / 项目版本管理自建 | 与 Jira/Confluence 完全重叠 |
| Skills 高权限技能商店 | 安全模型未解决前是负资产 |
| 双向全量 Jira 同步 | 复杂度高一个量级，单向创建 + 链接回写足够 |
| i18n / 外观主题 | 非核心，后置 |

---

## 11. 证据纪律与引用

- 本文档所有竞品结论的证据强度与来源，见各竞品目录的 `03-证据表.md` 与 `modules/00-共享证据基线.md`；
- 源码级修正（效力最高）：FullScopeTest 的 C1–C12 修正表；
- **TestHub 为 GPL-3.0：本文档所有「借鉴」均指机制与数据建模层面，严禁复制/改写其源码**；
- 三家竞品的 AI 能力宣称（生成采纳率、归因准确率、评审评分）均无量化数据支撑，涉及其 AI 效果的决策需部署实测后复核；
- 我方现状未盘点（各竞品 `04-能力对比.md` 的空白列），建议补充后复核本文档优先级。

**交叉引用**：

- competitors/wharttest/（源仓库 opensource-product-analysis：competitors/wharttest/） · 重点看 `06-决策建议.md`、`modules/04-接口自动化测试.md`、`modules/05-UI自动化测试.md`、`modules/06-Agent对话与MCP工具调用.md`、`modules/07-知识库与RAG.md`、`modules/08-Skills技能库.md`
- competitors/fullscopetest/（源仓库 opensource-product-analysis：competitors/fullscopetest/） · 重点看 `modules/00-共享证据基线.md`（C1–C12 修正表）、`modules/01-AI-Copilot全局助手.md`、`modules/03-智能错误分析与自愈.md`、`modules/09-性能压测与APP测试.md`、`modules/10-CICD集成与QualityGate.md`、`modules/12-组织多租户计费与白标.md`
- competitors/testhub/（源仓库 opensource-product-analysis：competitors/testhub/） · 重点看 `modules/02-AI智能测试BrowserUse.md`、`modules/03-MCP工具调用与危险操作审批.md`、`modules/04-LLMJudge质量评测引擎.md`、`modules/05-多模型统一配置中心.md`、`modules/11-性能测试模块.md`
- references/enterprise_ai_dev_assistant_research_2026-07-28/（源仓库 opensource-product-analysis：references/enterprise_ai_dev_assistant_research_2026-07-28/） · 本平台的前置整体研究（企业研发 AI 助手，2026-07-28 快照）；AI 自动化测试相关重点：`docs/03_产品战略与PRD.md`（模块 C 自动化测试中心 + Skill 模型）、`docs/04_系统架构设计.md`（副作用分级 / 工作流 / Connector / Evidence / Sandbox 规格）、`docs/07_安全治理与评测.md`（HITL / Prompt Injection 防护 / 评测体系）、`examples/workflow-test-center.yaml`、`diagrams/02_test_center_workflow.mmd`
- [market_research.md](01_market_research/market_research.md)（01_market_research/ · Stage 3） · 研究包到本平台的逐项借鉴映射（17 项机制）、技术选型修订与不采纳清单
- 本目录各阶段文档链（按开发流程图 Stage 顺序；**各文档最新版本以其文首版本头为唯一事实源**，本链不随下游升版回头改版本号）：[03-市场调研借鉴](01_market_research/market_research.md)（Stage 3）→ [04-竞品功能拆解索引](02_competitor_analysis/competitor_analysis.md)（Stage 4）→ [05-业务建模](03_problem_modeling/problem_model.md)（Stage 5：ER / 状态机 / IA / AI Schema）→ [06-核心交互链设计](04_interaction_design/interaction_flows.md)（Stage 6，已生成）→ [07-产品原型设计](05_prototype/prototype_spec.md)（Stage 7，占位待生成）→ [08-后端架构设计](06_architecture_design/architecture.md)（Stage 8，占位待生成）∥ [12-PRD](08_prd/prd.md)（Stage 12 终版收口位，当前为中期版，待吸收 05/06/07 后重生成 v2）

## 12. 变更日志

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1.0 | 2026-08-23 | 首版：基于三份竞品拆解（WHartTest / FullScopeTest / TestHub）与需求草稿，给出八章决策建议，含三大域逐域建议、平台功能裁定表（15 项决策）、分期路线图（M0–M4）、安全清单（16 条「必须反向做对」）、10 条明确不做清单 |
| v1.1 | 2026-08-23 | 新增第 5 章 Release 模块与全局 Copilot（平台模块扩展）；README 与研究包（2026-07-28）解耦：本文档为平台建设决策，研究包作为输入之一 |
| v1.2 | 2026-08-23 | 新增第 1 章产品原则六条（← 03 借鉴文档 3.1）；第 5.2 节 Skills 升级为版本化 Skill 包模型；第 7 章新增 7.9–7.13（副作用分级 / 持久工作流 / Evidence / 模型路由 / 技术选型注记）；第 8 章 M1/M2 补聚类与存量 CI 接入、新增 Gate 制验收与北极星指标；第 9 章补 9.12–9.14（参数哈希审批 / Prompt Injection / 幂等补偿） |
| v1.3 | 2026-08-23 | 新增 4.0 节执行架构（双执行模式：Script / Agent）；对齐 12-PRD v1.1（US-13 / FR-19 / A8）与 05 v1.0（ExecutionMode / 10 态统一）；旧 4.0 后移为 4.1，旧表述「DRAFT 起点」作废（改 PENDING）|
| v1.4 | 2026-08-23 | 执行架构扩展为「**双执行模式 × 双执行环境**」：平台执行器（本地 Docker）与企业 CI（Jenkins 等）并为一等执行环境，新增引用型用例（Mock 型）支持存量 pipeline 零迁移接入（← 03 借鉴文档第 2 节 Jenkins Job Contract）；对齐 12-PRD v1.2（US-14 / FR-18 / ExecutionEnvironment）；M0 执行环境注册中心采纳研究包集成契约规范 |
| v1.5 | 2026-08-24 | 全链路一致性复核修复（Stage 3→6 反向核查）：① 3 处旧表述作废（「8 态」→ 统一 10 态，对齐 05 v1.3 §2.2；「DRAFT 起点 / 8 态」→ PENDING 起点 / 10 态；「TestHub 性能 8 态」→ 已合并入统一模型）；② 元信息更新（v1.5 / 2026-08-24）；③ 本版不引入新功能，仅消歧与版本号对齐（下游 05 v1.3 / 12-PRD v1.5） |
