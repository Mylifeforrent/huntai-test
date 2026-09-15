import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConnectorListItem, ListEnvelope } from "@/api/types";
import { ApiError } from "@/api/errors";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const apiGet = vi.fn();
const apiPut = vi.fn();

vi.mock("@/api/client", () => ({
  api: {
    get: (...args: unknown[]) => apiGet(...args),
    post: vi.fn(),
    put: (...args: unknown[]) => apiPut(...args),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("@/hooks/useSession", () => ({
  useSession: () => ({
    phase: "ready" as const,
    me: {
      user: { id: "user-owner", display_name: "Owner", is_disabled: false },
      organization: {
        id: "org-1",
        name: "Org",
        slug: "org",
        version: 2,
        is_active: true,
        capability_controls: {},
        siem_export_enabled: false,
      },
      memberships: [{ project_id: "proj-1", role: "owner" as const }],
      reauth_required: false,
    },
    error: null,
    refetch: vi.fn(),
  }),
}));

import { IntegrationPage } from "./IntegrationPage";

const connectorItem: ConnectorListItem = {
  id: "conn-1",
  type: "ci",
  name: "CI Connector",
  credential_present: false,
  outbound_write_enabled: false,
  version: 1,
};

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

function wrap(ui: ReactNode, projectId = "proj-1") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/projects/${projectId}/integrations`]}>
        <Routes>
          <Route path="/projects/:projectId/integrations" element={ui} />
          <Route path="/integrations" element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function mount(node: ReactNode, projectId = "proj-1") {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(wrap(node, projectId));
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
  apiPut.mockReset();
  apiGet.mockImplementation((apiId: string) => {
    if (apiId === "API-160") {
      return Promise.resolve({
        data: { items: [connectorItem] },
        page: { has_more: false, next_cursor: null },
      } satisfies ListEnvelope<ConnectorListItem>);
    }
    return Promise.reject(new Error(`unexpected ${apiId}`));
  });
  apiPut.mockResolvedValue({
    data: { project_id: "proj-1", version: 2, bindings: [] },
  });
});

afterEach(() => {
  for (const { root, container } of mounts.splice(0)) {
    act(() => root.unmount());
    container.remove();
  }
});

describe("IntegrationPage", () => {
  it("queries connectors via API-160 when projectId is present", async () => {
    mount(<IntegrationPage />);
    await flush();
    const listCall = apiGet.mock.calls.find((call) => call[0] === "API-160");
    expect(listCall).toBeDefined();
    expect(listCall?.[1]).toBe("/api/v1/connectors");
  });

  it("puts API-167 with expected_version and binding fields on save", async () => {
    const container = mount(<IntegrationPage />);
    await flush();
    const valueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    act(() => {
      valueSetter?.call(document.querySelector("#repo"), "org/repo");
      document.querySelector("#repo")?.dispatchEvent(new Event("input", { bubbles: true }));
      valueSetter?.call(document.querySelector("#ref"), "main");
      document.querySelector("#ref")?.dispatchEvent(new Event("input", { bubbles: true }));
      valueSetter?.call(document.querySelector("#plan"), "plan-1");
      document.querySelector("#plan")?.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const saveButton = Array.from(container.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("保存绑定"),
    );
    act(() => {
      saveButton?.click();
    });
    await flush();
    const putCall = apiPut.mock.calls.find((call) => call[0] === "API-167");
    expect(putCall).toBeDefined();
    expect(putCall?.[1]).toBe("/api/v1/projects/proj-1/ci-trigger-bindings");
    const body = putCall?.[2] as {
      expected_version?: number;
      bindings?: Array<{
        repository?: string;
        ref_pattern?: string;
        test_plan_id?: string;
      }>;
    };
    expect(body.expected_version).toBe(1);
    expect(body.bindings?.[0]).toEqual({
      repository: "org/repo",
      ref_pattern: "main",
      test_plan_id: "plan-1",
    });
  });

  it("shows CommandFeedback on save error without fake success", async () => {
    apiPut.mockRejectedValue(
      new ApiError({
        kind: "business",
        message: "version conflict",
        apiId: "API-167",
        path: "PUT /api/v1/projects/proj-1/ci-trigger-bindings",
        httpStatus: 409,
        body: {
          code: "HT-VER-001",
          class: "business",
          subclass: "version_conflict",
          message: "version conflict",
          retryable: false,
          trace_id: "trace-1",
        },
      }),
    );
    const container = mount(<IntegrationPage />);
    await flush();
    const valueSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    act(() => {
      valueSetter?.call(document.querySelector("#repo"), "org/repo");
      document.querySelector("#repo")?.dispatchEvent(new Event("input", { bubbles: true }));
      valueSetter?.call(document.querySelector("#ref"), "main");
      document.querySelector("#ref")?.dispatchEvent(new Event("input", { bubbles: true }));
      valueSetter?.call(document.querySelector("#plan"), "plan-1");
      document.querySelector("#plan")?.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const saveButton = Array.from(container.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("保存绑定"),
    );
    act(() => {
      saveButton?.click();
    });
    await flush();
    expect(container.textContent).toContain("version conflict");
    expect(container.textContent).not.toContain("绑定已保存");
  });

  it("shows EmptyState when connector list is empty", async () => {
    apiGet.mockImplementation((apiId: string) => {
      if (apiId === "API-160") {
        return Promise.resolve({
          data: { items: [] },
          page: { has_more: false, next_cursor: null },
        } satisfies ListEnvelope<ConnectorListItem>);
      }
      return Promise.reject(new Error(`unexpected ${apiId}`));
    });
    const container = mount(<IntegrationPage />);
    await flush();
    expect(container.textContent).toContain("无连接器");
  });

  it("shows alert when projectId is missing from route", async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    act(() => {
      root.render(
        <QueryClientProvider client={client}>
          <MemoryRouter initialEntries={["/integrations"]}>
            <Routes>
              <Route path="/integrations" element={<IntegrationPage />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>,
      );
    });
    mounts.push({ root, container });
    await flush();
    expect(container.textContent).toContain("项目级集成依赖路径中的 projectId");
    expect(apiGet.mock.calls.find((call) => call[0] === "API-160")).toBeUndefined();
  });
});
