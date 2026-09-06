import { createRoot, type Root } from "react-dom/client";
import { act } from "react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const apiGet = vi.fn();
const apiPost = vi.fn();

vi.mock("@/api/client", () => ({
  api: {
    get: (...args: unknown[]) => apiGet(...args),
    post: (...args: unknown[]) => apiPost(...args),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    getBlob: vi.fn(),
  },
}));

vi.mock("@/hooks/useSession", () => ({
  useSession: () => ({
    phase: "ready" as const,
    me: {
      user: { id: "user-owner", display_name: "Owner", is_disabled: false },
      organization: { id: "org-1", capability_controls: {} },
      memberships: [{ project_id: "proj-1", role: "owner" as const }],
      reauth_required: false,
    },
    error: null,
    refetch: vi.fn(),
  }),
}));

import { PerformancePage } from "./PerformancePage";

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

function wrap(initialEntries: string[]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>
        <PerformancePage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function flush() {
  for (let i = 0; i < 10; i += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  }
}

function render(initialEntries: string[]) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(wrap(initialEntries));
  });
  mounts.push({ root, container });
  return container;
}

describe("PerformancePage", () => {
  beforeEach(() => {
    apiGet.mockImplementation((apiId: string) => {
      if (apiId === "API-010") {
        return Promise.resolve({
          data: { id: "org-1", version: 7, capability_controls: {} },
        });
      }
      if (apiId === "API-056") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "pb-1",
                scenario_test_case_id: "case-1",
                is_active: true,
                metrics_snapshot: { p95_ms: 120 },
              },
            ],
          },
          page: { has_more: false, next_cursor: null },
        });
      }
      return Promise.resolve({ data: {} });
    });
    apiPost.mockResolvedValue({
      data: { id: "run-9", result_summary: { queued: true, reason: "scenario_mutex" } },
    });
  });

  afterEach(() => {
    mounts.forEach(({ root, container }) => {
      act(() => {
        root.unmount();
      });
      container.remove();
    });
    mounts.length = 0;
    vi.clearAllMocks();
  });

  it("starts a perf run with whitelist params via API-062", async () => {
    const container = render([
      "/test-center/performance?projectId=proj-1&envId=env-1&scenarioId=case-1&targetEnv=http://t.example&whitelist=http://t.example,http://s.internal&users=5&runTime=30",
    ]);
    await flush();
    const startButton = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("发起压测"),
    );
    expect(startButton).toBeDefined();
    expect(startButton?.disabled).toBe(false);
    await act(async () => {
      startButton?.click();
    });
    await flush();
    expect(apiPost).toHaveBeenCalledWith(
      "API-062",
      "/api/v1/test-runs",
      expect.objectContaining({
        execution_source: "script",
        case_ids: ["case-1"],
        params: expect.objectContaining({
          TARGET_ENV: "http://t.example",
          perf_whitelist: ["http://t.example", "http://s.internal"],
          perf_scenario: expect.objectContaining({ users: 5, run_time_seconds: 30 }),
        }),
      }),
      expect.any(String),
    );
    expect(container.textContent).toContain("排队");
  });

  it("creates a baseline via API-057", async () => {
    const container = render([
      "/test-center/performance?projectId=proj-1&scenarioId=case-1&baselineP95=120&baselineTolerance=0.2",
    ]);
    await flush();
    const createButton = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("创建基线"),
    );
    expect(createButton).toBeDefined();
    await act(async () => {
      createButton?.click();
    });
    await flush();
    expect(apiPost).toHaveBeenCalledWith(
      "API-057",
      "/api/v1/perf-baselines",
      {
        scenario_test_case_id: "case-1",
        metrics_snapshot: { p95_ms: 120 },
        tolerance: { rt: 0.2 },
      },
      expect.any(String),
    );
    expect(container.textContent).toContain("120");
  });

  it("tightens the performance module via API-199 kill switch", async () => {
    const container = render(["/test-center/performance?projectId=proj-1"]);
    await flush();
    const killButton = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("Kill switch"),
    );
    expect(killButton).toBeDefined();
    await act(async () => {
      killButton?.click();
    });
    await flush();
    const confirm = Array.from(document.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("立即关停"),
    );
    expect(confirm).toBeDefined();
    await act(async () => {
      confirm?.click();
    });
    await flush();
    expect(apiPost).toHaveBeenCalledWith(
      "API-199",
      "/api/v1/organizations/current/capability-controls/tighten",
      expect.objectContaining({
        target: { level: "module", module: "performance" },
      }),
    );
  });
});
