import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/errors";
import type { AiCostDashboard, ResourceEnvelope } from "@/api/types";

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

vi.mock("@/hooks/useSession", () => ({
  useSession: () => ({
    phase: "ready" as const,
    me: {
      user: { id: "user-owner", display_name: "Owner", is_disabled: false },
      organization: { id: "org-1", name: "Org", slug: "org", version: 1, is_active: true, capability_controls: {} },
      memberships: [{ project_id: "proj-1", role: "owner" as const }],
      reauth_required: false,
    },
    error: null,
    refetch: vi.fn(),
  }),
}));

import { AiCostPage } from "./AiCostPage";

const dashboard: AiCostDashboard = {
  window: { from: "2026-09-01T00:00:00.000Z", to: "2026-09-01T12:00:00.000Z" },
  totals: {
    token_usage: { prompt_tokens: 10, completion_tokens: 20, total_tokens: 30 },
    cost: 1.5,
    invocation_count: 3,
    adoption_rate: 0.33,
    degrade_rate: 0.67,
    cost_per_workflow: {},
  },
  series: [],
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
    root.render(node);
  });
  mounts.push({ root, container });
  return container;
}

async function flushReactQuery() {
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
});

afterEach(() => {
  for (const item of mounts.splice(0)) {
    act(() => item.root.unmount());
    item.container.remove();
  }
});

describe("AiCostPage", () => {
  it("renders server totals for admin", async () => {
    apiGet.mockResolvedValueOnce({ data: dashboard } satisfies ResourceEnvelope<AiCostDashboard>);
    const container = mount(wrap(<AiCostPage />));
    await flushReactQuery();
    expect(container.textContent).toContain("30");
    expect(container.textContent).toContain("1.5");
  });

  it("shows permission error for viewer", async () => {
    apiGet.mockRejectedValueOnce(
      new ApiError({
        kind: "permission",
        message: "Forbidden",
        httpStatus: 403,
        apiId: "API-183",
        path: "GET /api/v1/ai/cost-dashboard",
        body: {
          code: "HT-IAM-001",
          class: "permission",
          subclass: "forbidden",
          message: "Forbidden",
          retryable: false,
          trace_id: "trace-viewer",
        },
      }),
    );
    const container = mount(wrap(<AiCostPage />));
    await flushReactQuery();
    expect(container.textContent).toContain("无权限");
  });
});
