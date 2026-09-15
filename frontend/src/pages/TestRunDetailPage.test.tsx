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
const apiPatch = vi.fn();
const apiGetBlob = vi.fn();

vi.mock("@/api/client", () => ({
  api: {
    get: (...args: unknown[]) => apiGet(...args),
    post: (...args: unknown[]) => apiPost(...args),
    put: vi.fn(),
    patch: (...args: unknown[]) => apiPatch(...args),
    delete: vi.fn(),
    getBlob: (...args: unknown[]) => apiGetBlob(...args),
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
  apiPatch.mockReset();
  apiGetBlob.mockReset();
  apiGetBlob.mockResolvedValue(new Blob(["bytes"], { type: "image/png" }));
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
    if (apiId === "API-133") {
      return Promise.resolve({
        data: { items: [] },
        page: { has_more: false, next_cursor: null },
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
      if (apiId === "API-133") {
        return Promise.resolve({
          data: { items: [] },
          page: { has_more: false, next_cursor: null },
        });
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

  it("submits correction via API-132", async () => {
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
                confidence: 0.3,
                blocking_judgment: "uncertain",
                evidence_refs: [],
                failure_refs: ["case-result-1"],
              },
            ],
            unclustered_refs: [],
            generation_status: "ready",
            degraded: true,
          },
        } satisfies ResourceEnvelope<FailureClusterReport>);
      }
      if (apiId === "API-131") {
        return Promise.resolve({
          data: {
            id: "cluster-1",
            test_run_id: "run-1",
            category: "assertion_real_bug",
            confidence: 0.3,
            blocking_judgment: "uncertain",
            evidence_refs: [],
            failure_refs: ["case-result-1"],
            correction_history: [],
            fixes_preview: [],
          },
        });
      }
      if (apiId === "API-133") {
        return Promise.resolve({
          data: { items: [] },
          page: { has_more: false, next_cursor: null },
        });
      }
      return Promise.reject(new Error(`unexpected ${apiId}`));
    });
    apiPatch.mockResolvedValue({
      data: {
        id: "cluster-1",
        category: "flaky",
        blocking_judgment: "uncertain",
        correction_history: [{ actor: "user-1", field: "category", old: "assertion_real_bug", new: "flaky", timestamp: "t" }],
      },
    });
    const container = mount(<TestRunDetailPage />);
    await flush();
    const categoryInput = container.querySelector("input");
    expect(categoryInput).toBeTruthy();
    await act(async () => {
      if (categoryInput) {
        const native = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype,
          "value",
        );
        native?.set?.call(categoryInput, "flaky");
        categoryInput.dispatchEvent(new Event("input", { bubbles: true }));
        categoryInput.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
    const correct = Array.from(container.querySelectorAll("button")).find((el) =>
      el.textContent?.includes("提交修正留痕"),
    );
    await act(async () => {
      correct?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flush();
    expect(apiPatch).toHaveBeenCalledWith(
      "API-132",
      "/api/v1/failure-clusters/cluster-1",
      {
        corrections: [
          {
            field: "category",
            new: "flaky",
            old: "assertion_real_bug",
          },
        ],
      },
    );
  });

  it("loads case result detail, step runs, and artifact metadata", async () => {
    apiGet.mockImplementation((apiId: string, path?: string) => {
      if (apiId === "API-061") {
        return Promise.resolve({ data: { ...pendingRun, status: "FAILED" } });
      }
      if (apiId === "API-064") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "case-result-1",
                test_run_id: "run-1",
                test_case_id: "case-1",
                outcome: "failed",
                attempt_seq: 1,
                is_late: false,
                is_partial: false,
                data_classification: "Internal",
              },
            ],
          },
          page: { has_more: false, next_cursor: null },
        });
      }
      if (apiId === "API-065") {
        return Promise.resolve({
          data: {
            id: "case-result-1",
            artifact_ids: ["artifact-trace-1"],
          },
        });
      }
      if (apiId === "API-066") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "step-1",
                case_result_id: "case-result-1",
                step_index: 0,
                is_incomplete: false,
                observation_ref: "org/key/trace.zip",
              },
            ],
          },
          page: { has_more: false, next_cursor: null },
        });
      }
      if (apiId === "API-220") {
        return Promise.resolve({
          data: {
            id: path?.split("/").pop(),
            kind: "trace",
            object_key: "org/key/trace.zip",
            content_access: {
              mode: "app_proxy",
              content_path: "/api/v1/artifacts/artifact-trace-1/content",
            },
          },
        });
      }
      if (apiId === "API-130") {
        return Promise.resolve({
          data: {
            test_run_id: "run-1",
            items: [],
            unclustered_refs: [],
            generation_status: "ready",
            degraded: false,
          },
        });
      }
      return Promise.reject(new Error(`unexpected ${apiId}`));
    });
    mount(<TestRunDetailPage />);
    await flush();
    expect(apiGet).toHaveBeenCalledWith("API-065", "/api/v1/case-results/case-result-1");
    expect(apiGet).toHaveBeenCalledWith("API-066", "/api/v1/case-results/case-result-1/step-runs");
    expect(apiGet).toHaveBeenCalledWith("API-220", "/api/v1/artifacts/artifact-trace-1");
    expect(apiGetBlob).toHaveBeenCalled();
  });

  it("shows pending clustering banner", async () => {
    apiGet.mockImplementation((apiId: string) => {
      if (apiId === "API-061") {
        return Promise.resolve({ data: { ...pendingRun, status: "FAILED" } });
      }
      if (apiId === "API-064") {
        return Promise.resolve({
          data: { items: [] },
          page: { has_more: false, next_cursor: null },
        });
      }
      if (apiId === "API-130") {
        return Promise.resolve({
          data: {
            test_run_id: "run-1",
            items: [],
            unclustered_refs: [],
            generation_status: "pending",
            degraded: false,
          },
        });
      }
      return Promise.reject(new Error(`unexpected ${apiId}`));
    });
    const container = mount(<TestRunDetailPage />);
    await flush();
    expect(container.textContent).toContain("聚类生成中");
  });

  it("renders variable_unresolved result_summary reason and function catalog details", async () => {
    const failedRun: TestRunDetail = {
      ...pendingRun,
      status: "FAILED",
      result_summary: {
        reason: "variable_unresolved",
        details: ["function_catalog_unavailable: ${uuid()}"],
      },
    };
    apiGet.mockImplementation((apiId: string) => {
      if (apiId === "API-061") {
        return Promise.resolve({ data: failedRun } satisfies ResourceEnvelope<TestRunDetail>);
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
            items: [],
            unclustered_refs: [],
            generation_status: "ready",
            degraded: false,
          },
        } satisfies ResourceEnvelope<FailureClusterReport>);
      }
      return Promise.reject(new Error(`unexpected ${apiId}`));
    });
    const container = mount(<TestRunDetailPage />);
    await flush();
    expect(container.textContent).toContain("失败原因：variable_unresolved");
    expect(container.textContent).toContain("function_catalog_unavailable: ${uuid()}");
    expect(container.textContent).toContain("动态函数目录未启用，占位符未解析。");
    expect(container.textContent).not.toContain("已解析");
    expect(container.textContent).not.toContain("变量解析失败");
  });

  it("posts jira_write preview on failed run and hides button for viewer role", async () => {
    const failedRun: TestRunDetail = { ...pendingRun, status: "FAILED" };
    apiGet.mockImplementation((apiId: string) => {
      if (apiId === "API-061") {
        return Promise.resolve({ data: failedRun } satisfies ResourceEnvelope<TestRunDetail>);
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
                root_cause: "status mismatch",
                confidence: 0.85,
                blocking_judgment: "blocker",
                evidence_refs: ["ev-1"],
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
            evidence_refs: ["ev-1"],
            failure_refs: ["case-result-1"],
            correction_history: [],
          },
        });
      }
      if (apiId === "API-133") {
        return Promise.resolve({
          data: { items: [] },
          page: { has_more: false, next_cursor: null },
        });
      }
      return Promise.reject(new Error(`unexpected ${apiId}`));
    });
    apiPost.mockResolvedValue({
      data: { gate: "REQUIRE_APPROVAL", approval_request_id: "apr-jira" },
    });
    const container = mount(<TestRunDetailPage />);
    await flush();
    const jiraButton = Array.from(container.querySelectorAll("button")).find((el) =>
      el.textContent?.includes("一键创建 Jira 缺陷"),
    );
    expect(jiraButton).toBeTruthy();
    await act(async () => {
      jiraButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flush();
    expect(apiPost).toHaveBeenCalledWith(
      "API-120",
      "/api/v1/action-previews",
      expect.objectContaining({
        action_type: "jira_write",
        target_object_type: "failure_cluster",
        target_object_id: "cluster-1",
      }),
    );
  });
});
