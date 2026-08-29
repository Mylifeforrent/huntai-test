# 07_backend_design — 数据模型与 API 规范

存放数据模型与 API 规范产出：模块私有逻辑表、ER、字段/约束/分级，以及后续 API 契约（路径 / 方法 / 请求响应 / 错误码 / SSE）。
由 Stage 7（数据模型与 API 规范）产出。

本文档阶段**不**定义 LangChain / LangGraph 编排表或接口；Agent/Copilot 边界以 Stage 6 已定稿架构为准（LangGraph 仅限受限节点，M0–M3 不采用 MCP）。

**约定输出**：

| 文件 | 状态 | 说明 |
| --- | --- | --- |
| [data_model.md](data_model.md) | Draft · 本次产出 | 逻辑数据模型：23 对象映射、从属结构、基础设施表、分级与迁移政策 |
| [module_schema_ownership.drawio](module_schema_ownership.drawio) | 已生成 | 模块私有 schema 归属图（可编辑） |
| [module_schema_ownership.svg](module_schema_ownership.svg) | 已生成 | 同上图 SVG 预览 |
| `api_spec.md` | 未开始 | 后续产出；OpenAPI 风格 API 契约，不含本阶段表设计 |
