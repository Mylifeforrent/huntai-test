# Stage 6 · 核心交互链设计 · Agent Team 提示词

> - **用途**：在多 Agent 工具中执行开发流程图 Stage 6「核心交互链设计」，产出填入 [interaction_flows.md](interaction_flows.md) 骨架
> - **事实源**：[problem_model.md](../03_problem_modeling/problem_model.md)（页面清单 / 状态机 / 领域对象均以它为唯一事实源）
> - **配套**：Stage 7（产品原型）、Stage 8（后端架构）可按本模板同构改写，需要时再生成

---

## 提示词全文（复制使用）

```
请创建一个 Agent Team，对于每一个 Teammate 都使用 Sonnet 模型，一定要注意的是：在做任何改动之前，必须先获得计划的审批！

本阶段为开发流程图 Stage 6「核心交互链设计」。请严格基于仓库内既有文档完成交互链路设计，只允许进行调研和规范文档的生成，不要写任何的前后端代码！

【必读输入（每个 Teammate 开工前先完整阅读，禁止跳过）】
1. docs/03_problem_modeling/problem_model.md —— 唯一的建模事实源：§1 领域对象与 ER、§2 状态机全集、§4 信息架构与页面清单（20 个页面 + 三个关键页面结构约束）、§5 AI 输出 Schema；
2. docs/08_prd/prd.md —— 用户故事 / FR / 验收标准与边界场景（FR 编号已冻结，作为全链路溯源标识）；
3. docs/04_interaction_design/interaction_flows.md —— 本阶段骨架：四条链路定义与输出结构要求；
4. docs/README.md 第 1 章 —— 北极星闭环与产品原则。

【硬性收口纪律（违反任何一条即返工）】
- 页面流只能引用 05 §4 清单中的页面，不得新造页面；
- 状态迁移只能引用 05 §2 已定义的状态与状态机，不得新增未定义状态；
- 不得引入 05 / 12-PRD 之外的新功能、新对象、新字段；
- 发现上游文档缺口时，写入自己文档末尾的「缺口上报」小节（缺口描述 + 建议归属的上游文档），禁止自行发明补齐。

Agent Teams 的团队分工如下：

- Teammate 1：负责链路 C1「北极星质量闭环」——Confluence 需求 → AI 生成（两步式）→ 审阅入库 → 执行（双模式 Script/Agent × 双环境 平台执行器/外部 CI）→ 质量门禁 / GitHub Check Run → Jira 缺陷 → Release Task（Readiness Gate → 调用 Release 系统）→ 证据回流；对应 FR-05/13/14/15/18；

- Teammate 2：负责链路 C2「审批链」——动作发起 → 参数哈希生成与绑定 → 审批中心九要素卡片 → 审批人操作（同意 / 拒绝 / 参数变更致审批失效）→ 执行前复核（anti-TOCTOU）→ 执行留痕与补偿；对应 FR-04 与 README 9.12，必须覆盖四眼原则、行锁防双执行、审批独立 TTL 三项反向设计；

- Teammate 3：负责链路 C3「执行发起链」——模式选择（Script / Agent）→ 环境选择（平台执行器 / 外部 CI，含引用型用例按 Job Schema 动态生成的参数表单）→ TestRun 状态机全路径流转（PENDING→VALIDATING→RUNNING→WAITING_EXTERNAL→WAITING_APPROVAL→STOPPING→终态，含 TIMEOUT 僵尸回收）→ 结果与证据产出；对应 FR-08/18/19；

- Teammate 4：负责链路 C4「失败分诊链」——TestRun 完成 → 报告归一化 → 失败聚类（含阻塞判断与 confidence 展示、无法判断项）→ 人工审阅修正（修改留痕）→ 建 Jira 缺陷 / 自愈建议（diff → 审批 → 快照 → 回滚）→ 证据落库；对应 FR-06/07。

每个 Teammate 的输出要求：

1. 写入 docs/04_interaction_design/chains/ 目录下对应的 md 文件：c1_north_star_quality_loop.md / c2_approval_chain.md / c3_execution_kickoff.md / c4_failure_triage.md；
2. 每条链路文档必须包含以下六节，缺一不可：
   ① 触发者与前置条件（角色 / 权限 / 进入时的对象状态）；
   ② 页面流（表格：步骤 → 页面（必须引用 05 §4 的页面名称）→ 关键交互）；
   ③ 状态迁移（Mermaid sequenceDiagram 或 flowchart，状态名与 05 §2 完全一致，图中每个跳转标注触发条件）；
   ④ 分支与异常（取消 / 超时 / 降级 / 审批拒绝 / 参数失效 / 僵尸回收 / AI 降级横幅，逐项给出走向与用户可见反馈）；
   ⑤ 审批与副作用点（哪些动作触发 L2+ 审批，逐个标注 sideEffectLevel 与对应 ApprovalRequest 场景）；
   ⑥ 证据落点（各环节产生的 EvidenceObject / AuditEvent / Artifact，对应 05 §1 领域对象名）；
3. 文档头部标注：链路编号、覆盖的 FR、上游引用文档相对路径；文档末尾附「缺口上报」小节（无缺口则写「无」）。

Lead 的要求：

1. 一定不要下场写主题内容；
2. 你要等待所有的 Teammate 完成后，再输出汇总。汇总只做三件事：
   a. 一致性检查：核验四份文档的页面引用是否都在 05 §4 清单内、状态引用是否都在 05 §2 内、FR 溯源是否正确——存在 FAIL 先逐条列出，不要假装通过；
   b. 将 docs/04_interaction_design/interaction_flows.md 的头部状态从「占位待生成」更新为「已生成 v1.0」，并在其 §1 之后补一张四条链路的索引表（链路 → 文件路径 → 覆盖 FR）与建议阅读顺序；
   c. 输出执行摘要（≤300 字：四份文件路径 + 一致性检查结论 + 缺口上报汇总）。

收尾要求：

你需要在每个 Teammate 关闭以后，清空当前的 Team。
```
