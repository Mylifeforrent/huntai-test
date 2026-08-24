# 08 · 后端架构设计（Stage 8 · ⚠️ 占位待生成）

> - **状态**：占位文档——将由开发流程图 Stage 8「后端架构设计」执行生成（与 Stage 12 PRD 终版并行）；本文件仅定义输入、范围与输出结构
> - **上游输入**：[05-业务建模](../03_problem_modeling/problem_model.md)（ER / 状态机 / 治理约束）· [03-市场调研借鉴](../01_market_research/market_research.md) 第 4 节（技术选型裁定：Temporal POC / pgvector 起步 / FastAPI+Pydantic）· [04-竞品功能拆解索引](../02_competitor_analysis/competitor_analysis.md)（行号级避坑清单）· [README](../README.md) 第 7 章（平台底座）与第 9 章（安全清单 16 条）
> - **下游消费者**：数据模型 / API 设计 / 开发实施（流程图后续 Stage）· [12-PRD](../08_prd/prd.md) v2 终版（并行互校）

## 1. 输出结构要求

| 小节 | 内容 |
| --- | --- |
| 模块划分 | 对照 05 §1 领域对象与 03 研究包分层（Experience / Application / Orchestration / Integration / Execution / Data），给出模块-对象归属矩阵 |
| 执行编排定稿 | Temporal vs Celery+自建状态机的 POC 结论（PRD Q3 的闭环） |
| 核心组件设计 | 执行器（平台/外部 CI Connector）、沙箱、Policy Gate、审批中心、LLM 工厂唯一出口、模型路由、Evidence 服务、审计管道 |
| 数据与存储 | PostgreSQL / Redis / MinIO 职责边界；保留策略（PRD Q6 法务确认后定稿） |
| 部署拓扑 | 私有化单企业部署起步；与 AIOps/网关的边界（README 裁定） |
| 安全设计 | 逐条对照 README 第 9 章 16 条 + 04 §4 六项修订建议（LLM 出口收口 / Token 消费闭环 / import 完整性门禁等）给落点 |
| ADR 记录 | 所有架构决策以 ADR 形式记录，可追溯 |

## 2. 生成纪律

1. 不得推翻 README / 03 已裁定项；确需推翻，先回写决策文档并更新版本号；
2. 每个组件设计须引用 04 索引的对应竞品实现参考与「必须反向做对」条目；
3. 完成后将头部状态改为「已生成 vX.0」。
