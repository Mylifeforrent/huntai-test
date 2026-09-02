import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ExecutionOptions, ListEnvelope, ResourceEnvelope } from "@/api/types";

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

import { ExecutionLaunchPage } from "./ExecutionLaunchPage";

const options: ExecutionOptions = {
  project_id: "proj-1",
  environments: [
    {
      id: "env-active",
      name: "Active env",
      env_type: "platform_executor",
      status: "ACTIVE",
      selectable: true,
      version: 2,
    },
    {
      id: "env-disabled",
      name: "Disabled env",
      env_type: "platform_executor",
      status: "DISABLED",
      selectable: false,
      unavailable_reason: "not_active",
      version: 1,
    },
  ],
  cases: [
    {
      id: "case-1",
      title: "Pets",
      lifecycle_status: "ACTIVE",
      validity: "valid",
      execution_mode: "script",
      selectable: true,
    },
  ],
  combo_constraints: { agent_times_external_ci_allowed: false },
};

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

function wrap(ui: ReactNode, initialEntry = "/test-center/kickoff?projectId=proj-1") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/test-center/kickoff" element={ui} />
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
  apiGet.mockReset();
  apiPost.mockReset();
  apiGet.mockImplementation((apiId: string) => {
    if (apiId === "API-011") {
      return Promise.resolve({
        data: { items: [{ id: "proj-1", name: "P1" }] },
        page: { has_more: false, next_cursor: null },
      } satisfies ListEnvelope<Record<string, unknown>>);
    }
    if (apiId === "API-069") {
      return Promise.resolve({ data: options } satisfies ResourceEnvelope<ExecutionOptions>);
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

describe("ExecutionLaunchPage", () => {
  it("loads execution options from API-069 and does not select non-ACTIVE environments", async () => {
    const container = mount(<ExecutionLaunchPage />);
    await flush();
    expect(apiGet).toHaveBeenCalledWith(
      "API-069",
      "/api/v1/projects/proj-1/execution-options",
      expect.objectContaining({ execution_source: "script" }),
    );
    expect(container.textContent).toContain("Active env");
    const disabled = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("Disabled env"),
    );
    expect(disabled).toBeDefined();
    expect(disabled?.hasAttribute("disabled")).toBe(true);
  });
});
