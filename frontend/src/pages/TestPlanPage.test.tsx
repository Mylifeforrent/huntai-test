import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ListEnvelope, ResourceEnvelope, TestPlanDetail, TestPlanListItem } from "@/api/types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const apiGet = vi.fn();
const apiPost = vi.fn();
const apiPut = vi.fn();

vi.mock("@/api/client", () => ({
  api: {
    get: (...args: unknown[]) => apiGet(...args),
    post: (...args: unknown[]) => apiPost(...args),
    put: (...args: unknown[]) => apiPut(...args),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("@/hooks/useSession", () => ({
  useSession: () => ({
    phase: "ready" as const,
    me: {
      user: { id: "user-tester", display_name: "Tester", is_disabled: false },
      organization: {
        id: "org-1",
        name: "Org",
        slug: "org",
        version: 2,
        is_active: true,
        capability_controls: {},
        siem_export_enabled: false,
      },
      memberships: [{ project_id: "proj-1", role: "tester" as const }],
      reauth_required: false,
    },
    error: null,
    refetch: vi.fn(),
  }),
}));

import { TestPlanPage } from "./TestPlanPage";

const emptyDetail: TestPlanDetail = {
  id: "plan-1",
  project_id: "proj-1",
  name: "Regression",
  jira_fix_version: null,
  case_ids: [],
  schedule: null,
  report_aggregate: {
    last_run_id: null,
    last_run_status: null,
    pass_rate: null,
    gate_result: null,
  },
  version: 1,
  created_at: "2026-09-01T00:00:00.000Z",
  updated_at: "2026-09-01T00:00:00.000Z",
  created_by: "user-tester",
};

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

function wrap(ui: ReactNode, initialEntry = "/projects/proj-1/plans?plan=plan-1") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/projects/:projectId/plans" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function mount(node: ReactNode, initialEntry?: string) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(wrap(node, initialEntry));
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

describe("TestPlanPage", () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
    apiPut.mockReset();
    apiGet.mockImplementation((apiId: string) => {
      if (apiId === "API-050") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "plan-1",
                project_id: "proj-1",
                name: "Regression",
                case_count: 0,
                version: 1,
                created_at: emptyDetail.created_at,
                updated_at: emptyDetail.updated_at,
              } satisfies TestPlanListItem,
            ],
          },
          page: { next_cursor: null, has_more: false },
        } satisfies ListEnvelope<TestPlanListItem>);
      }
      if (apiId === "API-051") {
        return Promise.resolve({ data: emptyDetail } satisfies ResourceEnvelope<TestPlanDetail>);
      }
      if (apiId === "API-030") {
        return Promise.resolve({
          data: { items: [{ id: "case-1", title: "Case A" }] },
          page: { next_cursor: null, has_more: false },
        });
      }
      return Promise.reject(new Error(`unexpected GET ${apiId}`));
    });
    apiPost.mockResolvedValue({
      data: {
        id: "plan-new",
        project_id: "proj-1",
        name: "New plan",
        version: 1,
        case_ids: [],
      },
    });
    apiPut.mockResolvedValue({
      data: {
        id: "plan-1",
        project_id: "proj-1",
        name: "Regression",
        version: 2,
        case_ids: ["case-1"],
      },
    });
  });

  afterEach(() => {
    for (const { root, container } of mounts.splice(0)) {
      act(() => root.unmount());
      container.remove();
    }
  });

  it("shows independent gap labels and does not call API-062", async () => {
    const container = mount(<TestPlanPage />);
    await flush();
    expect(container.textContent).toContain("用例集：未绑定");
    expect(container.textContent).toContain("定时：未绑定");
    expect(container.textContent).toContain("执行：未发起");
    expect(container.textContent).toContain("计划级结果缺口");
    expect(apiPost).not.toHaveBeenCalledWith(
      "API-062",
      expect.anything(),
      expect.anything(),
    );
  });

  it("create plan calls API-052", async () => {
    const container = mount(<TestPlanPage />, "/projects/proj-1/plans");
    await flush();
    const nameInput = container.querySelector("#plan-name") as HTMLInputElement;
    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      "value",
    )?.set;
    await act(async () => {
      nativeSetter?.call(nameInput, "New plan");
      nameInput.dispatchEvent(new Event("input", { bubbles: true }));
      nameInput.dispatchEvent(new Event("change", { bubbles: true }));
    });
    const button = Array.from(container.querySelectorAll("button")).find((el) =>
      el.textContent?.includes("创建计划"),
    );
    expect(button).toBeTruthy();
    await act(async () => {
      button?.click();
      await flush();
    });
    expect(apiPost).toHaveBeenCalledWith(
      "API-052",
      "/api/v1/test-plans",
      expect.objectContaining({ project_id: "proj-1", name: "New plan" }),
    );
  });

  it("bind cases calls API-054", async () => {
    const container = mount(<TestPlanPage />);
    await flush();
    const saveCases = Array.from(container.querySelectorAll("button")).find((el) =>
      el.textContent?.includes("保存用例绑定"),
    );
    await act(async () => {
      saveCases?.click();
      await flush();
    });
    expect(apiPut).toHaveBeenCalledWith(
      "API-054",
      "/api/v1/test-plans/plan-1/case-ids",
      expect.objectContaining({ expected_version: 1, case_ids: [] }),
    );
  });
});
