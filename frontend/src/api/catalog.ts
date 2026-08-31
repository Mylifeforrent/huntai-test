export interface ApiDescriptor {
  id: string;
  method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  path: string;
  summary: string;
}

/** Page → required APIs. Paths follow api_spec.md §6. */
export const PAGE_APIS = {
  P01: [
    { id: "API-020", method: "GET", path: "/api/v1/workbench", summary: "工作台聚合" },
    { id: "API-017", method: "GET", path: "/api/v1/org-quotas/current", summary: "配额余量" },
    { id: "API-022", method: "GET", path: "/api/v1/notifications/badge", summary: "未读角标" },
  ],
  P02: [{ id: "API-012", method: "GET", path: "/api/v1/projects/{project_id}", summary: "项目总览" }],
  P03: [
    { id: "API-160", method: "GET", path: "/api/v1/connectors", summary: "连接器列表" },
    { id: "API-167", method: "PUT", path: "/api/v1/projects/{project_id}/ci-trigger-bindings", summary: "CI 触发绑定" },
  ],
  P04: [
    { id: "API-013", method: "GET", path: "/api/v1/projects/{project_id}/members", summary: "成员列表" },
    { id: "API-018", method: "GET", path: "/api/v1/projects/{project_id}/quota-view", summary: "项目配额" },
    { id: "API-019", method: "GET", path: "/api/v1/projects/{project_id}/notification-subscriptions", summary: "通知订阅" },
  ],
  P04_members: [
    { id: "API-013", method: "GET", path: "/api/v1/projects/{project_id}/members", summary: "成员列表" },
    { id: "API-014", method: "POST", path: "/api/v1/projects/{project_id}/members", summary: "添加成员" },
    { id: "API-015", method: "PATCH", path: "/api/v1/projects/{project_id}/members/{user_id}", summary: "变更角色" },
    { id: "API-016", method: "DELETE", path: "/api/v1/projects/{project_id}/members/{user_id}", summary: "移除成员" },
  ],
  P04_quota: [{ id: "API-018", method: "GET", path: "/api/v1/projects/{project_id}/quota-view", summary: "项目配额" }],
  P04_notify: [
    {
      id: "API-019",
      method: "GET",
      path: "/api/v1/projects/{project_id}/notification-subscriptions",
      summary: "通知订阅",
    },
  ],
  P05: [
    { id: "API-030", method: "GET", path: "/api/v1/test-cases", summary: "用例列表" },
    { id: "API-200", method: "POST", path: "/api/v1/test-cases/imports", summary: "Excel 导入" },
    { id: "API-202", method: "POST", path: "/api/v1/test-cases/exports", summary: "Excel 导出" },
  ],
  P06: [{ id: "API-050", method: "GET", path: "/api/v1/test-plans", summary: "测试计划" }],
  P07: [
    { id: "API-180", method: "POST", path: "/api/v1/ai/generations", summary: "A1 生成受理" },
    { id: "API-182", method: "GET", path: "/api/v1/ai/generations/{generation_id}/drafts", summary: "结构化草稿" },
  ],
  P08: [
    { id: "API-011", method: "GET", path: "/api/v1/projects", summary: "项目列表" },
    { id: "API-069", method: "GET", path: "/api/v1/projects/{project_id}/execution-options", summary: "执行选项" },
    { id: "API-062", method: "POST", path: "/api/v1/test-runs", summary: "发起执行" },
    { id: "API-070", method: "GET", path: "/api/v1/execution-environments/{environment_id}/jobs/{job_id}/params-schema", summary: "Job 参数 Schema" },
  ],
  P09: [
    { id: "API-060", method: "GET", path: "/api/v1/test-runs", summary: "TestRun 列表" },
    { id: "API-061", method: "GET", path: "/api/v1/test-runs/{test_run_id}", summary: "TestRun 详情" },
    { id: "API-064", method: "GET", path: "/api/v1/test-runs/{test_run_id}/case-results", summary: "用例结果" },
    { id: "API-130", method: "GET", path: "/api/v1/test-runs/{test_run_id}/failure-clusters", summary: "聚类报告" },
    { id: "API-210", method: "GET", path: "/api/v1/test-runs/{test_run_id}/events", summary: "SSE 进度" },
    { id: "API-063", method: "POST", path: "/api/v1/test-runs/{test_run_id}/cancel", summary: "终止" },
  ],
  P10: [
    { id: "API-110", method: "GET", path: "/api/v1/approval-requests", summary: "审批队列" },
    { id: "API-112", method: "POST", path: "/api/v1/approval-requests/{approval_request_id}/decisions", summary: "批准/拒绝" },
    { id: "API-113", method: "POST", path: "/api/v1/approval-requests/{approval_request_id}/resubmissions", summary: "修改后重新提交" },
  ],
  P11: [{ id: "API-140", method: "GET", path: "/api/v1/quality-gate-policies", summary: "门禁策略" }],
  P12: [{ id: "API-144", method: "GET", path: "/api/v1/gate-evaluations", summary: "门禁评估历史" }],
  P13: [
    { id: "API-031", method: "GET", path: "/api/v1/test-cases/{test_case_id}", summary: "用例详情" },
    { id: "API-037", method: "GET", path: "/api/v1/test-cases/{test_case_id}/versions", summary: "版本历史" },
  ],
  P14: [
    { id: "API-067", method: "GET", path: "/api/v1/test-runs/{test_run_id}/trajectory", summary: "Agent 轨迹" },
    { id: "API-063", method: "POST", path: "/api/v1/test-runs/{test_run_id}/cancel", summary: "终止信号" },
    { id: "API-068", method: "POST", path: "/api/v1/test-runs/{test_run_id}/script-drafts", summary: "转脚本草稿" },
  ],
  P15: [
    { id: "API-100", method: "GET", path: "/api/v1/execution-environments", summary: "环境列表" },
    { id: "API-102", method: "POST", path: "/api/v1/execution-environments", summary: "环境注册" },
    { id: "API-120", method: "POST", path: "/api/v1/action-previews", summary: "Policy Gate Preview" },
  ],
  P16: [
    { id: "API-056", method: "GET", path: "/api/v1/perf-baselines", summary: "性能基线" },
    { id: "API-199", method: "POST", path: "/api/v1/organizations/current/capability-controls/tighten", summary: "kill switch 关停" },
  ],
  P17: [
    { id: "API-150", method: "GET", path: "/api/v1/release-tasks", summary: "Release 任务" },
    { id: "API-155", method: "GET", path: "/api/v1/release-tasks/{release_task_id}/readiness", summary: "Readiness Gate" },
  ],
  P18: [{ id: "API-190", method: "GET", path: "/api/v1/copilot-sessions", summary: "Copilot 会话" }],
  P19: [{ id: "API-194", method: "GET", path: "/api/v1/skills", summary: "技能列表" }],
  P20: [
    { id: "API-026", method: "GET", path: "/api/v1/evidence-objects", summary: "证据检索" },
    { id: "API-028", method: "POST", path: "/api/v1/evidence-objects/export-packages", summary: "证据包导出" },
  ],
  P21: [{ id: "API-183", method: "GET", path: "/api/v1/ai/cost-dashboard", summary: "AI 成本看板" }],
  P22: [
    { id: "API-196", method: "GET", path: "/api/v1/model-routes", summary: "模型路由" },
    { id: "API-198", method: "POST", path: "/api/v1/model-routes/{model_route_id}/connection-tests", summary: "测试连接" },
  ],
  P23: [
    { id: "API-010", method: "GET", path: "/api/v1/organizations/current", summary: "降级/开关投影" },
    { id: "API-199", method: "POST", path: "/api/v1/organizations/current/capability-controls/tighten", summary: "关停" },
    { id: "API-120", method: "POST", path: "/api/v1/action-previews", summary: "恢复须走 kill_switch_restore" },
  ],
  P24: [
    { id: "API-024", method: "GET", path: "/api/v1/audit-events", summary: "审计检索" },
    { id: "API-040", method: "PUT", path: "/api/v1/organizations/current/siem-export", summary: "SIEM 外发" },
  ],
  P25: [
    { id: "API-160", method: "GET", path: "/api/v1/connectors", summary: "组织级连接器" },
    { id: "API-164", method: "GET", path: "/api/v1/connectors/{connector_id}/webhook-deliveries", summary: "Webhook 投递" },
    { id: "API-170", method: "GET", path: "/api/v1/api-tokens", summary: "ApiToken 列表" },
    { id: "API-171", method: "POST", path: "/api/v1/api-tokens", summary: "签发 Token" },
  ],
  session: [
    { id: "API-005", method: "GET", path: "/api/v1/me", summary: "当前用户" },
    { id: "API-010", method: "GET", path: "/api/v1/organizations/current", summary: "租户投影" },
    { id: "API-011", method: "GET", path: "/api/v1/projects", summary: "项目列表" },
    { id: "API-001", method: "GET", path: "/api/v1/auth/oidc/start", summary: "OIDC 登录" },
  ],
} as const satisfies Record<string, ApiDescriptor[]>;

export type PageId = keyof typeof PAGE_APIS;
