# 00_setup — 项目规范

存放仓库级工程规范与协作规则（命名、目录组织、Git 分支与 Commit、AI 生成代码 Review Checklist、测试与验证、AI 使用红线）。
由 Stage 0（项目初始化与规范搭建）产出。

**约定输出**：

- `project_rules.md` — 工程规范（Markdown）
- 根目录 `AGENTS.md` — 仓库级 Agent 指令完善版（物理位置在仓库根；Stage 0 初始版，已吸收 Stage 3–8 设计资产约束）
- 根目录 `CLAUDE.md` — Claude Code 入口，正文以 `AGENTS.md` 为唯一权威
- 根目录 `.zcode/` — ZCode 项目配置（MCP + `rules/` 短指针；正文以 `AGENTS.md` 为准，禁止与 `.cursor/rules/` 各写一套）
- 根目录 `.cursor/` — Cursor 项目配置（MCP 与 rules，与 `.zcode/` 并列保留）
- 根目录 `.mcp.json` — Claude 兼容的 MCP 入口

---

## 本地教程（Stage 0 维护，非阶段约定输出）

面向「照着做就能在本地复现一次完整执行」的入门材料。**不属于上文的阶段约定输出**，增删不影响 Stage 0 的约定含义。新手按 `local-testing-guide.md` → `user-ui-guide.md` 的顺序读；要读代码的人再加 `developer-guide.md`。

| 文件 | 给谁看 | 内容 |
|---|---|---|
| `local-testing-guide.md` | 所有人（复现前提） | 从干净仓库起本地栈：`.env` 必填键、六步启动、两个合成账号与切身份、种子脚本实际写入什么、常见启动故障 |
| `user-ui-guide.md` | 普通用户 / 产品 / 测试 | 全程在 UI 里点：登录 → 建门禁策略 → A1 生成并采纳用例 → 提审 + 换账号审核 → 注册执行环境 + 四眼审批 → 发起执行 → 看状态机 / StepRun / 证据。含「失败怎么办」与覆盖范围表 |
| `developer-guide.md` | 前后端 / 测试开发 | 每个 UI 操作 → `API-NNN` / router / service / 数据表 / 错误码 → 对应的 `测试文件::用例名` 与单跑命令；含幂等键、CAS、Policy Gate、四眼、错误信封链路等横切原理 |
| `tutorial/index.html` | 想快速浏览的人 | 12 个模块的单页速览（HTML，浏览器直接打开） |

> 教程内引用的 `文件:行号` 与 `测试文件::用例名` 均取自当前仓库并逐一校验；如与代码不符，**以代码为准并提 issue 修文档**。

