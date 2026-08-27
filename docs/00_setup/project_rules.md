# 项目工程规范（project_rules）

- **适用范围**：huntai-test 全仓库（`frontend/`、`backend/`、`docs/`）
- **产出阶段**：Stage 0（项目初始化与规范搭建）
- **生效方式**：仓库根 `AGENTS.md` 摘要引用本文件并随会话自动加载；本文件与 AGENTS.md 冲突时，以本文件为准
- **修订方式**：任何修订必须先在 `docs/13_changes/change_log.md` 登记，再以 `docs(setup):` 类型的 commit 合入
- **约束等级用语**：**必须**（违反即阻断合入）／ **禁止**（违反即触犯红线，处置见 §6）／ **默认**（不声明变更即按此执行）

## 1. 代码命名规范

### 1.1 后端（Python）

| 对象 | 规范 | 示例 |
|---|---|---|
| 模块 / 文件 | snake_case | `chat_service.py` |
| 类 | PascalCase | `ChatSession` |
| 函数 / 方法 / 变量 | snake_case | `build_prompt` |
| 常量 | UPPER_SNAKE_CASE | `MAX_RETRY = 3` |
| 环境变量 | UPPER_SNAKE_CASE | `LLM_API_KEY` |
| 包名 | 单个小写单词 | `app.api` |

- 公开函数与类方法必须带完整类型注解（参数 + 返回值）。
- **判定标准**：`uv run ruff check .` 与 `uv run ruff format --check .` 零告警；抽查公开函数无缺失注解。

### 1.2 前端（TypeScript / React）

| 对象 | 规范 | 示例 |
|---|---|---|
| 组件文件 | PascalCase.tsx | `ChatPanel.tsx` |
| Hook 文件 | use 前缀 + camelCase.ts | `useChatStream.ts` |
| 工具 / 纯函数文件 | camelCase.ts | `formatTime.ts` |
| 组件名 / 类型 / 接口 | PascalCase | `ChatMessage` |
| 变量 / 函数 | camelCase | `sendMessage` |
| 常量 | UPPER_SNAKE_CASE | `MAX_MESSAGES` |
| 自定义 CSS 类 | kebab-case（优先使用 Tailwind 原子类） | `chat-panel` |

- tsconfig 必须开启 `strict: true`；禁止 `any`，确需宽类型用 `unknown` + 类型收窄。
- **判定标准**：`npx tsc --noEmit` 与 ESLint 零错误；grep 不出现 `: any` 与 `<any>`。

### 1.3 文档、数据与 API

- `docs/` 内文件名：全小写 snake_case，扩展名 `.md`（如 `market_research.md`）。
- `docs/` 阶段目录名固定为 `NN_名称`（00–13）：序号与名称不得修改；新增阶段目录必须走 §6 R2 变更流程。
- 数据库：表名 snake_case 复数（`chat_sessions`），字段名 snake_case。
- API 路径：全小写、连字符分隔、名词复数（如 `/api/v1/chat-sessions`）。

## 2. 目录组织规范

1. 仓库顶层只允许三类业务目录：`frontend/`、`backend/`、`docs/`；其余只能是仓库级配置文件（`README.md`、`AGENTS.md`、`.gitignore`、`.env.example`、`.pre-commit-config.yaml`、`.zcode/`、`.cursor/`、`.mcp.json`）。
2. 设计资产与过程文档只存放于 `docs/`；`frontend/`、`backend/` 内禁止出现设计文档（代码目录内的 `README.md` 不算设计文档，但内容只限「如何构建 / 运行」）。
3. 可执行代码只存放于 `frontend/`、`backend/`；`docs/` 内禁止出现代码文件（`.md` 内嵌的代码示例片段不算）。
4. 阶段产物只进对应 `docs/NN_*` 目录；跨阶段引用使用相对路径链接。
5. `backend/`、`frontend/` 的内部结构由 Stage 6/7 设计文档定稿；定稿前不得预建子目录（Stage 0 的占位 `README.md` 除外）。

**判定标准**：出现上述约定之外的顶层条目、或文件类型与所在目录不符，即不合规，当次提交必须移正后重新提交。

## 3. Git 分支策略与 Commit 规范

### 3.1 分支策略

- `main`：唯一长期分支，必须始终保持「可构建、可部署」状态。
- 代码变更：从 `main` 切出 `feat/<slug>` 或 `fix/<slug>`（slug 全小写连字符，可带阶段号，如 `feat/stage11-chat-api`），完成后 squash merge 回 `main` 并删除分支。
- 文档与规范变更：可直接提交 `main`。
- 禁止长期存活的开发分支：分支创建后 5 个工作日内未合并的，必须说明原因或废弃删除。

### 3.2 Commit 规范（Conventional Commits）

格式：`<type>(<scope>): <subject>`

- **type 限定**：`feat` `fix` `docs` `style` `refactor` `test` `chore` `perf` `ci` `build` `revert`
- **scope 限定**（可省略）：`frontend` `backend` `docs` `setup` `deploy`
- **subject**：中文祈使句，不超过 72 字符，结尾不加句号。
- 一个 commit 只做一件事；涉及行为变更或非平凡修改必须写 body 说明动机与影响。
- **判定标准**：commit subject 匹配正则 `^(feat|fix|docs|style|refactor|test|chore|perf|ci|build|revert)(\((frontend|backend|docs|setup|deploy)\))?: .{1,72}$`，不匹配即不合规。

### 3.3 提交门禁

- pre-commit（含 gitleaks 秘密扫描）必须通过；禁止 `git commit --no-verify`。
- 代码类 commit 合入前必须通过 §5 的验证命令。

## 4. AI 生成代码 Review Checklist

> 本清单对应上游手册附录 D（AI 生成代码 Review Checklist）；上游手册未入库期间，以本节条目为唯一执行版本，手册入库后如有出入，走 §6 R2 变更流程同步。

AI 生成（或 AI 辅助）的代码合入前逐项核对；**任何一项为「否」⇒ 不得合入**：

- [ ] **逐行可解释**：提交者能说明每段代码的意图；对无法解释的段落已删除或重写。
- [ ] **API 真实存在**：代码引用的第三方库符号在锁定版本（`uv.lock` / `package-lock.json`）中真实存在，并已通过运行验证。
- [ ] **无未审计依赖**：本次变更未引入未经批准与审计的第三方依赖（红线 R4）。
- [ ] **静态检查全绿**：ruff / ESLint / `tsc --noEmit` 零错误。
- [ ] **测试通过**：新增或修改的逻辑有对应测试，`uv run pytest` / `npm run test` 全绿。
- [ ] **无敏感信息**：无硬编码密钥、真实用户数据、生产数据。
- [ ] **边界处理**：空输入与失败路径（网络错误、上游 5xx、超时）有显式处理。
- [ ] **与设计一致**：实现与 `docs/` 已冻结设计资产（数据模型、API 契约、交互链路）无冲突。
- [ ] **安全基线**：无 SQL 字符串拼接、无未转义的用户输入渲染（如 `dangerouslySetInnerHTML`）、无未鉴权的敏感端点。

## 5. 测试与验证要求

> 以下命令中的 uv 项目与 npm scripts 于 Stage 11 代码初始化时提供；在此之前本节适用于验证「未引入代码文件」。

### 5.1 后端（pytest）

- 框架：pytest + pytest-asyncio + httpx；测试位于 `backend/tests/`（Stage 11 创建）。
- **必须**：
  - service / domain 层每个新增函数至少 1 条正例测试；含分支或外部调用（IO / 网络 / DB）的函数额外至少 1 条异常路径测试。
  - 每个 API 端点至少 1 条 happy-path 集成测试（httpx AsyncClient）。
  - bug 修复先写复现测试（先失败、后通过），测试与修复在同一 commit。
- **合入前验证命令（必须全部通过）**：`uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest`

### 5.2 前端（Vitest + React Testing Library）

- **必须**：组件交互逻辑（事件、状态流转）有测试；纯函数全量测试。
- **合入前验证命令（必须全部通过）**：`npm run lint && npx tsc --noEmit && npm run build && npm run test`

### 5.3 通用

- 无法本地验证的变更（如部署配置），必须在对应阶段输出文档中记录验证方式与验证人。
- **判定标准**：验证命令输出零失败；CI（Stage 12 引入）为绿。

## 6. AI 使用红线

违反任一红线的处置：立即停止当前 AI 操作，本次产生的变更全部回滚；已合入 `main` 的，revert 并在 `docs/13_changes/change_log.md` 登记。

### R1 禁止将密钥、生产数据、用户隐私数据提供给 AI

- 密钥只存在于本地 `.env`；任何 AI 会话、提示词、粘贴内容、日志、示例中不得出现 `.env` 的值。
- 需要 AI 协助处理数据问题时，必须使用脱敏或合成样例（不含真实用户标识）。
- **执行判定**：提交内容经 gitleaks 扫描零命中；对话与文档抽查无密钥值、无真实 PII。

### R2 禁止 AI 静默修改已冻结的设计资产

- 已冻结资产 = `docs/` 中带「已冻结」标记的文档（标记规范由 Stage 14 落地）；Stage 14 之前，凡已用于指导后续阶段的设计产出（如 PRD、API 规范）一律按冻结资产对待。
- 修改冻结资产的前置条件：① 先在 `docs/13_changes/change_log.md` 登记变更记录；② 获用户显式批准；③ 修改后在回复中展示变更 diff。三者缺一即视为静默修改。
- **执行判定**：冻结文档的任意 git 变更必须能对应到 change_log 记录；对应不到的，视为静默修改，必须 revert。

### R3 禁止提交未运行验证的 AI 生成代码

- 任何 AI 生成代码在提交前必须实际运行 §5 验证命令且零失败。
- 无法运行验证的代码不得合入 `main`（只能留在分支并在阶段输出文档中说明阻塞原因）。
- **执行判定**：commit message body 或阶段输出文档中记录验证命令与结果；抽查必须能复现验证输出。

### R4 禁止 AI 自行引入未审计的第三方依赖

- 新增运行时依赖的固定顺序：获用户批准 → 审计（维护活跃度、License 兼容、无未修复的安全通告）→ `uv add` / `npm install` 落锁。
- 依赖文件（`pyproject.toml`、`uv.lock`、`package.json`、`package-lock.json`）的变更必须独立成 commit，便于审计回溯。
- **执行判定**：依赖文件变更的 commit 无法对应到事先批准记录的，视为违规。
