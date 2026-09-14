import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { OrgQuotaCurrent, ResourceEnvelope, WorkbenchProjection } from "@/api/types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const apiGet = vi.fn();

vi.mock("@/api/client", () => ({
  api: {
    get: (...args: unknown[]) => apiGet(...args),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

import { WorkbenchPage } from "./WorkbenchPage";

const workbenchData: WorkbenchProjection = {
  pending_approvals: [
    {
      id: "appr-1",
      action_type: "jira_write",
      status: "PENDING",
      expires_at: "2030-01-01T00:00:00.000Z",
      initiator_id: "user-1",
      target_object_type: "TestRun",
      target_object_id: "run-1",
      version: 1,
    },
  ],
  active_runs: [
    {
      id: "run-wait",
      project_id: "proj-1",
      status: "WAITING_APPROVAL",
      version: 2,
      execution_source: "script",
      dwell_seconds: 120,
    },
  ],
  gate_anomalies: [],
  quota: {
    version: 1,
    token_budget: 1000,
    token_reserved: 0,
    token_consumed: 100,
    token_remaining: 900,
    executor_slot_quota: 5,
    perf_concurrency_quota: 2,
  },
};

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

function wrap(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function mount(node: ReactNode) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(wrap(node));
  });
  mounts.push({ root, container });
  return container;
}

async function flush() {
  for (let i = 0; i < 10; i += 1) {
    await act(async () => {
      await Promise.resolve();
      await new Promise<void>((resolve) => {
        setTimeout(resolve, 0);
      });
    });
  }
}

beforeEach(() => {
  apiGet.mockReset();
  apiGet.mockImplementation((apiId: string) => {
    if (apiId === "API-020") {
      return Promise.resolve({ data: workbenchData } satisfies ResourceEnvelope<WorkbenchProjection>);
    }
    if (apiId === "API-017") {
      return Promise.resolve({
        data: {
          version: 1,
          token_budget: 1000,
          token_reserved: 0,
          token_consumed: 100,
          token_remaining: 900,
          executor_slot_quota: 5,
          perf_concurrency_quota: 2,
        },
      } satisfies ResourceEnvelope<OrgQuotaCurrent>);
    }
    return Promise.reject(new Error(`unexpected ${apiId}`));
  });
});

afterEach(() => {
  for (const { root, container } of mounts.splice(0)) {
    act(() => root.unmount());
    container.remove();
  }
});

describe("WorkbenchPage", () => {
  it("renders pending approval and waiting run with dwell_seconds", async () => {
    const container = mount(<WorkbenchPage />);
    await flush();
    expect(container.textContent).toContain("appr-1");
    expect(container.textContent).toContain("jira_write");
    expect(container.textContent).toContain("run-wait");
    expect(container.textContent).toContain("等待审批");
    expect(container.textContent).toContain("滞留 120s");
  });

  it("uses API-020 counts not local aggregation beyond response length", async () => {
    const container = mount(<WorkbenchPage />);
    await flush();
    expect(container.textContent).toContain("900");
    const statOne = container.textContent?.match(/待审批[\s\S]*?1/);
    expect(statOne).toBeTruthy();
    expect(apiGet.mock.calls.filter((call) => call[0] === "API-020").length).toBe(1);
  });

  it("renders gate anomaly kind and links to run detail", async () => {
    apiGet.mockImplementation((apiId: string) => {
      if (apiId === "API-020") {
        return Promise.resolve({
          data: {
            ...workbenchData,
            gate_anomalies: [
              {
                kind: "fail_evaluation",
                test_run_id: "run-gate-fail",
                gate_evaluation_id: "eval-1",
                result: "fail",
                unevaluated_reason: null,
              },
            ],
          },
        } satisfies ResourceEnvelope<WorkbenchProjection>);
      }
      if (apiId === "API-017") {
        return Promise.resolve({
          data: {
            version: 1,
            token_budget: 1000,
            token_reserved: 0,
            token_consumed: 100,
            token_remaining: 900,
            executor_slot_quota: 5,
            perf_concurrency_quota: 2,
          },
        } satisfies ResourceEnvelope<OrgQuotaCurrent>);
      }
      return Promise.reject(new Error(`unexpected ${apiId}`));
    });
    const container = mount(<WorkbenchPage />);
    await flush();
    expect(container.textContent).toContain("fail_evaluation");
    expect(container.textContent).toContain("run-gate-fail");
    expect(container.querySelector('a[href="/test-center/runs/run-gate-fail"]')).not.toBeNull();
  });

  it("shows empty gate anomaly state and zero count", async () => {
    const container = mount(<WorkbenchPage />);
    await flush();
    expect(container.textContent).toContain("无门禁异常");
    expect(container.textContent).toMatch(/门禁异常[\s\S]*?0/);
  });
});
