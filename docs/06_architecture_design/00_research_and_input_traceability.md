# 研究与输入可追溯性

> - **Status: Draft**
> - **日期**：2026-08-26
> - **阶段**：Stage 6 · 系统架构设计 · 阶段二研究输入分册
> - **用途**：登记本阶段实际读取输入、官方技术结论、采用边界、冲突与缺失，供同目录架构分册及后续 POC/评审使用
> - **证据口径**：仓库事实来自本次实际读取并以相对路径和行号定位；LangGraph、Temporal、MCP 结论及官方链接由 Lead 事先核对，本次按授权直接消费，未进行网络访问或二次联网核验
> - **决策属性**：本文为 Draft 输入与建议，不把候选技术、POC 或上游冲突提升为已批准结论
> - **变更边界**：本文不修改、纠正或回写任何上游文档；需改变已冻结资产时，必须另走 `../13_changes/` 变更流程

## 0. 调研方法与限制

1. 对仓库内上游文档执行实际读取，提取可由当前仓库复核的对象、状态机、审批、安全、分期与技术选型事实。
2. 对 `docs/` 执行文件、图片和 HTTP 外链扫描；对 `docs/05_prototype/` 额外执行目录与 Git 跟踪状态核对。
3. 不访问网络。第 5 节只登记 Lead 已核对的官方链接与结论，不声称本次会话重新抓取或验证了网页内容。
4. 不读取仓库外 `opensource-product-analysis`、`competitor-src` 或其 `references/`、`competitors/` 内容；凡上游仅指向这些材料的结论，均标为“源仓库引用不可复核”。
5. 本文的“采用”只表示 Draft 架构采用边界；Temporal 与 MCP M4 均仍是条件 POC，不构成依赖、部署或产品承诺。

## 1. 实际读取输入清单

### 1.1 规则、阶段约定与总纲

| 输入 | 实际读取范围 | 本文消费点 |
| --- | --- | --- |
| `../../AGENTS.md` | 全文 | 目录职责、阶段输出、冻结资产与单文件变更边界；关键规则见 `../../AGENTS.md:13`、`../../AGENTS.md:17`、`../../AGENTS.md:35`、`../../AGENTS.md:61` |
| `../00_setup/README.md` | 全文 | Stage 0 输出约定 |
| `../00_setup/project_rules.md` | 全文 | 文档命名/目录、冻结资产变更红线；见 `../00_setup/project_rules.md:42`、`../00_setup/project_rules.md:52`、`../00_setup/project_rules.md:130` |
| `../README.md` | 全文 | 产品原则、双执行模式、审批治理、技术选型与 M0-M4 路线 |
| `README.md` | 全文 | Stage 6 目录职责与既有输出登记 |

### 1.2 上游产品、建模、交互与 PRD

| 输入 | 实际读取范围 | 本文消费点 |
| --- | --- | --- |
| `../01_market_research/README.md` | 全文 | 研究包本体仍在源仓库的事实 |
| `../01_market_research/market_research.md` | 全文 | 治理面/执行面、LangGraph 边界、Temporal 条件 POC、技术选型来源 |
| `../02_competitor_analysis/README.md` | 全文 | 竞品源码级拆解仍在源仓库的事实 |
| `../02_competitor_analysis/competitor_analysis.md` | 全文 | 审批反例、LangGraph/MCP 竞品索引及不可复核边界 |
| `../03_problem_modeling/README.md` | 全文 | `problem_model.md` 为唯一建模事实源的阶段声明 |
| `../03_problem_modeling/problem_model.md` | 全文 | 23 个对象、TestRun、ApprovalRequest、租户、门禁和审计不变量 |
| `../04_interaction_design/README.md` | 全文 | C1-C4 输出索引 |
| `../04_interaction_design/agent_team_prompt.md` | 全文 | 历史生成纪律与必读输入说明，仅作过程追溯，不作为最新事实源 |
| `../04_interaction_design/interaction_flows.md` | 全文 | C1-C4 范围与状态/页面收口纪律 |
| `../04_interaction_design/chains/c1_north_star_quality_loop.md` | 全文 | 端到端治理、Agent/外部 CI、门禁、Release 与证据链 |
| `../04_interaction_design/chains/c2_approval_chain.md` | 全文 | 四眼、`param_hash`、审批 TTL、行锁与审计链 |
| `../04_interaction_design/chains/c3_execution_kickoff.md` | 全文 | TestRun、外部 CI、Agent Mode 与恢复/幂等语义 |
| `../04_interaction_design/chains/c4_failure_triage.md` | 全文 | AI 受限输出、Evidence、审批后副作用与 fallback |
| `../08_prd/prd.md` | 全文 | FR、非目标、M0-M4、POC、开放问题与 Gate |

### 1.3 同阶段架构草稿：用于横向一致性核对

| 输入 | 实际读取范围 | 使用限制 |
| --- | --- | --- |
| `architecture.md` | 全文 | 当前后端集成架构 Draft；用于核对分册、ADR 与统一推荐，不作为上游事实源 |
| `frontend_design_spec-v1.0.md` | 全文 | 修订阶段纳入前后端交叉核对；消费页面状态、TestRun 呈现、SSE 与审批入口约束，不作为后端技术选型事实源 |
| `frontend_backend_boundary_spec-v1.0.md` | 全文 | 复核后端权威边界、`param_hash`/行锁/幂等和外部访问约束 |
| `01_domain_and_service_architecture.md` | 全文 | 横向核对模块、Worker、事务/消息与开放问题；其自身为 Draft，不作为上游事实源 |
| `02_api_workflow_and_review.md` | 全文 | 横向核对 LangGraph/MCP 分期与 API/审批边界；其自身为 Draft |
| `03_security_reliability_and_operations.md` | 全文 | 横向核对 Temporal POC 运维 Gate、LangGraph/MCP 安全边界；其自身为 Draft |
| `04_architecture_review.md` | 全文 | 修订阶段消费独立 finding-first 审查与验收项；其结论是 Draft 审查建议，不是批准 |

### 1.4 未作为输入读取的文件

- 未读取 `docs/08_prd/README.md` 及 Stage 9-13 的一般占位/变更文档正文：它们不是本次 LangGraph、Temporal、MCP 研究结论的直接事实源；`../13_changes/` 仅作为上游变更流程位置引用。
- 未读取 Git 历史中的 `docs/05_prototype/*.md` 删除前内容；“当前无可读文件”按当前工作树事实记录，不通过 Git 恢复内容来替代当前输入。

## 2. 输入可用性与来源可复核性检查

| 检查项 | 结果 | 证据与处置 |
| --- | --- | --- |
| `docs/05_prototype/` 当前可读文件 | **0 个** | 目录存在，但当前工作树没有可读文件；Git 状态显示其原跟踪的 `README.md`、`component-inventory.md`、`design-review.md`、`page-inventory.md`、`prototype_spec.md`、`ui-brief.md`、`visual-acceptance.md` 处于删除状态。本次不恢复、不读取、不修改这些文件。 |
| `docs/05_prototype/` 图片 | **0 张** | 当前目录无文件，因此无图片可读。 |
| `docs/05_prototype/` HTTP 外链 | **0 条** | 当前目录无可读文件，因此没有可提取或跟随的 HTTP 外链。 |
| 整个 `docs/` 当前图片 | **0 张** | 扫描扩展名 `.png/.jpg/.jpeg/.webp/.gif/.svg` 无结果。 |
| 仓库上游输入中的 HTTP 外链 | **0 条** | 对 `docs/00_setup` 至 `docs/04_interaction_design` 扫描 `http://`/`https://` 无结果；因此除 Lead 本次提供的官方链接外，没有可跟随的仓库内 HTTP 研究引用。 |
| 源仓库引用 | **不可复核** | 总纲明确 `competitors/` 与 `references/` 未随迁，见 `../README.md:8`；市场调研继续引用源仓库研究包，见 `../01_market_research/market_research.md:4`、`../01_market_research/market_research.md:5`；竞品索引声明源码位于仓库外，见 `../02_competitor_analysis/competitor_analysis.md:7`。本次不将这些二手索引提升为重新验证的源码事实。 |
| 官方网页 | **本次未联网复核** | 链接和结论由 Lead 核对后提供；本文按该输入登记问题、结论和项目影响。 |

**输入缺口影响**：缺少 Stage 5 原型可读文件不会改变后端审批、工作流与协议边界的既有事实，但使本次无法核对原型是否已正确表达 WAITING 状态、九要素审批卡片、MCP 禁用态或 POC 标识。该缺口应由原型 Owner 恢复或确认 Stage 5 资产后再做跨阶段一致性评审。

## 3. 关键仓库事实（相对路径:行号）

| ID | 可复核事实 | 仓库依据 | 本文架构含义 |
| --- | --- | --- | --- |
| F-01 | AI 只提议，策略裁决、工作流、重试、幂等和权限不由模型决定 | `../README.md:44`、`../README.md:45`；`../01_market_research/market_research.md:34` | LangGraph 只能位于受限 Agent/Copilot 推理节点，不能成为业务控制面。 |
| F-02 | Agent 动态性限于单用例步骤层，每个工具动作经 Tool Router + Policy Gate | `../README.md:182`、`../README.md:184`、`../README.md:186` | LangGraph 节点恢复后仍需重新经过平台治理。 |
| F-03 | ApprovalRequest 是独立领域对象，绑定 `param_hash`、四眼、独立 TTL，并用行锁单次消费 | `../03_problem_modeling/problem_model.md:28`、`../03_problem_modeling/problem_model.md:193`、`../03_problem_modeling/problem_model.md:195`、`../03_problem_modeling/problem_model.md:197`、`../03_problem_modeling/problem_model.md:199` | interrupt/checkpoint/resume 不得替代审批事实、anti-TOCTOU 或并发控制。 |
| F-04 | 审批消费前重算哈希、重校验权限，失败也审计 | `../04_interaction_design/chains/c2_approval_chain.md:127`、`../04_interaction_design/chains/c2_approval_chain.md:130`、`../04_interaction_design/chains/c2_approval_chain.md:181`、`../04_interaction_design/chains/c2_approval_chain.md:235` | LangGraph/Temporal 只协调等待与唤醒，放行仍由后端 ApprovalRequest 事务完成。 |
| F-05 | TestRun 有 10 态；WAITING_* 是可长期等待态，审批过期不自动放行 | `../03_problem_modeling/problem_model.md:150`、`../03_problem_modeling/problem_model.md:173`、`../03_problem_modeling/problem_model.md:178`、`../03_problem_modeling/problem_model.md:184` | Temporal POC 必须无损映射业务状态，不能以引擎内部状态替代 TestRun。 |
| F-06 | 故障重启不得重复副作用，外部写要求幂等键、external request id、响应快照与补偿 | `../README.md:336`、`../README.md:374` | Temporal Activity 的至少一次执行语义必须由业务幂等与对账吸收。 |
| F-07 | Redis 不得成为工作流/审批等唯一事实源；跨模块消息至少一次且消费者必须幂等 | `01_domain_and_service_architecture.md:95`、`01_domain_and_service_architecture.md:97`、`01_domain_and_service_architecture.md:467` | durable engine、消息总线和 checkpoint 都是协调设施，不是业务事实替代物。 |
| F-08 | 租户隔离和 RBAC 在后端/工具层强制，跨租户不泄露存在性 | `../03_problem_modeling/problem_model.md:97`、`../README.md:328`、`../README.md:334` | MCP host/client/server 或 tool schema 不构成授权边界；每次调用仍需 tenant/RBAC。 |
| F-09 | AuditEvent append-only，外部写与失败操作均需可追溯 | `../03_problem_modeling/problem_model.md:30`、`../03_problem_modeling/problem_model.md:244`、`../04_interaction_design/chains/c2_approval_chain.md:227` | 任一框架事件、resume 或 MCP 调用都必须关联平台审计，而非只留框架日志。 |
| F-10 | Temporal 当前仅为 POC，Celery + 自建状态机 + 幂等纪律是保底 | `../01_market_research/market_research.md:136`、`../README.md:339`、`../08_prd/prd.md:360` | 不能在 POC Gate 前写成定稿依赖或生产部署结论。 |
| F-11 | LangGraph 只作单点受限推理节点，不作业务工作流 | `../01_market_research/market_research.md:137` | 采用 interrupt/checkpoint/streaming 也不扩大其职责。 |
| F-12 | 一期不做 MCP 对外暴露，M4 才评估 | `../08_prd/prd.md:73`、`../08_prd/prd.md:303` | M0-M3 不采用；M4 只读 POC 仍需专项批准。 |

## 4. 事实 / 假设 / 冲突 / 缺失 / 架构影响追溯表

| ID | 类型 | 内容 | 依据或来源 | 架构影响 / 处置 |
| --- | --- | --- | --- | --- |
| T-01 | 事实 | LangGraph 仅用于 Agent/Copilot 受限推理；interrupt/checkpoint/resume 不替代 ApprovalRequest、四眼、`param_hash`、TTL、行锁和审计 | Lead 已核对官方结论；F-01 至 F-04、F-09、F-11 | 将 LangGraph 定位为推理/交互适配层；恢复前必须查询平台事实并重新鉴权。 |
| T-02 | 事实 | Temporal durable workflow 适配长等待和恢复，但 Activity 至少一次，外部副作用必须业务幂等 | Lead 已核对官方结论；F-05、F-06、F-10 | 仅进入条件 POC；TestRun/ApprovalRequest/PostgreSQL 仍为业务事实源。 |
| T-03 | 事实 | MCP 的 tools/resources/prompts 与 host/client/server 是协议边界，不是权限、审批或租户隔离 | Lead 已核对官方结论；F-08、F-09、F-12 | M4 只读 POC 也必须经 Tool Router、tenant/RBAC、审计和 kill switch。 |
| T-04 | 假设 | 团队能运维 Temporal 的持久库、Worker 版本升级、可观测、备份恢复和在途工作流兼容 | 当前无 POC 实测；`03_security_reliability_and_operations.md:418` 至 `03_security_reliability_and_operations.md:427` | 未通过运维 Gate 则采用 Celery + PostgreSQL 权威状态机保底。 |
| T-05 | 假设 | LangGraph checkpoint 可按租户加密、清理，并满足 Agent/Copilot 恢复 SLO | 当前无实现/POC；`02_api_workflow_and_review.md:768` | checkpoint 只存最小上下文或受控引用；不得含 secret/Restricted 原文。 |
| T-06 | 假设 | M4 存在明确只读 MCP 用例，且内部服务契约不能更简单地满足需求 | 当前只有愿景，无需求基线和用户验证 | POC 前先证明具体消费者、价值、白名单与退出条件；否则继续不采用。 |
| T-07 | 冲突 | README 描述 MCP 双向生态位与 M4 能力，而 PRD 明确一期不做 | `../README.md:290`、`../README.md:351`；`../08_prd/prd.md:73` | 以分期兼容：M0-M3 不采用，M4 仅只读 POC 候选，不将愿景当承诺。 |
| T-08 | 冲突 | `docs/04` 的旧图仍有“审批过期 → CANCELLED”，但建模层已裁定 TestRun 保持 WAITING_APPROVAL | `../04_interaction_design/chains/c2_approval_chain.md:161`；`../03_problem_modeling/problem_model.md:178` | Temporal/LangGraph POC 采用建模层最新语义；不得因框架超时自动取消或放行。冲突仅登记，不回写上游。 |
| T-09 | 冲突 | C1 把 release prepare 标为 L3，建模冻结表标为 L4 | `../04_interaction_design/chains/c1_north_star_quality_loop.md:278`；`../03_problem_modeling/problem_model.md:220` | 任何引擎/协议 POC 不碰 Release 写；后续按最高事实源与变更流程裁定。 |
| T-10 | 缺失 | `docs/05_prototype/` 当前无可读文件，无法核对原型表现 | 第 2 节本地扫描结果 | 不阻塞本研究 Draft；阻塞 Stage 5/6 跨阶段 UX 一致性确认。 |
| T-11 | 缺失 | 源仓库 references/competitors 与竞品源码快照当前不可复核 | `../README.md:8`、`../02_competitor_analysis/competitor_analysis.md:7` | 竞品论据只作上游索引，不作为本次新增的源码级证据。 |
| T-12 | 缺失 | Temporal POC 的部署模式、持久化、namespace/task queue、history retention、RPO/RTO 和成本未定 | `03_security_reliability_and_operations.md:414`、`03_security_reliability_and_operations.md:435` | 未补齐不得定稿 Temporal。 |
| T-13 | 缺失 | MCP M4 只读 POC 的工具白名单、试点 tenant、认证映射、退出标准和协议版本未定 | `02_api_workflow_and_review.md:769`、`03_security_reliability_and_operations.md:501` | M4 专项评审前保持关闭，不引入 SDK/依赖。 |
| T-14 | 缺失 | LangGraph checkpoint 的数据分类、保留/删除、加密与恢复 SLO 未定 | `02_api_workflow_and_review.md:768` | Agent/Copilot 技术评审前不得把 checkpoint 当持久化承诺。 |
| T-15 | 架构影响 | 三项技术均不能改变平台的后端权威边界 | `frontend_backend_boundary_spec-v1.0.md:17` 至 `frontend_backend_boundary_spec-v1.0.md:23` | 框架/协议适配器必须位于既有命令、Policy Gate、ApprovalRequest、Connector 与 AuditEvent 之外侧。 |

## 5. 官方调研日志

> 本节“官方结论”由 Lead 事先核对。本次不联网，链接按官方原始 URL 原样登记。每条日志都给出问题、结论、项目影响、采用/不采用理由和 POC 处置。

### 5.1 LangGraph

| ID | 问题 | 官方链接 | Lead 核对结论 | 项目影响 | 采用 / 不采用理由 | POC |
| --- | --- | --- | --- | --- | --- | --- |
| LG-01 | LangGraph 的总体定位是否适合承担平台 TestRun/审批工作流？ | [Overview](https://docs.langchain.com/oss/python/langgraph/overview) | LangGraph 提供面向 Agent 的低层编排能力，适合有状态 Agent、持久化、流式和 HITL；不因此成为本项目业务控制面。 | 可用于 Agent/Copilot 受限推理图；TestRun、ApprovalRequest 继续由领域状态机和后端命令裁决。 | **受限采用**：匹配 Agent/Copilot；**不采用**为普通 TestRun、外部 CI、Release 或审批事实源，因为 F-01/F-05 已有权威业务模型。 | Agent/Copilot 专项 POC：验证受限节点调用、取消、错误恢复，不验证/不改变业务状态机。 |
| LG-02 | interrupt/resume 能否替代审批中心？ | [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) | interrupt 可暂停图并在外部输入后 resume，但它只负责 Agent 执行暂停/恢复。 | interrupt 只能保存等待点并关联 `approval_request_id`；审批创建、四眼、TTL、`param_hash`、行锁消费与审计仍在平台后端。 | **采用 bridge，不采用替代**：可改善 Agent HITL 体验；不能提供项目所需业务不变量和 anti-TOCTOU。 | 模拟 L2+ 工具意图：interrupt → 创建 ApprovalRequest → 独立审批 → resume 前 GET + 哈希/权限复核；自批、过期、参数变更和重复 resume 必须全部拒绝。 |
| LG-03 | checkpoint/persistence 能否作为审批或工作流唯一事实源？ | [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | persistence 保存图状态/checkpoint，支持恢复；它不替代业务数据库中的审批、租户、幂等、状态和审计事实。 | checkpoint 只保存最小 Agent 上下文或平台对象引用；不得保存 secret/Restricted 原文；删除和 tenant 生命周期需另定。 | **受限采用**：用于 Agent/Copilot 恢复；**不采用**为 ApprovalRequest/TestRun/AuditEvent 权威存储。 | 杀进程/恢复 POC：checkpoint 重放不重复工具副作用；跨 tenant thread/checkpoint 访问 100% 阻断；保留/删除待 T-14 闭环。 |
| LG-04 | streaming 是否改变前后端状态权威？ | [Streaming](https://docs.langchain.com/oss/python/langgraph/streaming) | streaming 可提供 Agent 输出、状态或事件增量；流不是业务事实源。 | 可向 UI 提供 Copilot/Agent 进度；终态、审批与执行结果仍以 GET 后端领域资源为准。 | **采用展示流，不采用状态裁决**：与现有 SSE“只展示、GET 对账”原则一致。 | 断流、重连、重复/乱序事件 POC；UI 不得因流中断将 TestRun/ApprovalRequest 推演为失败或过期。 |

### 5.2 Temporal

| ID | 问题 | 官方链接 | Lead 核对结论 | 项目影响 | 采用 / 不采用理由 | POC |
| --- | --- | --- | --- | --- | --- | --- |
| TP-01 | durable workflow 是否适配长审批、长轮询和重启恢复？ | [Workflows](https://docs.temporal.io/workflows) | Workflow 适合持久、可恢复、长时间运行的协调逻辑。 | 与 WAITING_APPROVAL/WAITING_EXTERNAL、外部轮询和恢复需求匹配；但 TestRun/ApprovalRequest 仍是业务事实源。 | **条件采用**：表达力匹配 F-05/F-06；仅在 POC 证明无损状态映射、可运维和可恢复后定稿。 | 以 external_ci + 审批等待为代表流程，分别重启 API、Worker、Temporal 和数据库，验证不丢等待、不重复副作用。 |
| TP-02 | Activity 的交付/重试语义对外部副作用有何约束？ | [Activities](https://docs.temporal.io/activities)；[Retry Policies](https://docs.temporal.io/encyclopedia/retry-policies)；[Idempotency](https://docs.temporal.io/activity-definition#idempotency) | Activity 可能至少一次执行并受重试策略驱动；外部副作用必须业务幂等，不能假设框架 exactly-once。 | Jira issue、CI Job、Check Run、Release item、通知等必须使用稳定幂等键、external_request_id、查询后重试和补偿；压测/Agent 禁止自动重试的业务规则仍有效。 | **采用 Activity，拒绝“框架保证不重复”假设**：Temporal 提供恢复机制，但业务幂等才满足 F-06。 | 对每类外部写注入“请求成功但响应丢失”、Activity 超时、Worker 崩溃和重复投递；外部对象数量必须保持 1，未知结果先查询。 |
| TP-03 | Signal/Update 等消息机制能否承接审批、取消和外部回调？ | [Sending Messages](https://docs.temporal.io/sending-messages) | Workflow 可接收外部消息以推进长流程；消息到达不自动等于业务授权或状态迁移。 | 可作为 ApprovalRequest 结果、取消、webhook 规范化后的唤醒通道；处理前仍需读平台事实、校验版本和幂等。 | **采用协调信号，不采用授权信号**：避免把消息来源或到达顺序误当有效审批。 | 重复、乱序、过期 Signal；ApprovalRequest 已 EXPIRED/REJECTED 后的批准消息不得执行；终态 TestRun 不得被迟到消息重开。 |
| TP-04 | Worker 升级如何兼容长期在途工作流？ | [Worker Versioning](https://docs.temporal.io/worker-versioning) | 长流程要求 Worker 版本演进兼容历史执行。 | POC 必须覆盖新旧 Worker 并存、回滚和旧 history；不得通过清空在途任务解决升级。 | **条件采用**：没有版本治理就不满足长等待生产运维要求。 | 启动旧版本长等待 workflow，部署新 Worker、回滚并恢复；业务状态与外部副作用保持一致。 |
| TP-05 | 自托管/部署运维是否在团队能力边界内？ | [Self-hosted deployment](https://docs.temporal.io/self-hosted-guide/deployment) | 自托管涉及持久化、服务拓扑、升级、容量、可观测、备份恢复和安全运维。 | Temporal 不能只按开发 API 选型；部署方式、RPO/RTO、证书、namespace/task queue 权限和成本均是 Gate。 | **不直接采用生产部署**：先完成 T-04/T-12；失败则走 Celery + PostgreSQL 状态机保底，安全标准不降低。 | 比较托管/自托管/保底方案的恢复演练、值班技能、资源成本和升级复杂度，形成可批准结论。 |

### 5.3 MCP

| ID | 问题 | 官方链接 | Lead 核对结论 | 项目影响 | 采用 / 不采用理由 | POC |
| --- | --- | --- | --- | --- | --- | --- |
| MCP-01 | host/client/server 架构边界是否等同信任或授权边界？ | [Architecture](https://modelcontextprotocol.io/specification/2025-06-18/architecture) | host/client/server 描述协议参与方和连接边界，不自动提供项目级权限、审批、租户隔离或数据分级。 | 任何 MCP 调用者/服务端都必须映射到平台 tenant/project/actor；不接受客户端自报 tenant，不共享平台会话或 Vault secret。 | **M0-M3 不采用；M4 条件 POC**：协议互操作有潜在价值，但不能替代平台治理。 | 仅试点 tenant、显式 allowlist server、只读调用；跨 tenant、伪造身份与未注册 server 必须拒绝。 |
| MCP-02 | tools 能否直接承接平台动作与审批？ | [Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools) | tool 暴露可调用能力及 schema；tool 声明/注解不是可信授权，也不替代 Policy Gate/ApprovalRequest。 | M4 POC 仅暴露 L0 只读工具；每次调用仍过 schema、tenant/RBAC、Tool Router、Policy Gate 和 AuditEvent。 | **只读 POC 候选，不采用写工具**：写工具会提前引入审批、幂等和外部副作用风险；现阶段无必要。 | 工具白名单、参数篡改、注入、超时、重复调用、kill switch；任何写意图 DENY。 |
| MCP-03 | resources 是否可作为 Evidence/ACL 的替代？ | [Resources](https://modelcontextprotocol.io/specification/2025-06-18/server/resources) | resource 提供上下文数据访问模式，但不自动继承项目 ACL、租户隔离、数据分类或 Evidence provenance。 | resource 读取必须先授权再返回；结果标为不可信上下文，保留稳定来源引用；不能用 resource URI 代替 EvidenceObject。 | **受限只读候选**：可标准化读取接口；不采用为证据或授权模型。 | 验证 ACL 变化即时生效、跨租户 URI 不泄露存在性、Restricted 数据不返回、读取全审计。 |
| MCP-04 | prompts 能否视为可信系统指令或权限模板？ | [Prompts](https://modelcontextprotocol.io/specification/2025-06-18/server/prompts) | prompt 是协议暴露的模板能力，不是系统策略；远端 prompt/描述/内容必须视为不可信输入。 | MCP prompt 不得覆盖 System/Policy，不得授权工具或改变 sideEffectLevel；需版本、来源、注入检测和审计。 | **M4 POC 默认不采用 prompts；确有只读价值再单独评审**：当前内部 Skill/Prompt 版本体系更可控。 | 若评估，使用恶意 prompt 套件证明不能越权、泄露或触发工具；失败即退出该能力。 |
| MCP-05 | 协议授权能力是否替代平台 RBAC/审批？ | [Authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization) | 协议授权解决连接/访问的一部分问题，不等同平台的 tenant/project 资源授权、四眼审批或动作级 Policy Gate。 | 外部身份必须映射平台身份；每次资源/tool 调用做持续授权；L2+ 即使未来开放也仍走平台审批。 | **不替代、只叠加**：平台后端授权是最终边界。 | Token scope、吊销、身份映射、混淆代理/错误受众等负面测试；平台 RBAC 仍需独立通过。 |
| MCP-06 | 需要哪些协议级安全前置？ | [Security Best Practices](https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices) | MCP 存在授权、代理、令牌、远端内容和工具调用等安全风险；需最小权限、显式信任、校验和防注入。 | POC 需 allowlist、egress、版本/依赖审计、最小 scope、数据分级、大小/超时/并发限制、全审计和 kill switch。 | **Gate 前不采用**：协议能力不能先于威胁建模与供应链审计。 | 安全专项 POC 与退出标准绑定；任一越权副作用、跨租户泄露或 Restricted 出站即停止。 |

## 6. 采用矩阵

| 技术 / 能力 | M0 | M1 | M2 | M3 | M4 | 最终 Draft 边界 |
| --- | --- | --- | --- | --- | --- | --- |
| LangGraph Agent/Copilot 受限推理 | 不进入主业务链 | 不进入主业务链 | Agent Mode 可做专项 POC/试点 | Copilot 最小版可按需使用 | 可扩展受限推理 | **采用**，但只在 Agent/Copilot 节点；不拥有 TestRun、ApprovalRequest、权限、幂等或审计。 |
| LangGraph interrupt/resume | 不用于审批中心 | 不用于普通任务 | Agent L2+ bridge 候选 | Copilot bridge 候选 | 延续 | **受限采用候选**；只暂停/恢复图，必须绑定平台 ApprovalRequest。 |
| LangGraph checkpoint/persistence | POC 前不承诺 | 同左 | 仅 Agent 恢复 POC | Copilot 会话恢复候选 | 按数据治理评审 | **受限采用候选**；不是业务事实源，数据治理 T-14 未闭环前不定稿。 |
| LangGraph streaming | 不需要 | A1 可用既有异步/SSE | Agent 进度候选 | Copilot 输出候选 | 延续 | **采用展示能力候选**；GET/领域资源仍权威。 |
| Temporal durable workflow | 条件 POC | POC 通过后才可用于 TestRun/外部 CI | 延续 | 长审批/Release 候选 | 延续 | **仅条件采用**；POC 未通过则 Celery + PostgreSQL 权威状态机保底。 |
| Temporal Activity | 随 POC | 随引擎决定 | 延续 | 延续 | 延续 | 即使采用也按至少一次设计；外部副作用必须业务幂等、查询后重试、可补偿。 |
| MCP client/server | **不采用** | **不采用** | **不采用** | **不采用** | **仅只读 POC 候选** | 不开放写工具，不替代内部 Connector/Tool Router，不作为对外承诺。 |
| MCP tools | 不采用 | 不采用 | 不采用 | 内部白名单工具不用 MCP | L0 只读 POC 候选 | 每次调用仍经 tenant/RBAC、schema、Policy Gate、审计、kill switch。 |
| MCP resources | 不采用 | 不采用 | 不采用 | 不采用 | 只读资源 POC 候选 | 不能替代 EvidenceObject、ACL 或数据分类。 |
| MCP prompts | 不采用 | 不采用 | 不采用 | 不采用 | 默认不进首轮 POC | 远端 prompt 不可信；确有需求再单独评审。 |

## 7. POC Gate 与退出条件

### 7.1 LangGraph POC

**范围**：Agent/Copilot 单条 L2+ 工具意图的 interrupt bridge、checkpoint 恢复和 streaming 展示。

**必须通过**：

1. interrupt 创建并只引用后端 ApprovalRequest；自批、过期、`param_hash` 变化、权限变化、跨租户恢复、重复 resume 均 100% 拒绝；
2. checkpoint 丢失或恢复失败不改变 ApprovalRequest/TestRun 事实，不重复工具副作用；
3. 流断线、重复和乱序不让 UI 推演业务终态；
4. checkpoint 不含 secret/Restricted 原文，并能按 tenant 删除；
5. 每一步可关联 AIInvocationLog、AuditEvent、Skill/Prompt 版本和 Evidence。

**退出**：若需要把业务状态复制进 checkpoint 才能正确运行，或无法证明 tenant 清理/重复恢复安全，则不采用 LangGraph persistence；保留普通受限模型调用与平台自有状态机。

### 7.2 Temporal POC

**范围**：一个 external_ci 长轮询流程 + 一个 WAITING_APPROVAL 长等待流程；覆盖 Activity、Signal/Update、Worker 版本和恢复演练。

**必须通过**：

1. TestRun 10 态和 ApprovalRequest 六态无损映射，不新增或隐藏业务状态；
2. API、Worker、Temporal、数据库分别重启，外部 CI/Jira/Release 模拟副作用均不重复；
3. Activity 重复/超时采用稳定幂等键和 external_request_id，未知结果先查询；
4. 重复、乱序、迟到消息不能重开终态或放行过期审批；
5. Worker 新旧版本兼容在途流程，可回滚，不清空 history；
6. tenant/actor/classification/request hash 传播并在执行点重校验，secret 不进入 history；
7. 备份恢复、可观测、权限、容量、成本和值班能力有实测证据；
8. 与 Celery + PostgreSQL 保底方案按同一混沌、幂等、安全 Gate 比较。

**退出**：任何恢复重复副作用、旧流程无法升级、secret 进入 history、RPO/RTO/值班无法承担，均不定稿 Temporal，切换保底方案且不降低 Gate。

### 7.3 MCP M4 只读 POC

**前置**：M0-M3 明确不采用；M4 必须先有已批准的只读用户场景、试点 tenant、协议版本、依赖/License/供应链审计和威胁模型。

**必须通过**：

1. 仅 L0 只读 tools/resources；prompts 默认不在首轮；任何写意图和未声明动作 DENY；
2. host/client/server 各方身份映射到平台 tenant/project/actor，跨租户访问 100% 阻断且不泄露存在性；
3. 调用经 allowlist、Tool Router、schema、RBAC、Policy Gate、数据分级、egress、审计和 kill switch；
4. server/tool description、resource、prompt、result 全视为不可信内容，恶意注入不能改变系统策略或触发工具；
5. Restricted 数据不出站，Confidential 按路由策略处理；不向外部 Agent 暴露平台会话/Vault secret；
6. 每次 list/read/call 可追溯到 server/tool/version、actor、request hash、classification、结果和 Evidence；
7. 证明相较内部 API/Connector 契约有明确价值，且成本/稳定性可接受。

**退出**：出现一次越权副作用、跨租户泄露、Restricted 出站，或无法证明优于内部契约，则关闭 POC，不进入产品路线。

## 8. 待确认项、Owner 与期限

| ID | 待确认项 | Owner | 期限 | 阻塞对象 |
| --- | --- | --- | --- | --- |
| Q-01 | 确认 Stage 5 原型资产为何当前无可读文件，是否需要恢复或重新批准替代输入 | 原型 Owner + Lead | Stage 6 总评审前 | 原型与架构跨阶段一致性确认 |
| Q-02 | 批准 LangGraph interrupt/checkpoint POC 的最小场景、数据保留/删除、加密和恢复 SLO | Agent/Copilot 技术 Owner + 安全 | M2 Agent 试点前 | LangGraph persistence/interrupt 定稿 |
| Q-03 | Temporal POC 的托管/自托管候选、RPO/RTO、namespace/task queue、history retention、成本和值班责任 | 平台架构师 + SRE + 安全 | M0 第 4 周 | Temporal 选型 Gate；对齐 `../08_prd/prd.md:360` |
| Q-04 | 为 CI/Jira/GitHub/Release 各动作冻结幂等键、external_request_id 查询和补偿契约 | 集成 Owner + 各外部系统 Owner | 相应 Connector contract test 前，最迟 M1 | Temporal/Celery 两方案的副作用安全 |
| Q-05 | 处理“审批过期”旧交互图与建模层冲突 | 产品 + 领域建模 Owner | Stage 7 API/状态机契约冻结前 | POC 状态映射；本文暂服从建模层 |
| Q-06 | 处理 release prepare L3/L4 冲突 | 安全 + Release Owner + 产品 | M3 Release 设计前 | Release Policy Gate；当前 POC 禁止触碰写入 |
| Q-07 | 明确 MCP M4 只读 POC 的用户场景、工具/资源白名单、试点 tenant、协议版本和退出指标 | M4 产品 Owner + 安全 + 架构师 | M4 立项评审前 | 是否启动 MCP POC |
| Q-08 | 完成 MCP SDK/依赖 License、供应链与安全通告审计；未经批准不得引入依赖 | 架构师 + 安全 + 法务/依赖 Owner | MCP POC 依赖变更前 | MCP POC 实施 |
| Q-09 | 确认官方链接版本在 POC 开始时仍适用，并冻结评审日期/协议版本 | 各 POC 技术 Owner | 各 POC 开始前 | 避免文档/API 漂移 |
| Q-10 | 指派具体人名与评审日历；当前仅有角色级 Owner | 平台负责人 | M0 启动会 | 所有 POC 执行与签字 |

## 9. 对下游架构分册的约束

1. 任何同目录分册不得把 LangGraph 描述为平台业务工作流引擎，或把 checkpoint/interrupt 当作 ApprovalRequest、TestRun、审计、权限和租户事实源。
2. 任何 Temporal 方案必须明确 Activity 至少一次和业务幂等，不得使用“durable/exactly once”措辞淡化外部副作用重复风险。
3. Temporal 只能在 POC Gate 后由 Draft/TBD 升级为定稿；此前架构必须保留 Celery + PostgreSQL 权威状态机的可行保底。
4. M0-M3 不得引入 MCP SDK、传输、server/client 或对外协议承诺；M4 仅允许经过批准的只读 POC。
5. MCP tools/resources/prompts、host/client/server、授权协议均不得替代平台 tenant/RBAC、Policy Gate、ApprovalRequest、EvidenceObject 或 AuditEvent。
6. 所有框架/协议适配器只能调用既有后端命令、查询和连接器端口，不得直写领域私有表或绕过业务状态机。

## 10. 不改上游声明

本文只创建 Stage 6 研究输入分册，不修改 `docs/00_setup` 至 `docs/05_prototype`、`docs/08_prd`、`docs/13_changes` 或同目录其他 Stage 6 文档。文中发现的旧图、等级、缺失资产和来源不可复核问题均只登记为 Draft 冲突/缺失，不代表上游已被修正；后续若需变更已用于指导下游的设计资产，必须遵循 `../00_setup/project_rules.md:130` 至 `../00_setup/project_rules.md:134` 的登记、批准与 diff 要求。

## 11. Draft 结论

- **LangGraph**：采用范围限定为 Agent/Copilot 受限推理及可选 interrupt/checkpoint/streaming 适配；永不替代 ApprovalRequest、四眼、`param_hash`、TTL、行锁、tenant/RBAC、审计或 TestRun。
- **Temporal**：只进入条件 POC；durable workflow 与长等待匹配，但 Activity 至少一次，所有外部副作用必须由业务幂等、查询后重试、external_request_id 和补偿保证。POC 未通过即使用 Celery + PostgreSQL 权威状态机保底。
- **MCP**：M0-M3 不采用；M4 仅只读 POC 候选。tools/resources/prompts 与 host/client/server/authorization 不能替代平台权限、审批、租户隔离、Evidence 或审计。
- **输入完整性**：仓库内核心建模和交互事实可复核；`docs/05_prototype/` 当前无可读文件、无图片，仓库上游无 HTTP 外链，源仓库 references/competitors 不可复核，均已显式登记，不用推测补齐。
