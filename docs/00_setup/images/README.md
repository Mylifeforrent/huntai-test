# 教程截图（`docs/00_setup/images/`）

本目录存放 [`user-ui-guide.md`](../user-ui-guide.md) 与 [`local-testing-guide.md`](../local-testing-guide.md) 引用的界面截图。

## 这些图是什么

- **来源**：一次真实的端到端走查。截图脚本按 `user-ui-guide.md` 的顺序，在本地实例上操作真实 UI，走到哪一步就地截图。
- **不是**：示意图、设计稿、拼凑的合成图。页面标题、按钮文字、字段名、空态与报错都来自真实运行的实例。
- **标注**：图上的红色描边框与 ① ② ③ 角标，是截图时**在页面上注入的 overlay**（描边 div + 编号角标），界面本身没有被改动。图下 `>` 引用块里的编号与角标一一对应。

## 拍摄环境

| 项 | 值 |
| --- | --- |
| 浏览器 | 本机 Google Chrome（Playwright 1.62，`channel="chrome"`，headless） |
| 视口 | 1440×900，`deviceScaleFactor=1` |
| 语言 | `zh-CN` |
| 格式 | PNG |
| 数据 | 干净库：只跑过 `scripts/seed_local_identity.py`，没有客户演示数据 |

> Playwright 复用 `frontend/node_modules` 里已声明的版本，**没有新增任何依赖**；Playwright 自带的 Chromium 未安装，所以走系统 Chrome 的 `channel="chrome"`。

## 文件名规则

`<章节号>-<序号>-<语义>.png`，与教程小节一一对应：

| 前缀 | 对应 `user-ui-guide.md` |
| --- | --- |
| `1.1-` … `1.3-` | §1 登录、认路与切身份 |
| `2.1-` … `2.5-` | §2 数据准备 |
| `3.1-` … `3.5-` | §3 跑一次并看结果 |
| `4-` | §4 审批中心与九要素卡片 |
| `7-` | §7 质量闭环扩展（Jira / Release / 可选 Jenkins）；`7-a-p25-connectors.png` … `7-g-release-ready.png` 已入库 |

其中 `1.1-a-idp-login.png` 与 `1.3-a-switch-account.png` 同时被 `local-testing-guide.md` §4 复用，不重复存两份。

## 重拍方法

1. **复位到干净种子态**（清掉上次走查产生的策略 / 用例 / 环境 / TestRun）：

   ```bash
   cd backend
   uv run python scripts/reset_local_data.py --yes
   ```

   一条命令完成：清空本项目 schema 下的业务表并重跑身份种子，不动库结构（`alembic_version` 不受影响）。完整说明见 [`../local-testing-guide.md`](../local-testing-guide.md) §6.1。

2. **起齐四件套**（见 [`../local-testing-guide.md`](../local-testing-guide.md) §3）：mock IdP(8090) + mock 集成(8091) + 后端(8000) + 前端(5173)。

3. **补齐 §2 教程数据**（公开 API，不写 SQL）：门禁策略、ACTIVE 用例、名为「本地教程环境」的 ACTIVE 执行环境。

   ```bash
   cd backend
   uv run python scripts/bootstrap_tutorial_assets.py
   ```

   也可按 [`user-ui-guide.md`](../user-ui-guide.md) §2 在浏览器里手工造数。截图脚本本身不造数。

4. **用 Playwright 按教程顺序走查并截图**：

   **§7 质量闭环**（`feat/local-integration-mocks`）：

   ```bash
   cd backend
   node scripts/capture_tutorial_screenshots.mjs
   ```

   脚本复用 `frontend/node_modules/playwright`（`channel: "chrome"`，headless），视口 1440×900、`zh-CN`；截图前在页面上注入红色描边框与 ① ② ③ 角标。前置须已完成 §2–§3 教程数据（策略 / 用例 / 环境），且四件套（8090 / 8091 / 8000 / 5173）均已启动；缺数据或进程未起时以中文报错 exit 1。本机须安装 Google Chrome（未安装时 exit 2）。

   §7 产出：`7-a-p25-connectors.png` … `7-g-release-ready.png`（见 [`user-ui-guide.md`](../user-ui-guide.md) §7）。

   §1–§5 仍按 [`user-ui-guide.md`](../user-ui-guide.md) 手工走查；登录片段示意：

   ```js
   const { chromium } = require("playwright"); // 复用 frontend/node_modules，无需安装
   const browser = await chromium.launch({ channel: "chrome", headless: true });
   const ctx = await browser.newContext({
     viewport: { width: 1440, height: 900 },
     locale: "zh-CN",
   });
   const page = await ctx.newPage();

   await page.goto("http://127.0.0.1:5173/");
   await page.waitForURL(/127\.0\.0\.1:8090\/authorize/);
   await page.fill('input[name="username"]', "local-dev-user");
   await page.fill('input[name="password"]', "local-dev");
   await page.click('button[type="submit"]');

   await page.screenshot({ path: "docs/00_setup/images/<章节号>-<序号>-<语义>.png" });
   ```

> 走查顺序不能乱：**门禁策略 → 用例（生成 / 评审）→ 执行环境（四眼审批）→ 发起执行**。每一步的真实状态都依赖上一步，跳过就会拍到空态。

## 注意

- 截图里会出现本地生成的 UUID（项目 / 审批 / TestRun）与本地租户名。这些都是本地种子数据，不是生产数据，也不含任何密钥。
- 界面改版后请**重拍**，不要修图：图上的标注与教程文案必须继续与真实界面对应。
