import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/errors";
import type {
  AIInvocationLogListItem,
  ListEnvelope,
  ModelRouteListItem,
  ProjectRole,
  ResourceEnvelope,
} from "@/api/types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const apiGet = vi.fn();
const apiPut = vi.fn();
const apiPost = vi.fn();

const ownerSession = {
  phase: "ready" as const,
  me: {
    user: { id: "user-owner", display_name: "Owner", is_disabled: false },
    organization: { id: "org-1", name: "Org", slug: "org", version: 1, is_active: true, capability_controls: {} },
    memberships: [{ project_id: "proj-1", role: "owner" as const }],
    reauth_required: false,
  },
  error: null,
  refetch: vi.fn(),
};

type SessionMock = {
  phase: "ready";
  me: {
    user: { id: string; display_name: string; is_disabled: boolean };
    organization: {
      id: string;
      name: string;
      slug: string;
      version: number;
      is_active: boolean;
      capability_controls: Record<string, unknown>;
    };
    memberships: Array<{ project_id: string; role: ProjectRole }>;
    reauth_required: boolean;
  };
  error: null;
  refetch: ReturnType<typeof vi.fn>;
};

let sessionMock: SessionMock = ownerSession;

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
  useSession: () => sessionMock,
}));

import { ModelRoutePage } from "./ModelRoutePage";

const route: ModelRouteListItem = {
  id: "route-1",
  task_type: "general",
  data_classification: "Internal",
  provider_allowlist: ["openai"],
  max_cost: 10,
  fallback: { strategy: "degrade" },
  require_prompt_version: true,
  require_structured_output: false,
  credential_present: false,
  version: 1,
};

const logItem: AIInvocationLogListItem = {
  id: "log-1",
  created_at: "2026-09-01T00:00:00Z",
  created_by: "user-owner",
  model: "openai",
  prompt_version: "v1",
  usage: { total_tokens: 0 },
  cost: 0,
  latency_ms: 12,
  data_classification: "Internal",
  result: "degraded",
};

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

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

function wrap(ui: ReactNode, path = "/admin/model-routes") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/admin/model-routes" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
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
  sessionMock = ownerSession;
  apiGet.mockImplementation((apiId: string) => {
    if (apiId === "API-196") {
      return Promise.resolve({
        data: { items: [route] },
        page: { next_cursor: null, has_more: false },
      } satisfies ListEnvelope<ModelRouteListItem>);
    }
    if (apiId === "API-184") {
      return Promise.resolve({
        data: { items: [logItem] },
        page: { next_cursor: null, has_more: false },
      } satisfies ListEnvelope<AIInvocationLogListItem>);
    }
    return Promise.reject(new Error(`unexpected GET ${apiId}`));
  });
  apiPut.mockResolvedValue({ data: { ...route, max_cost: 20, version: 2 } });
  apiPost.mockResolvedValue({
    data: { reachable: true, latency_ms: 5 },
  } satisfies ResourceEnvelope<{ reachable: boolean; latency_ms: number }>);
});

afterEach(() => {
  for (const item of mounts.splice(0)) {
    act(() => {
      item.root.unmount();
    });
    item.container.remove();
  }
  vi.clearAllMocks();
});

describe("ModelRoutePage", () => {
  it("renders routes for admin", async () => {
    const container = mount(wrap(<ModelRoutePage />));
    await flushReactQuery();
    expect(container.textContent).toContain("general");
    expect(container.textContent).toContain("Internal");
    expect(container.textContent).not.toContain("credential_ref");
  });

  it("saves route via PUT API-197", async () => {
    const container = mount(wrap(<ModelRoutePage />));
    await flushReactQuery();
    const editButton = Array.from(container.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("编辑"),
    );
    expect(editButton).toBeTruthy();
    await act(async () => {
      editButton?.click();
      await flushReactQuery();
    });
    const saveButton = Array.from(container.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("保存"),
    );
    await act(async () => {
      saveButton?.click();
      await flushReactQuery();
    });
    expect(apiPut).toHaveBeenCalled();
  });

  it("runs connection test via API-198", async () => {
    const container = mount(wrap(<ModelRoutePage />));
    await flushReactQuery();
    const testButton = Array.from(container.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("测试连接"),
    );
    await act(async () => {
      testButton?.click();
      await flushReactQuery();
    });
    expect(apiPost).toHaveBeenCalledWith(
      "API-198",
      "/api/v1/model-routes/route-1/connection-tests",
      { expected_version: 1 },
    );
    expect(container.textContent).toContain("可达");
  });

  it("logs list uses API-184 without prompt field in items", async () => {
    const container = mount(wrap(<ModelRoutePage />, "/admin/model-routes?tab=logs"));
    await flushReactQuery();
    expect(apiGet).toHaveBeenCalledWith("API-184", "/api/v1/ai-invocation-logs", expect.any(Object));
    expect(container.textContent).toContain("v1");
    expect(container.textContent).toContain("degraded");
    expect(container.textContent).not.toContain("Prompt 原文");
    const logsCallIndex = apiGet.mock.calls.findIndex((call) => call[0] === "API-184");
    expect(logsCallIndex).toBeGreaterThanOrEqual(0);
    const resolved = (await apiGet.mock.results[logsCallIndex]?.value) as ListEnvelope<AIInvocationLogListItem>;
    for (const item of resolved.data.items) {
      expect(item).not.toHaveProperty("prompt");
      expect(item.prompt_version).toBeTruthy();
    }
  });

  it("blocks viewer with permission error", async () => {
    sessionMock = {
      ...ownerSession,
      me: {
        ...ownerSession.me,
        memberships: [{ project_id: "proj-1", role: "viewer" }],
      },
    };
    apiGet.mockRejectedValueOnce(
      new ApiError({
        kind: "permission",
        message: "Forbidden",
        httpStatus: 403,
        apiId: "API-196",
        path: "GET /api/v1/model-routes",
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
    const container = mount(wrap(<ModelRoutePage />));
    await flushReactQuery();
    expect(container.textContent).toContain("无权限");
  });
});
