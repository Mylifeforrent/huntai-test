import { createRoot, type Root } from "react-dom/client";
import { act } from "react";
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

import { ReleaseTaskPage } from "./ReleaseTaskPage";

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

function wrap(initialEntries: string[]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>
        <ReleaseTaskPage />
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

function render(initialEntries: string[]) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(wrap(initialEntries));
  });
  mounts.push({ root, container });
  return container;
}

describe("ReleaseTaskPage", () => {
  beforeEach(() => {
    apiGet.mockImplementation((apiId: string) => {
      if (apiId === "API-150") {
        return Promise.resolve({
          data: {
            items: [
              {
                id: "task-1",
                project_id: "proj-1",
                status: "PENDING_CONFIRM",
                jira_version_ref: "v1.0",
                version: 3,
              },
            ],
          },
          page: { has_more: false, next_cursor: null },
        });
      }
      if (apiId === "API-151") {
        return Promise.resolve({
          data: {
            id: "task-1",
            status: "PENDING_CONFIRM",
            version: 3,
            scope_snapshot: { jira_version_ref: "v1.0", jira_scope_issues: [] },
            a5: {
              summary: "Release notes draft",
              missing_inputs: ["jira_scope_issues"],
            },
            notes_draft: "Release notes draft",
            divergence: null,
          },
        });
      }
      if (apiId === "API-155") {
        return Promise.resolve({
          data: {
            release_task_id: "task-1",
            overall: "red",
            items: [{ key: "jira_scope", level: "red", unmet: true }],
            gate_evaluation_id: null,
            unevaluated_reason: null,
            task_version: 3,
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    apiPost.mockResolvedValue({
      data: { approval_request_id: "appr-1", id: "task-2" },
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

  it("renders list, readiness and read-only A5 draft", async () => {
    const container = render(["/releases?projectId=proj-1"]);
    await flush();
    expect(container.textContent).toContain("v1.0");
    expect(container.textContent).toContain("总体 red");
    expect(container.textContent).toContain("Release notes draft");
    expect(container.textContent).toContain("缺失：jira_scope_issues");
    expect(container.textContent).toContain("禁止自动推送");
  });

  it("creates a release task via API-152", async () => {
    const container = render(["/releases?projectId=proj-1&jiraVersionRef=v2.0"]);
    await flush();
    const createButton = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("圈定版本创建"),
    );
    expect(createButton?.disabled).toBe(false);
    await act(async () => {
      createButton?.click();
    });
    await flush();
    expect(apiPost).toHaveBeenCalledWith(
      "API-152",
      "/api/v1/release-tasks",
      { project_id: "proj-1", jira_version_ref: "v2.0" },
      expect.any(String),
    );
  });

  it("opens release_push approval dialog for PENDING_CONFIRM tasks", async () => {
    const container = render(["/releases?projectId=proj-1"]);
    await flush();
    const pushButton = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("发起 release_push 审批"),
    );
    expect(pushButton).toBeDefined();
    await act(async () => {
      pushButton?.click();
    });
    await flush();
    const confirm = Array.from(document.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("发起审批"),
    );
    expect(confirm).toBeDefined();
    await act(async () => {
      confirm?.click();
    });
    await flush();
    expect(apiPost).toHaveBeenCalledWith(
      "API-120",
      "/api/v1/action-previews",
      expect.objectContaining({
        action_type: "release_push",
        target_object_type: "release_task",
        project_id: "proj-1",
      }),
      expect.any(String),
    );
  });
});
