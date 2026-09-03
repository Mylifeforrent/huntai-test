import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  ListEnvelope,
  QualityGatePolicyDetail,
  QualityGatePolicyListItem,
  ResourceEnvelope,
} from "@/api/types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const apiGet = vi.fn();
const apiPost = vi.fn();
const apiPatch = vi.fn();

vi.mock("@/api/client", () => ({
  api: {
    get: (...args: unknown[]) => apiGet(...args),
    post: (...args: unknown[]) => apiPost(...args),
    patch: (...args: unknown[]) => apiPatch(...args),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("@/hooks/useSession", () => ({
  useSession: () => ({
    phase: "ready" as const,
    me: {
      user: { id: "user-admin", display_name: "Admin", is_disabled: false },
      organization: {
        id: "org-1",
        name: "Org",
        slug: "org",
        version: 2,
        is_active: true,
        capability_controls: {},
        siem_export_enabled: false,
      },
      memberships: [{ project_id: "proj-1", role: "admin" as const }],
      reauth_required: false,
    },
    error: null,
    refetch: vi.fn(),
  }),
}));

import { QualityGatePolicyPage } from "./QualityGatePolicyPage";

const listItem: QualityGatePolicyListItem = {
  id: "policy-1",
  project_id: "proj-1",
  thresholds: { min_pass_rate: 95, max_p95_ms: 500, max_error_rate: 1 },
  mode: "report_only",
  policy_version: 1,
  version: 1,
  created_at: "2026-09-01T00:00:00.000Z",
  updated_at: "2026-09-01T00:00:00.000Z",
};

const detail: QualityGatePolicyDetail = {
  ...listItem,
  scope: {},
};

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

function wrap(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/gates/policies?projectId=proj-1&policy=policy-1"]}>
        {ui}
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
  for (let i = 0; i < 10; i += 1) {
    await act(async () => {
      await Promise.resolve();
      await new Promise<void>((resolve) => {
        setTimeout(resolve, 0);
      });
    });
  }
}

describe("QualityGatePolicyPage", () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
    apiPatch.mockReset();
    apiGet.mockImplementation((apiId: string) => {
      if (apiId === "API-140") {
        return Promise.resolve({
          data: { items: [listItem] },
          page: { next_cursor: null, has_more: false },
        } satisfies ListEnvelope<QualityGatePolicyListItem>);
      }
      if (apiId === "API-141") {
        return Promise.resolve({ data: detail } satisfies ResourceEnvelope<QualityGatePolicyDetail>);
      }
      return Promise.reject(new Error(`unexpected get ${apiId}`));
    });
  });

  afterEach(() => {
    for (const { root, container } of mounts) {
      act(() => {
        root.unmount();
      });
      container.remove();
    }
    mounts.length = 0;
  });

  it("lists empty policies", async () => {
    apiGet.mockImplementation((apiId: string) => {
      if (apiId === "API-140") {
        return Promise.resolve({
          data: { items: [] },
          page: { next_cursor: null, has_more: false },
        });
      }
      return Promise.reject(new Error(`unexpected get ${apiId}`));
    });
    const container = mount(<QualityGatePolicyPage />);
    await flush();
    expect(container.textContent).toContain("无门禁策略");
    expect(apiGet).toHaveBeenCalledWith(
      "API-140",
      "/api/v1/quality-gate-policies",
      expect.objectContaining({ project_id: "proj-1" }),
    );
    expect(apiGet).not.toHaveBeenCalledWith("API-144", expect.anything(), expect.anything());
    expect(apiGet).not.toHaveBeenCalledWith("API-146", expect.anything(), expect.anything());
  });

  it("shows policies from list", async () => {
    const container = mount(<QualityGatePolicyPage />);
    await flush();
    expect(container.textContent).toContain("policy_version 1");
    expect(container.textContent).toContain("仅报告");
  });

  it("confirming blocking PATCH includes confirm_blocking", async () => {
    apiPatch.mockResolvedValue({
      data: { ...listItem, mode: "blocking", version: 2, policy_version: 2 },
    });
    const container = mount(<QualityGatePolicyPage />);
    await flush();
    const blockingCard = Array.from(container.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("切换为阻断须确认"),
    );
    expect(blockingCard).toBeTruthy();
    await act(async () => {
      blockingCard?.click();
      await flush();
    });
    const confirm = Array.from(document.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("确认开启阻断"),
    );
    expect(confirm).toBeTruthy();
    await act(async () => {
      confirm?.click();
      await flush();
    });
    expect(apiPatch).toHaveBeenCalledWith(
      "API-143",
      "/api/v1/quality-gate-policies/policy-1",
      expect.objectContaining({
        mode: "blocking",
        confirm_blocking: true,
        expected_version: 1,
      }),
    );
  });

  it("create report_only calls API-142 without confirm_blocking", async () => {
    apiPost.mockResolvedValue({ data: detail });
    const container = mount(<QualityGatePolicyPage />);
    await flush();
    const createBtn = Array.from(container.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("创建策略"),
    );
    expect(createBtn).toBeTruthy();
    await act(async () => {
      createBtn?.click();
      await flush();
    });
    expect(apiPost).toHaveBeenCalledWith(
      "API-142",
      "/api/v1/quality-gate-policies",
      expect.objectContaining({
        project_id: "proj-1",
        mode: "report_only",
        scope: {},
      }),
    );
    expect(apiPost.mock.calls[0][2]).not.toHaveProperty("confirm_blocking");
  });
});
