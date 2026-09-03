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
      id: "env-ci",
      name: "External CI",
      env_type: "external_ci",
      status: "ACTIVE",
      selectable: true,
      version: 3,
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
  apiGet.mockImplementation((apiId: string, _path: string, params?: Record<string, unknown>) => {
    if (apiId === "API-011") {
      return Promise.resolve({
        data: { items: [{ id: "proj-1", name: "P1" }] },
        page: { has_more: false, next_cursor: null },
      } satisfies ListEnvelope<Record<string, unknown>>);
    }
    if (apiId === "API-069") {
      if (params?.execution_source === "external_ci") {
        return Promise.resolve({
          data: {
            ...options,
            cases: [
              {
                id: "case-ref",
                title: "CI case",
                lifecycle_status: "ACTIVE",
                validity: "valid",
                execution_mode: "script",
                case_type: "referenced",
                job_id: "smoke-suite",
                selectable: true,
              },
            ],
          },
        } satisfies ResourceEnvelope<ExecutionOptions>);
      }
      return Promise.resolve({ data: options } satisfies ResourceEnvelope<ExecutionOptions>);
    }
    if (apiId === "API-070") {
      return Promise.resolve({
        data: {
          job_id: "smoke-suite",
          schema: {
            type: "object",
            required: ["branch"],
            properties: { branch: { type: "string" } },
          },
        },
      } satisfies ResourceEnvelope<{ job_id: string; schema: Record<string, unknown> }>);
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
    expect(apiGet).toHaveBeenCalledWith("API-069", "/api/v1/projects/proj-1/execution-options", {});
    expect(container.textContent).toContain("Active env");
    const disabled = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("Disabled env"),
    );
    expect(disabled).toBeDefined();
    expect(disabled?.hasAttribute("disabled")).toBe(true);
  });

  it("loads API-070 job params for external_ci and submits them", async () => {
    const container = mount(<ExecutionLaunchPage />);
    await flush();
    const ciEnv = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("External CI"),
    );
    expect(ciEnv).toBeDefined();
    await act(async () => {
      ciEnv?.click();
    });
    await flush();
    expect(apiGet).toHaveBeenCalledWith(
      "API-069",
      "/api/v1/projects/proj-1/execution-options",
      expect.objectContaining({ execution_source: "external_ci" }),
    );
    const caseCheckbox = container.querySelector('[role="checkbox"]') as HTMLButtonElement | null;
    await act(async () => {
      caseCheckbox?.click();
    });
    await flush();
    await flush();
    expect(apiGet).toHaveBeenCalledWith(
      "API-070",
      "/api/v1/execution-environments/env-ci/jobs/smoke-suite/params-schema",
    );
    const branchInput = container.querySelector("#job-param-branch") as HTMLInputElement | null;
    expect(branchInput).toBeTruthy();
    await act(async () => {
      if (branchInput) {
        const setter = Object.getOwnPropertyDescriptor(
          HTMLInputElement.prototype,
          "value",
        )?.set;
        setter?.call(branchInput, "main");
        branchInput.dispatchEvent(new Event("input", { bubbles: true }));
      }
    });
    await flush();
    apiPost.mockResolvedValueOnce({
      data: { id: "run-1", status: "PENDING", receipt: { id: "r1", status: "accepted" } },
    });
    const launchButton = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("发起执行"),
    );
    await act(async () => {
      launchButton?.click();
    });
    await flush();
    expect(apiPost).toHaveBeenCalledWith(
      "API-062",
      "/api/v1/test-runs",
      expect.objectContaining({
        execution_source: "external_ci",
        params: expect.objectContaining({ branch: "main" }),
      }),
    );
  });

  it("blocks agent mode on external_ci environments", async () => {
    const container = mount(<ExecutionLaunchPage />);
    await flush();
    const ciEnv = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("External CI"),
    );
    await act(async () => {
      ciEnv?.click();
    });
    await flush();
    const agentCard = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("Agent Mode"),
    );
    expect(agentCard?.hasAttribute("disabled")).toBe(true);
  });
});
