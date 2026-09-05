import { createRoot, type Root } from "react-dom/client";
import { act } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
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

import { AgentTaskDetailPage } from "./AgentTaskDetailPage";

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

function wrap() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/test-center/runs/run-1/agent"]}>
        <Routes>
          <Route path="/test-center/runs/:runId/agent" element={<AgentTaskDetailPage />} />
          <Route path="/projects/:projectId/cases/:caseId" element={<div>CASE-DETAIL</div>} />
        </Routes>
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

function render() {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(wrap());
  });
  mounts.push({ root, container });
  return container;
}

const TRAJECTORY = {
  test_run_id: "run-1",
  available: true,
  unavailable_reason: null,
  a8: {
    task_id: "run-1",
    status: "completed",
    incomplete: false,
    steps: [
      {
        seq: 1,
        intent: "step 1: request",
        action: { tool: "request", args_hash: "abc123" },
        observation_ref: null,
        screenshot_ref: null,
        elapsed_ms: 12,
      },
    ],
    assertion_results: [{ expr: "status_code", passed: true }],
    token_usage: { prompt_tokens: 0, completion_tokens: 0 },
  },
  policy_denials: [],
};

describe("AgentTaskDetailPage", () => {
  beforeEach(() => {
    apiGet.mockImplementation((apiId: string) => {
      if (apiId === "API-067") {
        return Promise.resolve({ data: TRAJECTORY });
      }
      if (apiId === "API-061") {
        return Promise.resolve({
          data: { id: "run-1", status: "SUCCEEDED", version: 3, execution_source: "agent" },
        });
      }
      return Promise.resolve({ data: {} });
    });
    apiPost.mockResolvedValue({
      data: {
        test_case: {
          id: "case-9",
          project_id: "proj-1",
          lifecycle_status: "DRAFT",
          execution_mode: "script",
          tags: ["ai-generated"],
        },
        test_run_id: "run-1",
      },
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

  it("renders trajectory steps with sanitized args hash", async () => {
    const container = render();
    await flush();
    expect(container.textContent).toContain("step 1: request");
    expect(container.textContent).toContain("abc123");
    expect(container.textContent).not.toContain("params");
  });

  it("shows empty state for non-agent runs", async () => {
    apiGet.mockImplementation((apiId: string) => {
      if (apiId === "API-067") {
        return Promise.resolve({
          data: { available: false, unavailable_reason: "not_agent_source", a8: null },
        });
      }
      return Promise.resolve({ data: { id: "run-1", status: "SUCCEEDED", version: 3 } });
    });
    const container = render();
    await flush();
    expect(container.textContent).toContain("无 Agent 轨迹");
    expect(container.textContent).toContain("not_agent_source");
  });

  it("converts trajectory to script draft and navigates to the new case", async () => {
    const container = render();
    await flush();
    const draftButton = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("转脚本草稿"),
    );
    expect(draftButton).toBeDefined();
    await act(async () => {
      draftButton?.click();
    });
    await flush();
    const confirm = Array.from(document.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("确认转换"),
    );
    expect(confirm).toBeDefined();
    await act(async () => {
      confirm?.click();
    });
    await flush();
    expect(apiPost).toHaveBeenCalledWith(
      "API-068",
      "/api/v1/test-runs/run-1/script-drafts",
      {},
    );
    expect(container.textContent).toContain("CASE-DETAIL");
  });
});
