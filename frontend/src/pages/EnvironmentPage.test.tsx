import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/errors";
import type {
  ExecutionEnvironmentListItem,
  ExecutionEnvironmentRegisterResult,
  ListEnvelope,
  ResourceEnvelope,
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

import { EnvironmentPage } from "./EnvironmentPage";

const listItem: ExecutionEnvironmentListItem = {
  id: "env-1",
  env_type: "external_ci",
  name: "Staging CI",
  status: "PENDING_APPROVAL",
  scope_level: "organization",
  credential_present: false,
  version: 1,
  created_at: "2026-09-01T00:00:00.000Z",
  updated_at: "2026-09-01T00:00:00.000Z",
};

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

function wrap(ui: ReactNode, initialEntry = "/projects/proj-1/environments") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/projects/:projectId/environments" element={ui} />
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

beforeEach(() => {
  apiGet.mockReset();
  apiPost.mockReset();
  apiGet.mockResolvedValue({
    data: { items: [listItem] },
    page: { has_more: false, next_cursor: null },
  } satisfies ListEnvelope<ExecutionEnvironmentListItem>);
});

afterEach(() => {
  for (const { root, container } of mounts.splice(0)) {
    act(() => root.unmount());
    container.remove();
  }
});

describe("EnvironmentPage", () => {
  it("renders list without credential_ref field", async () => {
    const container = mount(<EnvironmentPage />);
    await flush();
    expect(container.textContent).toContain("Staging CI");
    expect(container.textContent).not.toContain("credential_ref");
    const listCall = apiGet.mock.calls.find((call) => call[0] === "API-100");
    expect(listCall).toBeDefined();
  });

  it("posts register with PENDING_APPROVAL path body fields", async () => {
    apiPost.mockResolvedValue({
      data: {
        id: "env-new",
        env_type: "external_ci",
        name: "New Env",
        status: "PENDING_APPROVAL",
        version: 1,
        has_credential: false,
        approval_request_id: "appr-1",
      },
    } satisfies ResourceEnvelope<ExecutionEnvironmentRegisterResult>);

    const container = mount(<EnvironmentPage />);
    await flush();

    const nameInput = container.querySelector("#env-name") as HTMLInputElement;
    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      "value",
    )?.set;
    await act(async () => {
      nativeSetter?.call(nameInput, "New Env");
      nameInput.dispatchEvent(new Event("input", { bubbles: true }));
      nameInput.dispatchEvent(new Event("change", { bubbles: true }));
    });

    const submit = Array.from(container.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("提交注册"),
    );
    expect(submit).toBeDefined();
    await act(async () => {
      submit?.click();
    });
    await flush();

    expect(apiPost).toHaveBeenCalled();
    const [, path, body] = apiPost.mock.calls[0] as [string, string, Record<string, unknown>];
    expect(path).toBe("/api/v1/execution-environments");
    expect(body.project_id).toBe("proj-1");
    expect(body.name).toBe("New Env");
    expect(body).not.toHaveProperty("status");
    expect(body).not.toHaveProperty("credential_ref");
  });

  it("surfaces permission error from register", async () => {
    apiPost.mockRejectedValue(
      new ApiError({
        kind: "permission",
        message: "Forbidden",
        apiId: "API-102",
        path: "POST /api/v1/execution-environments",
        httpStatus: 403,
        body: {
          code: "HT-IAM-001",
          class: "permission",
          subclass: "forbidden",
          message: "Forbidden",
          retryable: false,
          trace_id: "trace-1",
        },
      }),
    );

    const container = mount(<EnvironmentPage />);
    await flush();

    const nameInput = container.querySelector("#env-name") as HTMLInputElement;
    const nativeSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      "value",
    )?.set;
    await act(async () => {
      nativeSetter?.call(nameInput, "Denied");
      nameInput.dispatchEvent(new Event("input", { bubbles: true }));
      nameInput.dispatchEvent(new Event("change", { bubbles: true }));
    });
    const submit = Array.from(container.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("提交注册"),
    );
    await act(async () => {
      submit?.click();
    });
    await flush();

    expect(container.textContent).toMatch(/Forbidden|权限|HT-IAM-001/i);
  });
});
