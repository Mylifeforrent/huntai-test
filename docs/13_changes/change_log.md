# 变更记录（change_log）

> 使用规则：任何对已沉淀设计资产或工程规范的修改，必须**先**在下方表格追加一行并获批准，再执行修改。
> 新记录在上（按时间倒序）。登记格式不完整视为未登记。

| 日期 | 变更对象（路径） | 变更摘要 | 原因 | 批准人 | 状态 |
|---|---|---|---|---|---|
| 2026-08-29 | `docs/03_problem_modeling/problem_model.md`；`docs/04_interaction_design/chains/c4_failure_triage.md`；`docs/06_architecture_design/`；`docs/08_prd/prd.md` | 按独立复审修订 Stage 6：接受模块化单体控制面与 Temporal 持久工作流选型；明确该选择不等于生产就绪，保留恢复、版本、容量、成本和运维 Gate；补齐 Temporal/Outbox/Activity 路由、模块拓扑、一致性矩阵及外部副作用 `unknown` 结果与 execution intent 恢复协议 | 用户已完成 Temporal 适配 POC，并明确要求以 2026-08-29 架构复审结果为准修订冻结资产 | 用户（本会话明确确认修订计划） | 已完成 |
| 2026-08-27 | `docs/06_architecture_design/architecture.md`；`docs/06_architecture_design/README.md` | `architecture.md` 从 Draft 转为 Stage 6 已定稿集成正文；README 同步登记该文件状态。8 份 ADR 仍 Proposed，00–04 分册与前端规范仍 Draft；不把 Proposed/TBD/POC 提升为已批准实现 | 用户确认架构文档符合要求并要求定稿 | 用户（本会话明确请求） | 已完成 |
| 2026-08-27 | `docs/00_setup/project_rules.md` §2、`AGENTS.md` §1；新增 `.cursor/` | 顶层仓库级配置白名单增加 `.cursor/`（Cursor MCP 与 rules）；与既有 `.zcode/`、`.mcp.json` 并列，不替换 | 在 Cursor 中使用与 ZCode 相同的 LangChain MCP，并明确 Cursor 工程配置合法落点 | 用户（本会话明确请求） | 已完成 |
| 2026-08-25 | docs/05_prototype/ 新增 5 份 UI/UX 模板 | 自源仓库 UI-UX-docs 的 docs/templates 复制 page-inventory 等五份模板（工具，非阶段产出），外链转源仓库限定 | 原型阶段需要统一的页面清单/组件清单/评审模板 | Tony | 已完成 |
| 2026-08-25 | docs/06_architecture_design/frontend_design_spec-v1.0.md（新增） | 生成前端设计规范 v1.0：P01–P25 页面清单、路由结构、跳转矩阵、前端职责边界、核心交互要求、响应式工程约定、与 Prototype 对应关系；缺口 6 项上报 | Stage 6 前端分册收口，供原型评审与实现使用 | Tony | 已完成 |
| 2026-08-24 | docs/01–08、13 新增 14 份设计文档 | 迁入 opensource-product-analysis 仓库决策文档集：按仓库规范重命名（snake_case）、改写全部内部交叉链接、外部资产（competitors/ references/）转为源仓库限定引用；各阶段 README 登记产出 | 复用已完成的设计资产，避免重复调研与建模 | Tony | 已完成 |
|  |  |  |  |  |  |
