import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
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
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("@/hooks/useSession", () => ({
  useSession: () => ({
    phase: "ready" as const,
    me: {
      memberships: [{ project_id: "proj-1", role: "owner" as const }],
    },
    error: null,
    refetch: vi.fn(),
  }),
}));

import { GateEvalHistoryPage } from "./GateEvalHistoryPage";

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

function wrap(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/gates/history?projectId=proj-1"]}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function renderPage() {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  mounts.push({ root, container });
  act(() => {
    root.render(wrap(<GateEvalHistoryPage />));
  });
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

describe("GateEvalHistoryPage", () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
    apiGet.mockImplementation((id: string) => {
      if (id === "API-144") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "eval-1",
                test_run_id: "run-1",
                result: "fail",
                check_run_ref: { sync_status: "completed" },
                policy_snapshot: { mode: "report_only" },
                waiver_approval_id: null,
              },
            ],
          },
          page: { has_more: false, next_cursor: null },
        });
      }
      if (id === "API-145") {
        return Promise.resolve({
          data: {
            id: "eval-1",
            threshold_details: { min_pass_rate: { passed: false } },
          },
        });
      }
      return Promise.resolve({ data: { items: [] }, page: {} });
    });
  });

  afterEach(() => {
    for (const mount of mounts.splice(0)) {
      act(() => mount.root.unmount());
      mount.container.remove();
    }
  });

  it("shows waiver button for fail result when owner/admin", async () => {
    const container = renderPage();
    await flush();
    expect(container.textContent).toContain("申请豁免");
  });

  it("renders policy mode badge from policy_snapshot", async () => {
    const container = renderPage();
    await flush();
    expect(container.textContent).toContain("仅报告");
    expect(container.textContent).not.toContain("阻断");
  });

  it("posts gate_waiver preview with confirm true", async () => {
    apiPost.mockResolvedValue({
      data: { gate: "REQUIRE_APPROVAL", approval_request_id: "appr-1" },
    });
    const container = renderPage();
    await flush();
    const button = Array.from(container.querySelectorAll("button")).find((node) =>
      node.textContent?.includes("申请豁免"),
    );
    expect(button).toBeTruthy();
    await act(async () => {
      button?.click();
      await Promise.resolve();
    });
    await flush();
    expect(apiPost).toHaveBeenCalled();
    const [, , body] = apiPost.mock.calls[0] as [string, string, Record<string, unknown>];
    expect(body).toMatchObject({
      action_type: "gate_waiver",
      target_object_type: "gate_evaluation",
      target_object_id: "eval-1",
      payload: { confirm: true },
    });
  });
});
