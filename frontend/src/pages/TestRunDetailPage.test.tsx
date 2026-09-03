import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  FailureClusterReport,
  ListEnvelope,
  ResourceEnvelope,
  TestRunDetail,
} from "@/api/types";

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
  },
}));

vi.mock("@/hooks/useSession", () => ({
  useSession: () => ({
    phase: "ready" as const,
    me: {
      user: { id: "user-1", display_name: "Tester", is_disabled: false },
      organization: {
        id: "org-1",
        name: "Org",
        slug: "org",
        version: 1,
        is_active: true,
        capability_controls: {},
      },
      memberships: [{ project_id: "proj-1", role: "tester" as const }],
      reauth_required: false,
    },
    error: null,
    refetch: vi.fn(),
  }),
}));

type Listener = (event: MessageEvent<string>) => void;

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  listeners = new Map<string, Listener[]>();
  url: string;
  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }
  addEventListener(type: string, listener: Listener) {
    const current = this.listeners.get(type) ?? [];
    current.push(listener);
    this.listeners.set(type, current);
  }
  removeEventListener(type: string, listener: Listener) {
    const current = this.listeners.get(type) ?? [];
    this.listeners.set(
      type,
      current.filter((item) => item !== listener),
    );
  }
  close() {
    this.listeners.clear();
  }
  emit(type: string, data: string) {
    for (const listener of this.listeners.get(type) ?? []) {
      listener({ data } as MessageEvent<string>);
    }
  }
}

vi.stubGlobal("EventSource", FakeEventSource);

import { TestRunDetailPage } from "./TestRunDetailPage";

const pendingRun: TestRunDetail = {
  id: "run-1",
  project_id: "proj-1",
  env_id: "env-1",
  execution_source: "script",
  trigger_type: "manual",
  status: "PENDING",
  version: 1,
  created_at: "2026-09-02T00:00:00.000Z",
  updated_at: "2026-09-02T00:00:00.000Z",
  snapshot_summary: {
    case_ids: ["case-1"],
    env_id: "env-1",
    env_config_version: 1,
    params_redacted: {},
  },
};

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

function wrap(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/test-center/runs/run-1"]}>
        <Routes>
          <Route path="/test-center/runs/:runId" element={ui} />
        </Routes>
      </MemoryRouter>
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
  for (let i = 0; i < 12; i += 1) {
    await act(async () => {
      await Promise.resolve();
      await new Promise<void>((resolve) => {
        setTimeout(resolve, 0);
      });
    });
  }
}

beforeEach(() => {
  FakeEventSource.instances = [];
  apiGet.mockReset();
  apiPost.mockReset();
  apiGet.mockImplementation((apiId: string) => {
    if (apiId === "API-061") {
      return Promise.resolve({ data: pendingRun } satisfies ResourceEnvelope<TestRunDetail>);
    }
    if (apiId === "API-064") {
      return Promise.resolve({
        data: { items: [] },
        page: { has_more: false, next_cursor: null },
      } satisfies ListEnvelope<Record<string, unknown>>);
    }
    if (apiId === "API-130") {
      return Promise.resolve({
        data: {
          test_run_id: "run-1",
          items: [
            {
              id: "cluster-1",
              test_run_id: "run-1",
              category: "assertion_real_bug",
              confidence: 0.85,
              blocking_judgment: "blocker",
              evidence_refs: [],
              failure_refs: ["case-result-1"],
            },
          ],
          unclustered_refs: [],
          generation_status: "ready",
          degraded: false,
          page: { has_more: false, next_cursor: null },
        },
      } satisfies ResourceEnvelope<FailureClusterReport>);
    }
    if (apiId === "API-131") {
      return Promise.resolve({
        data: {
          id: "cluster-1",
          test_run_id: "run-1",
          category: "assertion_real_bug",
          confidence: 0.85,
          blocking_judgment: "blocker",
          evidence_refs: [],
          failure_refs: ["case-result-1"],
          correction_history: [],
          fixes_preview: [
            {
              field: "assertions",
              current: "200",
              suggested: '{"assertions":[{"type":"status_code","expected":500}]}',
              reason: "align",
              confidence: 0.85,
              can_auto_apply: false,
            },
          ],
        },
      });
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

describe("TestRunDetailPage", () => {
  it("does not treat SSE progress as SUCCEEDED when GET still returns PENDING", async () => {
    const container = mount(<TestRunDetailPage />);
    await flush();
    const source = FakeEventSource.instances[0];
    expect(source).toBeDefined();
    act(() => {
      source.emit(
        "progress",
        JSON.stringify({ hint: "succeeded", progress_percent: 100 }),
      );
    });
    await flush();
    expect(container.textContent).toContain("PENDING");
    expect(container.textContent).toContain("SSE 提示（非终态）：succeeded");
  });

  it("renders API-130 report shape and shows apply for high confidence", async () => {
    const succeededRun: TestRunDetail = { ...pendingRun, status: "FAILED" };
    apiGet.mockImplementation((apiId: string) => {
      if (apiId === "API-061") {
        return Promise.resolve({ data: succeededRun } satisfies ResourceEnvelope<TestRunDetail>);
      }
      if (apiId === "API-064") {
        return Promise.resolve({
          data: { items: [{ id: "case-result-1", test_case_id: "case-1", outcome: "failed" }] },
          page: { has_more: false, next_cursor: null },
        } satisfies ListEnvelope<Record<string, unknown>>);
      }
      if (apiId === "API-130") {
        return Promise.resolve({
          data: {
            test_run_id: "run-1",
            items: [
              {
                id: "cluster-1",
                test_run_id: "run-1",
                category: "assertion_real_bug",
                confidence: 0.85,
                blocking_judgment: "blocker",
                evidence_refs: [],
                failure_refs: ["case-result-1"],
              },
            ],
            unclustered_refs: [],
            generation_status: "ready",
            degraded: false,
          },
        } satisfies ResourceEnvelope<FailureClusterReport>);
      }
      if (apiId === "API-131") {
        return Promise.resolve({
          data: {
            id: "cluster-1",
            test_run_id: "run-1",
            category: "assertion_real_bug",
            confidence: 0.85,
            blocking_judgment: "blocker",
            evidence_refs: [],
            failure_refs: ["case-result-1"],
            correction_history: [],
            fixes_preview: [
              {
                field: "assertions",
                current: "200",
                suggested: "{}",
                reason: "align",
                confidence: 0.85,
                can_auto_apply: false,
              },
            ],
          },
        });
      }
      if (apiId === "API-031") {
        return Promise.resolve({ data: { id: "case-1", version: 2 } });
      }
      return Promise.reject(new Error(`unexpected ${apiId}`));
    });
    const container = mount(<TestRunDetailPage />);
    await flush();
    expect(container.textContent).toContain("可应用");
    apiPost.mockResolvedValue({
      data: { gate: "REQUIRE_APPROVAL", approval_request_id: "apr-1" },
    });
    const apply = Array.from(container.querySelectorAll("button")).find((el) =>
      el.textContent?.includes("可应用"),
    );
    expect(apply).toBeTruthy();
    await act(async () => {
      apply?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flush();
    expect(apiGet).toHaveBeenCalledWith("API-031", "/api/v1/test-cases/case-1");
    expect(apiGet).not.toHaveBeenCalledWith(
      "API-031",
      "/api/v1/test-cases/case-result-1",
    );
  });
});
