# Stage 9 · 高保真设计说明与 Token

> - **阶段**：Stage 9（`docs/09_figma_highfi`）
> - **日期**：2026-09-12
> - **Status**：已产出（本轮无独立 Figma 文件；视觉权威 = 本文件 + `frontend/` 源码）
> - **代码基线**：layout 优化与 token 别名落在同次变更
> - **上游**： [frontend_design_spec-v1.0.md](../06_architecture_design/frontend_design_spec-v1.0.md)（页面 / 路由 / 分区顺序 / 七态 / 断点）· [problem_model.md](../03_problem_modeling/problem_model.md) §4.3 · `frontend/src/index.css`（色 / 字体 / 圆角的唯一色值源）
> - **不新增** 页面、导航项、状态、US / FR / API；**不调换** P08 / P09 / P10 分区顺序；**不发明** 未在 CSS 出现过的色值

## 1. 范围与交付

| 项 | 本轮 |
|---|---|
| 约定产出 | 本文 `highfi_design.md` |
| Figma 文件 | **不做**（确认：token 板 + 三关键帧留待后续） |
| 切图 / 导出资产 | 无独立 PNG；认证页截图依赖 mock IdP，compose 栈未含 IdP，**未登记二进制截图** |
| Layout 代码 | 全局壳、P01、P08、P09、P10（`ApprovalCard`）、共享 `PageHeader` / `StepMark` |

`templates/` 下订单审批示例**不是** HuntAI 内容，仅作填写规则参考。

## 2. Design Token

全部色值与字体摘自 `frontend/src/index.css` `@theme inline`。语义间距是对已有 Tailwind 档的别名，不是新 rem。

### 2.1 字体

| Token | 值 | 用途 |
|---|---|---|
| `--font-sans` | IBM Plex Sans, ui-sans-serif, system-ui | 正文、导航、标题 |
| `--font-mono` | IBM Plex Mono, ui-monospace | ID、哈希、成本、进度步号 |

字重：400 / 500 / 600 / 700（Sans）；400 / 500 / 600（Mono）。由 Google Fonts `@import` 加载。

### 2.2 色彩（表面与品牌）

| Token | Hex | 用途 |
|---|---|---|
| `--color-background` | `#f4f6f9` | 应用底 |
| `--color-foreground` | `#0f172a` | 主文字 |
| `--color-card` | `#ffffff` | 卡片 / 顶栏 |
| `--color-card-foreground` | `#0f172a` | 卡片文字 |
| `--color-popover` | `#ffffff` | 弹出层 |
| `--color-popover-foreground` | `#0f172a` | 弹出层文字 |
| `--color-primary` | `#1d4ed8` | 主按钮、激活描边、焦点环 |
| `--color-primary-foreground` | `#ffffff` | 主按钮文字 |
| `--color-secondary` | `#eef2f7` | 步号底、次按钮 |
| `--color-secondary-foreground` | `#334155` | 次级文字 |
| `--color-muted` | `#f1f5f9` | 弱底 |
| `--color-muted-foreground` | `#64748b` | 辅助说明 |
| `--color-accent` | `#eff6ff` | 选中层（模式卡 / 环境卡） |
| `--color-accent-foreground` | `#1e3a8a` | 强调文字 |
| `--color-destructive` | `#dc2626` | 拒绝、失效条、终止 |
| `--color-destructive-foreground` | `#ffffff` | 破坏性按钮文字 |
| `--color-border` | `#e2e8f0` | 边框、滚动条滑块 |
| `--color-input` | `#e2e8f0` | 输入边框 |
| `--color-ring` | `#1d4ed8` | 焦点环 |
| `--color-sidebar` | `#0b1220` | 一级导航底 |
| `--color-sidebar-foreground` | `#cbd5e1` | 侧栏默认文字 |
| `--color-sidebar-accent` | `#1e293b` | 侧栏激活 / 边 |
| `--color-sidebar-primary` | `#2563eb` | 侧栏品牌块、激活左边线 |

### 2.3 语义状态色

| Token | Hex | 用途 |
|---|---|---|
| `--color-success` | `#047857` | 成功、正向 diff「to」 |
| `--color-success-foreground` | `#ecfdf5` | 成功浅底 |
| `--color-warning` | `#b45309` | 降级横幅、只读提示、unknown 簇 |
| `--color-warning-foreground` | `#fffbeb` | 警告浅底 |
| `--color-info` | `#1d4ed8` | 信息 |
| `--color-info-foreground` | `#eff6ff` | 信息浅底 |

### 2.4 风险等级 L0–L4（冻结枚举，色标不得另造）

| 等级 | Token | Hex | 组件 |
|---|---|---|---|
| L0 | `--color-risk-l0` | `#475569` | `RiskBadge` |
| L1 | `--color-risk-l1` | `#2563eb` | 同上，浅底 `info-foreground` |
| L2 | `--color-risk-l2` | `#d97706` | 浅底 `warning-foreground` |
| L3 | `--color-risk-l3` | `#ea580c` | 浅底 `warning-foreground` |
| L4 | `--color-risk-l4` | `#dc2626` | 浅底 `destructive/10` |

### 2.5 圆角

| Token | 值 | 用途 |
|---|---|---|
| `--radius-sm` | `0.375rem` | 小控件 |
| `--radius` / `--radius-md` | `0.5rem` | 按钮、输入、侧栏项 |
| `--radius-lg` | `0.75rem` | 卡片 |

### 2.6 字号与间距（沿用 Tailwind，禁止新档）

| 语义 | 等价类 | 值 |
|---|---|---|
| 辅助 / 区标题 | `text-[10px]` / `text-xs` | 10px / `0.75rem` |
| 正文 | `text-sm` | `0.875rem` |
| 页标题 `--text-page-title` | `text-xl` | `1.25rem` |
| 工作台指标 | `text-2xl` | `1.5rem` |
| 卡片内边距 `--spacing-card` | `p-4` | `1rem` |
| 页边距 / 区块间距 `--spacing-page` `--spacing-section` | `p-6` / `gap-6` | `1.5rem` |
| 紧凑页边距（&lt;1280） | `p-4` | `1rem` |
| 内容最大宽 `--content-max` | `max-w-7xl` | `80rem` |
| 侧栏展开 / 图标 | `w-56` / `w-16` | `14rem` / `4rem` |
| 顶栏高 | `h-12` | `3rem` |

滚动条滑块映射到 `--color-border`，悬停 `--color-muted-foreground`（不再使用未登记 hex）。

### 2.7 聚类 7 值（只渲染已定义枚举）

标签文案在 `ClusterCard`：`env_down` 环境故障 · `auth_expired` 认证过期 · `locator_stale` 定位器过期 · `assertion_real_bug` 真实缺陷 · `flaky` 不稳定测试 · `data_issue` 数据问题 · `unknown` 未知（`Badge variant="warning"`，卡片 `border-warning/40`）。**不另配 7 套新色。**

## 3. 全局壳层

实现：`frontend/src/components/layout/AppLayout.tsx`。

```
┌──────── w-56 / w-16 ────────┬────────────── flex-1 ──────────────┐
│ 品牌 H + HuntAI Test        │ 顶栏 h-12：折叠 · 租户/用户 · AI 横幅 · 通知 · 退出 │
│ 一级导航 8 项（P18/P19 隐藏）│ ［只读条 &lt;1024］［再认证条］［二级 Subnav］ │
│                             │ main max-w-7xl gap-6 p-6/p-4      │
└─────────────────────────────┴───────────────────────────────────┘
```

- 一级导航（IA 10 项中当前可见 8）：工作台 / 项目 / 测试中心 / 门禁 / 发布 / 审批中心 / 证据 / 管理。助手 / 技能按里程碑隐藏。
- ≥1280：侧栏可手动折叠。1024–1279：**强制图标侧栏**（规范 §7）。&lt;1024：图标侧栏 + 只读黄条，命令按钮不出现。
- 顶栏租户 / 用户只渲染 API-005 `organization.name` 与 `user.display_name`。
- 通知铃对应缺口 G4；API-022 未开发时标明「通知未开发」，**不假装未读数**。审批待办徽标仍在「审批中心」项。
- AI 降级横幅：服务端 `capability_controls`，不静默。

## 4. 组件契约

| 组件 | 路径 | 变体 / 约束 |
|---|---|---|
| Button | `components/ui/button.tsx` | default / destructive / outline / secondary / ghost / link；sm / default / lg / icon |
| Badge | `components/ui/badge.tsx` | default / secondary / outline / success / warning / destructive / info |
| Card | `components/ui/card.tsx` | Header 底边、Content `p-4` |
| PageHeader | `PageState.tsx` | `text-xl` 标题；`actions` 在 `canMutate=false` 时不渲染 |
| StepMark | `PageState.tsx` | 步号 1–3，P08 三层与 P09 四区共用 |
| EmptyState / LoadingState / ErrorState | `PageState.tsx` | 七态：空 / 加载 / 错误；无权限走 `ApiError.kind=permission`；404 文案「资源不存在」 |
| StatusBadge | `domain/StatusBadge.tsx` | 服务端状态字符串，前端不推演 |
| RiskBadge | `domain/RiskBadge.tsx` | 仅 L0–L4 token |
| ApprovalCard | `domain/ApprovalCard.tsx` | 区序冻结，见 §5.2 |
| ClusterCard | `domain/ClusterCard.tsx` | 五要素 + 7 值枚举 |
| RunProgressBar | `domain/RunProgressBar.tsx` | TestRun 10 态 |
| EvidenceViewer | `domain/EvidenceViewer.tsx` | 截图 / 视频 / Trace |
| AiDegradeBanner | `domain/AiDegradeBanner.tsx` | 全局 + 聚类区局部 |

shadcn 源码内置，禁止改为 npm 包或换成 Ant / MUI。

## 5. 三个关键页（分区顺序冻结）

### 5.1 P08 执行发起

顺序不可调换：**项目选择（数据前置）→ ① 模式 Script/Agent → ② 环境（仅 selectable）→ ③ 参数 → 发起执行。**

实现：`ExecutionLaunchPage.tsx` 三个 `Layer` + `StepMark`。Agent 受限说明仍在模式层。&lt;1024 隐藏「发起执行」，表单可看。

### 5.2 P09 TestRun 详情

顺序：**页头 10 态进度条 → 聚类报告区 → 用例结果表 → 证据查看器。** `execution_source` 徽标挂在进度区，不插入新分区。WAITING_APPROVAL 高亮跳 P10。等待态不得因耗时隐藏。

### 5.3 P10 审批卡片

`data-zone` 顺序必须为：`invalid`（若有）→ `1` 动作与目标 → `2` diff → `3` 来源与模型 → `4` 风险+成本 → `5` 回滚 → `6` 参数哈希（默认折叠）→ `actions`。测试 `ApprovalCard.test.tsx` 钉住。&lt;1024 保留区序，操作区只出示只读说明。

## 6. 页面布局清单（P01–P25）

路由权威：前端规范 §3 与 `App.tsx`。下表只记 **壳 + 内容列**，不改 IA。

| 编号 | 布局要点 |
|---|---|
| P01 工作台 | 页头 + 指标 `1 / lg:2 / xl:4` 列 + 待审批/进行中列表 `1 / xl:2` 列。WAITING_* 滞留秒数原样展示 |
| P02 项目总览 | 卡片网格 `1 / md:2 / lg:3` |
| P03 集成 | 项目级绑定表 + 未开发/空态 |
| P04 项目设置 | 成员与角色表单 |
| P05 用例库 | 筛选进 URL 的表；&lt;1024 可横滑 |
| P06 测试计划 | 列表 + 表单两列（md） |
| P07 生成审阅 | 左右分栏 `lg:grid-cols-2`；partial 失败列表不得静默 |
| P08 | §5.1 |
| P09 列表 | 筛选进 URL 的表 |
| P09 详情 | §5.2 |
| P10 | 左队列 + 右卡片 `lg:grid-cols-[minmax(16rem,22rem)_1fr]`；§5.3 |
| P11 / P12 | 策略表单 / 评估表 |
| P13 | 定位器主备与版本区 |
| P14 | 轨迹时间线纵向 |
| P15 | 环境表 + 健康 |
| P16 | 压测表单 md 两列；白名单 DENY 提示 |
| P17 | 范围栏 + 就绪度 `lg:grid-cols-[18rem_1fr]` |
| P18 / P19 | 里程碑前无一级入口；页内占位不启用写操作 |
| P20 | 检索 + 证据包；筛选进 URL |
| P21 | 指标四卡，对齐 P01 网格 |
| P22 / P23 | 配置表 + 关停横幅以后端为准 |
| P24 | 审计检索表，筛选进 URL |
| P25 | 组织级连接器 / Token；明文仅签发当次 |

## 7. 七态与断点

全部页面覆盖：默认 / 加载 / 空数据 / 无结果 / 错误 / 无权限 / 成功。列表筛选、排序、分页进 URL。

| 视口 | 行为 |
|---|---|
| ≥1280px | 全功能；侧栏可折叠 |
| 1024–1279px | 可用；侧栏图标；P01 指标最多两列 |
| &lt;1024px | **只读浏览**；命令（发起 / 批准 / 拒绝 / 终止）不提供；语义与桌面一致 |

实现：`useViewport`（`frontend/src/hooks/useViewport.ts`）。无 `matchMedia` 的测试默认走 Context 的 desktop（`canMutate=true`）。

## 8. 资产登记

| 文件 | 来源 |
|---|---|
| 本文 | Stage 9 约定产出 |
| `frontend/src/index.css` | token 色值源 |
| — | 本轮无 PNG / SVG 切图；无 Figma 链接 |

登录后的界面截图待 mock IdP 与浏览器同机后再补，不把未拍摄的文件登记为已有。
