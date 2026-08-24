# huntai-test

个人 AI 应用项目，采用「文档先行、分阶段推进」的 Agent Team 协作流程：全部设计资产落盘在 `docs/`，实现代码只在 Stage 11 进入 `frontend/` 与 `backend/`。

> 当前阶段：**Stage 1–4 设计文档集已迁入**（2026-08-24，源自 opensource-product-analysis 仓库的决策文档集，见 `docs/README.md` 迁移注记）。仓库仍不含任何前后端实现代码；Stage 5 原型与 Stage 6 架构为占位骨架待生成，Stage 8 PRD 为中期版 v1.5。

## 目录结构

```text
huntai-test/
├── AGENTS.md                   # 仓库级 Agent 指令（ZCode 每次会话自动加载）
├── README.md                   # 本文件：项目总览与技术栈决策
├── frontend/                   # 前端源码（Stage 11 落地，当前为空）
├── backend/                    # 后端源码（Stage 11 落地，当前为空）
└── docs/                       # 全部设计资产与过程文档的唯一存放地
    ├── README.md               # 决策总纲（迁入文档集的总索引与编号映射）
    ├── 00_setup/               # Stage 0  · 项目规范
    ├── 01_market_research/     # Stage 1  · 业务调研
    ├── 02_competitor_analysis/ # Stage 2  · 竞品分析
    ├── 03_problem_modeling/    # Stage 3  · 业务问题建模
    ├── 04_interaction_design/  # Stage 4  · 核心交互链路设计
    ├── 05_prototype/           # Stage 5  · 产品原型规范
    ├── 06_architecture_design/ # Stage 6  · 系统架构设计
    ├── 07_backend_design/      # Stage 7  · 数据模型与 API 规范
    ├── 08_prd/                 # Stage 8  · PRD
    ├── 09_figma_highfi/        # Stage 9  · 高保真设计
    ├── 10_ai_context/          # Stage 10 · AI 上下文
    ├── 11_test/                # Stage 11 · 前端/后端实现与联调测试
    ├── 12_deployment/          # Stage 12 · 发布和部署
    └── 13_changes/             # Stage 13 · 变更记录（各阶段持续更新）
```

各目录的存放内容与约定输出文件见其内 `README.md`。

## 技术栈决策

选型原则：**单人项目没有团队缓冲去消化新栈的学习与踩坑成本**，因此优先选择「个人最熟悉、生态成熟、训练语料充分（AI 生成代码可靠性最高）」的组合，而非“当下最流行”的栈。此处只定组合、不锁版本；版本在 Stage 11 初始化代码时锁定。

### 后端：Python 3.12+ · FastAPI · uv · SQLAlchemy 2.0 · LangChain

| 选择 | 理由 |
|---|---|
| Python 3.12+ | LangChain / AI 生态的第一语言，与 uv 工具链成熟配套 |
| FastAPI | 原生 async，直接支持 AI 应用常见的 SSE 流式响应；Pydantic v2 校验 + 自动生成 OpenAPI 文档，作为前后端契约 |
| uv | 虚拟环境与依赖一体化管理，`uv.lock` 保证可复现；已固化为仓库工程约定（AGENTS.md §3） |
| Pydantic Settings | 以 `.env` 为唯一配置入口，与安全基线（`.env` 不入库、`.env.example` 只含键名）配套 |
| SQLAlchemy 2.0（async）+ Alembic | ORM 与迁移；开发期用 SQLite 零运维，如需多用户并发再切 PostgreSQL（方言差异被 ORM 层屏蔽） |
| LangChain / LangGraph | 仓库已接入 LangChain 官方文档 / 参考 MCP（`.zcode/config.json`、`.mcp.json`），项目方向即该生态 |

### 前端：React · TypeScript · Vite · Tailwind CSS · shadcn/ui

| 选择 | 理由 |
|---|---|
| React + TypeScript | 个人最熟练的组合，社区语料最充分，AI 生成与排错效率最高 |
| Vite（纯 SPA） | 前后端分离下职责边界最干净：渲染全在客户端、服务端只有 FastAPI；避免 Next.js SSR 与 Python 后端在服务端职责上重叠 |
| Tailwind CSS + shadcn/ui | 组件源码直接进仓库而非黑盒依赖，适合单人快速搭建 AI 应用常见的对话式 UI |
| TanStack Query + Zustand | 服务端状态与本地状态各用最简方案，不引入 Redux 级复杂度 |

### 质量工具链（Stage 11 随代码初始化落地）

- 后端门禁：`ruff check` / `ruff format --check` / `mypy` / `pytest`
- 前端门禁：ESLint / `tsc --noEmit` / `npm run build` / Vitest
- 提交门禁：pre-commit + gitleaks（已配置，`.pre-commit-config.yaml`）

## 关键文档

| 文档 | 内容 |
|---|---|
| `AGENTS.md` | 仓库级 Agent 指令：目录职责边界、`.env` / uv 约定、阶段输出文件要求、Plan 优先规则 |
| `docs/00_setup/project_rules.md` | 工程规范：命名、目录组织、Git 分支与 Conventional Commits、AI 生成代码 Review Checklist、测试与验证、AI 使用红线 |
| `docs/README.md` | 决策总纲（迁入）：北极星闭环、竞品结论、平台功能裁定、分期路线图、安全清单，以及迁入文档集的编号映射 |

已就绪的工程基线：`.gitignore`（密钥与环境文件忽略）、`.env.example`（仅键名模板）、pre-commit + gitleaks（秘密扫描）、LangChain 文档 / 参考 MCP（`.zcode/config.json` 与 Claude 兼容的 `.mcp.json`）。

## 阶段进度

| 阶段 | 产出位置 | 状态 |
|---|---|---|
| Stage 0 · 初始化与规范搭建 | `docs/00_setup/` + 根 `AGENTS.md` | ✅ 完成 |
| Stage 1 · 业务调研 | `docs/01_market_research/` | ✅ 文档集迁入（研究包借鉴与设计增强） |
| Stage 2 · 竞品分析 | `docs/02_competitor_analysis/` | ✅ 文档集迁入（源码实现索引） |
| Stage 3 · 业务问题建模 | `docs/03_problem_modeling/` | ✅ 文档集迁入（v1.3，23 对象 / 25 页 IA） |
| Stage 4 · 核心交互链路设计 | `docs/04_interaction_design/` | ✅ 文档集迁入（v1.1 + C1–C4 链路详设） |
| Stage 5 · 产品原型规范 | `docs/05_prototype/` | ⏳ 占位骨架已迁入，待生成 |
| Stage 6 · 系统架构设计 | `docs/06_architecture_design/` | ⏳ 占位骨架已迁入，待生成 |
| Stage 7 · 数据模型与 API 规范 | `docs/07_backend_design/` | 待启动 |
| Stage 8 · PRD | `docs/08_prd/` | 🔶 中期版 v1.5 已迁入，待 v2 终版 |
| Stage 9 · 高保真设计 | `docs/09_figma_highfi/` | 待启动 |
| Stage 10 · AI 上下文 | `docs/10_ai_context/` | 待启动 |
| Stage 11 · 实现与联调测试 | `docs/11_test/` + 代码目录 | 待启动 |
| Stage 12 · 发布和部署 | `docs/12_deployment/` | 待启动 |
| Stage 13 · 变更记录 | `docs/13_changes/` | 🔶 机制启用（change_log + 历史一致性修复记录） |
| Stage 14 · 设计资产冻结与约束补充 | `AGENTS.md` 补充条款 | 待启动 |
