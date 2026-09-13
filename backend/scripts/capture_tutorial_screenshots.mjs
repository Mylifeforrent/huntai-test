#!/usr/bin/env node
/**
 * §7 质量闭环教程截图（本地开发专用）
 *
 * 前置（四进程必须全部就绪）：
 *   - mock IdP      http://127.0.0.1:8090
 *   - mock 集成     http://127.0.0.1:8091
 *   - 后端 API      http://127.0.0.1:8000
 *   - 前端 Vite     http://127.0.0.1:5173
 *
 * 数据：已跑 seed_local_identity.py，且按 user-ui-guide §2–§3 完成
 *   门禁策略、ACTIVE 用例、名为「本地教程环境」的 ACTIVE 执行环境
 *   （可用 `uv run python scripts/bootstrap_tutorial_assets.py` 经公开 API 造数）。
 * 本脚本不会通过 SQL 造数；缺数据时以中文报错并 exit 1。
 *
 * 运行（在 backend/ 目录）：
 *   node scripts/capture_tutorial_screenshots.mjs
 *
 * 依赖：复用 frontend/node_modules/playwright（channel: chrome，无新增 npm 包）。
 * 若本机未安装 Google Chrome，脚本 exit 2 并提示安装 Chrome。
 */

import { randomUUID } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "../../frontend/node_modules/playwright/index.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../..");
const IMAGES_DIR = path.join(REPO_ROOT, "docs/00_setup/images");

const FRONTEND = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8000";
const IDP = "http://127.0.0.1:8090";
const MOCK = "http://127.0.0.1:8091";

const PROJECT_ID = "00000000-0000-4000-8000-000000000003";
const JIRA_VERSION = "1.0.0";
const RELEASE_CONNECTOR_ID = "00000000-0000-4000-8000-000000000013";
const ENV_TUTORIAL_NAME = "本地教程环境";
const PASSWORD = "local-dev";

const SCREENSHOTS = {
  p25: "7-a-p25-connectors.png",
  failedRun: "7-b-failed-run.png",
  jiraCluster: "7-c-jira-cluster.png",
  jiraApproval: "7-d-jira-approval.png",
  releaseCreate: "7-e-release-create.png",
  releasePush: "7-f-release-push.png",
  releaseReady: "7-g-release-ready.png",
};

/** @type {import('playwright').Browser | null} */
let browser = null;

function die(message) {
  console.error(`\n❌ ${message}\n`);
  process.exit(1);
}

function softExit(message) {
  console.warn(`\n⚠️  ${message}\n`);
  process.exit(2);
}

async function probe(url, label) {
  try {
    const response = await fetch(url, { redirect: "follow" });
    if (!response.ok) {
      die(`${label} 未就绪（${url} 返回 HTTP ${response.status}）。请先按 local-testing-guide.md §3 启动四件套。`);
    }
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    die(`${label} 无法连接（${url}）：${detail}。请先按 local-testing-guide.md §3 启动四件套。`);
  }
}

async function assertStackUp() {
  await probe(`${IDP}/.well-known/openid-configuration`, "mock IdP (8090)");
  await probe(`${MOCK}/healthz`, "mock 集成 (8091)");
  await probe(`${API}/healthz`, "后端 API (8000)");
  await probe(`${FRONTEND}/`, "前端 (5173)");
}

/**
 * @param {import('playwright').Page} page
 * @param {string} username
 */
async function login(page, username) {
  await page.goto(`${FRONTEND}/`);
  await page.waitForURL(/127\.0\.0\.1:8090\/authorize/, { timeout: 30_000 });
  await page.fill('input[name="username"]', username);
  await page.fill('input[name="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL(/127\.0\.0\.1:5173/, { timeout: 30_000 });
  await page.waitForSelector("nav", { timeout: 15_000 });
}

/**
 * @param {import('playwright').Page} page
 * @param {string} username
 */
async function switchAccount(page, username) {
  await page.goto(`${IDP}/switch-account`);
  await page.context().clearCookies();
  await login(page, username);
}

/**
 * @param {import('playwright').APIRequestContext} request
 */
async function verifyTutorialData(request) {
  const policies = await request.get(
    `${API}/api/v1/quality-gate-policies?project_id=${PROJECT_ID}`,
  );
  if (!policies.ok()) {
    die(`无法读取门禁策略（HTTP ${policies.status()}）。请确认已登录且后端正常。`);
  }
  const policyItems = (await policies.json()).data?.items ?? [];
  if (policyItems.length === 0) {
    die(
      "缺少质量门禁策略。请先按 user-ui-guide.md §2.1 创建策略，或运行 reset_local_data.py 后重做 §2。",
    );
  }

  const cases = await request.get(`${API}/api/v1/test-cases?project_id=${PROJECT_ID}`);
  if (!cases.ok()) {
    die(`无法读取用例列表（HTTP ${cases.status()}）。`);
  }
  const activeCases = ((await cases.json()).data?.items ?? []).filter(
    (row) => row.lifecycle_status === "ACTIVE",
  );
  if (activeCases.length === 0) {
    die(
      "缺少 ACTIVE 用例。请先按 user-ui-guide.md §2.2–§2.3 生成并采纳用例，或运行 reset_local_data.py 后重做 §2。",
    );
  }

  const envs = await request.get(
    `${API}/api/v1/execution-environments?project_id=${PROJECT_ID}`,
  );
  if (!envs.ok()) {
    die(`无法读取执行环境（HTTP ${envs.status()}）。`);
  }
  const tutorialEnv = ((await envs.json()).data?.items ?? []).find(
    (row) => row.name === ENV_TUTORIAL_NAME && row.status === "ACTIVE",
  );
  if (!tutorialEnv) {
    die(
      `缺少 ACTIVE 执行环境「${ENV_TUTORIAL_NAME}」。请先按 user-ui-guide.md §2.4 注册环境并完成四眼审批。`,
    );
  }

  return {
    caseId: String(activeCases[0].id),
    envId: String(tutorialEnv.id),
  };
}

/**
 * @param {import('playwright').Page} page
 * @param {{ locator: import('playwright').Locator; label: string }[]} callouts
 */
async function injectCallouts(page, callouts) {
  const boxes = [];
  for (const item of callouts) {
    await item.locator.waitFor({ state: "visible", timeout: 20_000 });
    const box = await item.locator.boundingBox();
    if (!box) {
      throw new Error(`标注目标不可见：${item.label}`);
    }
    boxes.push({ ...box, label: item.label });
  }

  await page.evaluate((items) => {
    const style = document.createElement("style");
    style.id = "huntai-screenshot-overlay-style";
    style.textContent = `
      #huntai-screenshot-overlay-root {
        position: fixed;
        inset: 0;
        pointer-events: none;
        z-index: 2147483646;
      }
      .huntai-callout-box {
        position: absolute;
        border: 3px solid #e11d48;
        border-radius: 4px;
        box-shadow: 0 0 0 1px rgba(225, 29, 72, 0.35);
      }
      .huntai-callout-badge {
        position: absolute;
        min-width: 26px;
        height: 26px;
        padding: 0 6px;
        border-radius: 999px;
        background: #e11d48;
        color: #fff;
        font: bold 14px/26px "PingFang SC", "Microsoft YaHei", sans-serif;
        text-align: center;
        transform: translate(-40%, -40%);
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.25);
      }
    `;
    document.head.appendChild(style);

    const root = document.createElement("div");
    root.id = "huntai-screenshot-overlay-root";
    for (const { x, y, width, height, label } of items) {
      const pad = 4;
      const outline = document.createElement("div");
      outline.className = "huntai-callout-box";
      outline.style.left = `${x - pad}px`;
      outline.style.top = `${y - pad}px`;
      outline.style.width = `${width + pad * 2}px`;
      outline.style.height = `${height + pad * 2}px`;

      const badge = document.createElement("div");
      badge.className = "huntai-callout-badge";
      badge.textContent = label;
      badge.style.left = `${x}px`;
      badge.style.top = `${y}px`;

      root.appendChild(outline);
      root.appendChild(badge);
    }
    document.body.appendChild(root);
  }, boxes);
}

/** @param {import('playwright').Page} page */
async function removeCallouts(page) {
  await page.evaluate(() => {
    document.getElementById("huntai-screenshot-overlay-root")?.remove();
    document.getElementById("huntai-screenshot-overlay-style")?.remove();
  });
}

/**
 * @param {import('playwright').Page} page
 * @param {string} filename
 * @param {{ locator: import('playwright').Locator; label: string }[]} callouts
 */
async function capture(page, filename, callouts = []) {
  const target = path.join(IMAGES_DIR, filename);
  if (callouts.length > 0) {
    await injectCallouts(page, callouts);
  }
  await page.screenshot({ path: target, fullPage: false });
  if (callouts.length > 0) {
    await removeCallouts(page);
  }
  console.log(`  ✓ ${filename}`);
}

/**
 * @param {import('playwright').Page} page
 * @param {string} wantedLabel
 * @param {string} wantedStatus
 */
async function waitForTerminalRun(page, wantedLabel, wantedStatus) {
  const runId = new URL(page.url()).pathname.split("/").filter(Boolean).at(-1);
  if (!runId) {
    throw new Error("无法从 URL 读取 TestRun id");
  }
  const deadline = Date.now() + 90_000;
  let last = "";
  while (Date.now() < deadline) {
    const response = await page.request.get(`${API}/api/v1/test-runs/${runId}`);
    if (!response.ok()) {
      throw new Error(`读取 TestRun 失败（HTTP ${response.status()}）`);
    }
    last = String((await response.json()).data?.status ?? "");
    if (last === wantedStatus) {
      await page.goto(`${FRONTEND}/test-center/runs/${runId}`);
      await page.getByText(wantedLabel).first().waitFor({ timeout: 15_000 });
      return;
    }
    await page.waitForTimeout(400);
  }
  throw new Error(`TestRun 未进入 ${wantedStatus}（最后状态：${last || "空"}）`);
}

/**
 * @param {string} taskId
 */
async function emitReleaseReadyWebhook(taskId) {
  const body = {
    huntai_base: API,
    connector_id: RELEASE_CONNECTOR_ID,
    event: "release_item_ready",
    delivery_id: randomUUID(),
    body: {
      release_task_id: taskId,
      external_item_id: "RI-TUTORIAL-7G",
      status: "ready",
    },
  };
  const response = await fetch(`${MOCK}/dev/emit-webhook`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`emit-webhook 失败（HTTP ${response.status}）：${text.slice(0, 200)}`);
  }
  const payload = await response.json();
  if (!payload.delivered) {
    throw new Error("emit-webhook 未投递成功");
  }
}

/**
 * @param {import('playwright').APIRequestContext} request
 * @param {string} taskId
 * @param {string} wanted
 */
async function waitForTaskStatus(request, taskId, wanted) {
  const deadline = Date.now() + 60_000;
  let last = "";
  while (Date.now() < deadline) {
    const response = await request.get(`${API}/api/v1/release-tasks/${taskId}`);
    if (!response.ok()) {
      throw new Error(`读取 Release 任务失败（HTTP ${response.status()}）`);
    }
    last = String((await response.json()).data?.status ?? "");
    if (last === wanted) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  throw new Error(`Release 任务未进入 ${wanted}（最后状态：${last || "空"}）`);
}

/**
 * @param {import('playwright').Page} page
 * @param {string} taskId
 */
async function waitForReleaseReady(page, taskId) {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    await page.goto(
      `${FRONTEND}/releases?projectId=${PROJECT_ID}&jiraVersionRef=${JIRA_VERSION}&id=${taskId}`,
    );
    const text = await page.locator("body").innerText();
    if (text.includes("就绪") || text.includes("READY")) {
      return;
    }
    await page.waitForTimeout(750);
  }
  throw new Error("Release 任务未在时限内进入 READY");
}

/**
 * @param {import('playwright').Page} page
 * @param {string} actionType
 */
async function openPendingApproval(page, actionType) {
  await page.goto(`${FRONTEND}/approvals?tab=queue&perspective=inbox&action_type=${actionType}`);
  await page.getByRole("tab", { name: "待处理队列" }).click();
  const row = page
    .locator("button")
    .filter({ hasText: actionType })
    .filter({ hasText: "待处理" })
    .first();
  await row.waitFor({ state: "visible", timeout: 30_000 });
  await row.click();
  await page.locator('[data-testid="approval-card"]').waitFor({ state: "visible" });
}

async function main() {
  console.log("§7 质量闭环教程截图");
  console.log("检查四件套…");
  await assertStackUp();

  fs.mkdirSync(IMAGES_DIR, { recursive: true });

  try {
    browser = await chromium.launch({ channel: "chrome", headless: true });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    softExit(
      `无法启动 Google Chrome（channel: chrome）：${detail}\n` +
        "请安装 Chrome 后重试；Playwright 自带 Chromium 未安装，本脚本刻意走系统 Chrome。",
    );
  }

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    locale: "zh-CN",
  });
  const page = await context.newPage();

  try {
    console.log("登录 local-dev-user 并校验 §2/§3 教程数据…");
    await login(page, "local-dev-user");
    const assets = await verifyTutorialData(page.request);

    console.log("7-a 集成中心（P25）…");
    await page.goto(`${FRONTEND}/admin/integrations`);
    await page.getByRole("heading", { name: "集成中心" }).waitFor();
    await page.getByRole("tab", { name: "连接器" }).click();
    await capture(page, SCREENSHOTS.p25, [
      { locator: page.getByRole("heading", { name: "集成中心" }), label: "①" },
      {
        locator: page.locator('[role="tabpanel"]').locator(".rounded-md.border").first(),
        label: "②",
      },
      { locator: page.getByText("Local mock Jira", { exact: false }).first(), label: "③" },
    ]);

    console.log("发起 FAILED TestRun（TARGET_ENV → 8091）…");
    await page.goto(
      `${FRONTEND}/test-center/kickoff?projectId=${PROJECT_ID}&caseId=${assets.caseId}`,
    );
    await page.getByRole("button", { name: "Script Mode" }).click();
    await page.getByRole("button", { name: ENV_TUTORIAL_NAME }).click();
    await page.locator("#target-env").fill(`${MOCK}`);
    const caseCheckbox = page.getByRole("checkbox").first();
    await caseCheckbox.waitFor({ state: "visible", timeout: 20_000 });
    if ((await caseCheckbox.getAttribute("data-state")) !== "checked") {
      await caseCheckbox.click();
    }
    await page.getByRole("button", { name: "发起执行" }).click();
    await page.waitForURL(/\/test-center\/runs\//, { timeout: 30_000 });

    console.log("7-b FAILED TestRun 详情…");
    await waitForTerminalRun(page, "失败", "FAILED");
    await capture(page, SCREENSHOTS.failedRun, [
      { locator: page.getByText("执行进度").first(), label: "①" },
      { locator: page.getByText("失败").first(), label: "②" },
      { locator: page.getByText("聚类报告区").first(), label: "③" },
    ]);

    console.log("等待聚类与 Jira 按钮…");
    const jiraButton = page.getByRole("button", { name: "一键创建 Jira 缺陷" });
    await jiraButton.waitFor({ state: "visible", timeout: 60_000 });

    console.log("7-c 失败聚类 + Jira 按钮…");
    await capture(page, SCREENSHOTS.jiraCluster, [
      { locator: page.getByText("聚类报告区").first(), label: "①" },
      { locator: jiraButton, label: "②" },
      { locator: page.getByText("用例结果表").first(), label: "③" },
    ]);

    await jiraButton.click();
    await page.waitForURL(/\/approvals/, { timeout: 20_000 });

    console.log("切换 local-dev-user-2 审批 jira_write…");
    await switchAccount(page, "local-dev-user-2");
    await openPendingApproval(page, "jira_write");

    console.log("7-d jira_write 审批卡片…");
    await capture(page, SCREENSHOTS.jiraApproval, [
      { locator: page.locator('[data-zone="1"]').first(), label: "①" },
      { locator: page.getByRole("button", { name: "批准" }), label: "②" },
      { locator: page.locator('[data-zone="4"]').first(), label: "③" },
    ]);
    await page.getByRole("button", { name: "批准" }).click();
    await page.waitForTimeout(1500);

    console.log("切回 local-dev-user，创建 Release 任务…");
    await switchAccount(page, "local-dev-user");
    await page.goto(
      `${FRONTEND}/releases?projectId=${PROJECT_ID}&jiraVersionRef=${JIRA_VERSION}`,
    );
    await page.getByLabel("项目 ID").waitFor();

    console.log("7-e Release 圈定表单…");
    await capture(page, SCREENSHOTS.releaseCreate, [
      { locator: page.getByLabel("项目 ID"), label: "①" },
      { locator: page.getByLabel("Jira 版本号"), label: "②" },
      { locator: page.getByRole("button", { name: "圈定版本创建（API-152）" }), label: "③" },
    ]);

    await page.getByRole("button", { name: "圈定版本创建（API-152）" }).click();
    await page.waitForURL(/[?&]id=/, { timeout: 30_000 });
    const createdTaskId = new URL(page.url()).searchParams.get("id");
    if (!createdTaskId) {
      throw new Error("未能从 URL 读取 release task id（?id=）");
    }
    await waitForTaskStatus(page.request, createdTaskId, "PENDING_CONFIRM");
    await page.goto(
      `${FRONTEND}/releases?projectId=${PROJECT_ID}&jiraVersionRef=${JIRA_VERSION}&id=${createdTaskId}`,
    );
    await page.getByRole("button", { name: "发起 release_push 审批" }).waitFor({
      timeout: 15_000,
    });

    console.log("7-f PENDING_CONFIRM + release_push 按钮…");
    await capture(page, SCREENSHOTS.releasePush, [
      { locator: page.getByText("待确认").first(), label: "①" },
      { locator: page.getByRole("button", { name: "发起 release_push 审批" }), label: "②" },
      { locator: page.getByText("范围快照（创建后不可变）").first(), label: "③" },
    ]);

    await page.getByRole("button", { name: "发起 release_push 审批" }).click();
    const dialog = page.getByRole("alertdialog");
    await dialog.waitFor({ state: "visible" });
    await dialog.getByRole("button", { name: "发起审批" }).click();
    await page.waitForTimeout(1500);

    const taskId = new URL(page.url()).searchParams.get("id");
    if (!taskId) {
      throw new Error("未能从 URL 读取 release task id（?id=）");
    }

    console.log("切换 admin 批准 release_push…");
    await switchAccount(page, "local-dev-user-2");
    await openPendingApproval(page, "release_push");
    await page.getByRole("button", { name: "批准" }).click();
    await page.waitForTimeout(2000);

    console.log("emit-webhook → READY…");
    await emitReleaseReadyWebhook(taskId);
    await switchAccount(page, "local-dev-user");
    await waitForReleaseReady(page, taskId);

    console.log("7-g Release READY…");
    await capture(page, SCREENSHOTS.releaseReady, [
      { locator: page.getByText("Readiness Gate", { exact: true }), label: "①" },
      { locator: page.getByText("就绪", { exact: true }).first(), label: "②" },
      { locator: page.getByText("范围快照（创建后不可变）").first(), label: "③" },
    ]);

    console.log(`\n完成：${Object.values(SCREENSHOTS).length} 张 PNG 已写入 ${IMAGES_DIR}\n`);
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  if (browser) {
    void browser.close();
  }
  die(`截图流程失败：${message}`);
});
