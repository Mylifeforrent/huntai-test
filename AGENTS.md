# AGENTS.md — huntai-test 仓库级指令

> Cursor 与 ZCode 均会在会话中加载本文件（Cursor 另读 `.cursor/rules/`；ZCode 等价于 Claude Code 的 `CLAUDE.md`）。
> 本文件是**工程规则初始版（Stage 0 产出）**：只包含工程约定，设计资产冻结与约束条款由 Stage 14 补充完善。
> 完整规范见 `docs/00_setup/project_rules.md`；两文冲突时以 project_rules.md 为准。
> MCP 三份清单须保持一致：ZCode `.zcode/config.json`、Cursor `.cursor/mcp.json`、Claude 兼容 `.mcp.json`。

## 1. 目录职责边界

| 目录 | 职责 | 禁止 |
|---|---|---|
| `frontend/` | 前端源码与前端工程配置 | 存放设计文档、后端代码 |
| `backend/` | 后端源码与后端工程配置 | 存放设计文档、前端代码 |
| `docs/` | **全部**设计资产与过程文档的唯一存放地 | 存放任何可执行代码 |

- 仓库顶层只允许上述三个业务目录 + 仓库级配置文件（`README.md`、`AGENTS.md`、`.gitignore`、`.env.example`、`.pre-commit-config.yaml`、`.zcode/`、`.cursor/`、`.mcp.json` 等）。
- 设计文档写进 `frontend/` / `backend/`，或可执行代码写进 `docs/`，均视为放错位置，当次提交必须移正。
- `docs/` 阶段目录（`00_setup` – `13_changes`）与阶段一一对应：目录序号与名称不得变更；任何阶段的产出只落入对应目录。
- `backend/` / `frontend/` 的内部子结构由 Stage 6/7 设计文档定稿；定稿前不得预建子目录。

## 2. 后端配置：统一 .env

- 后端全部配置（数据库连接、密钥、环境开关）统一经 `.env` 注入；代码中禁止硬编码任何配置值。
- `.env` 不入库（`.gitignore` 已忽略 `.env*`）；`.env.example` 入库且**只含键名，不含任何值**。
- 当前 `.env.example` 位于仓库根，`backend/` 初始化时迁入 `backend/` 并保持仅键名。
- 新增配置项的提交必须同步更新 `.env.example`；未同步的提交视为不完整，不得合入。

## 3. 后端依赖与环境：统一 uv

- 虚拟环境与依赖一律用 uv 管理：`uv sync` 安装、`uv add <pkg>` 新增；`uv.lock` 入库。
- 禁止 pip 直接安装、禁止手写 `requirements.txt`、禁止 poetry。
- `pyproject.toml` / `uv.lock` 的变更必须独立成 commit，且新增运行时依赖须事先获用户批准（红线 R4）。

## 4. 阶段输出文件要求

- 每个 Agent Team 阶段必须产出**明确的输出文件：路径 + 格式**；默认约定登记在各 `docs/NN_*/README.md`，偏离默认约定必须先经 `docs/13_changes/` 变更流程修订。
- 判定标准：约定输出文件不存在 ⇒ 该阶段未完成，不得进入下一阶段。
- 默认格式为 Markdown；二进制资产（原型图、切图等）存放于对应目录并在该阶段 README 登记文件名与来源。

## 5. 复杂任务先 Plan 再实施

满足任一条件即为复杂任务，必须先输出 Plan（目标、涉及文件、实施步骤、验证方式），经用户确认后实施：

1. 涉及 2 个及以上文件；
2. 修改已有代码行为或已有文档结论；
3. 新增目录或顶层文件；
4. 变更依赖或配置。

仅以下情况可直接执行：单文件内的文案 / 注释修订、纯格式化、新建空目录。

当前阶段附加约束：**Stage 0 禁止生成任何前后端实现代码。**

## 6. 分支与提交（摘要）

- 代码变更走 `feat|fix/<slug>` 分支，squash 合并回 `main` 并删除分支；文档与规范变更可直接提交 `main`。
- Commit 遵循 Conventional Commits（细则与正则校验见 `docs/00_setup/project_rules.md` §3）。
- pre-commit（含 gitleaks）必须通过，禁止 `--no-verify`。

## 7. AI 使用红线（摘要，逐条执行标准见 project_rules.md §6）

1. 禁止将密钥、生产数据、用户隐私数据提供给 AI。
2. 禁止 AI 静默修改已冻结的设计资产（变更必须先在 `docs/13_changes/` 登记并获批准）。
3. 禁止提交未运行验证的 AI 生成代码。
4. 禁止 AI 自行引入未审计的第三方依赖。
