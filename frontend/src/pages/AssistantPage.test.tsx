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

import { AssistantPage } from "./AssistantPage";

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

function wrap() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AssistantPage />
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

function render() {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(wrap());
  });
  mounts.push({ root, container });
  return container;
}

describe("AssistantPage", () => {
  beforeEach(() => {
    apiGet.mockImplementation((apiId: string) => {
      if (apiId === "API-190") {
        return Promise.resolve({
          data: {
            items: [
              { id: "sess-1", title: "qa session", project_id: "proj-1", updated_at: "2026-09-06T00:00:00Z" },
            ],
          },
          page: { has_more: false, next_cursor: null },
        });
      }
      if (apiId === "API-193") {
        return Promise.resolve({
          data: {
            id: "sess-1",
            messages: [{ role: "user", content: "最新 run 怎么样？" }],
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    apiPost.mockImplementation((apiId: string) => {
      if (apiId === "API-191") {
        return Promise.resolve({
          data: { id: "sess-2", title: "Copilot 会话", project_id: "proj-1" },
        });
      }
      return Promise.resolve({
        data: {
          answer: "项目最近 TestRun 1 个",
          citations: [{ source_type: "platform", resource_id: "run-1", evidence_ref: null }],
          tool_calls: [{ tool: "query_test_assets", args_hash: "abc", result_summary: "ok" }],
          refused_policies: ["cross_project_reference:00000000-0000-4000-8000-00000000000f"],
          meta: {},
        },
      });
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

  it("renders sessions and read-only notice", async () => {
    const container = render();
    await flush();
    expect(container.textContent).toContain("qa session");
    expect(container.textContent).toContain("只读助手");
  });

  it("creates a session via API-191", async () => {
    const container = render();
    await flush();
    const createButton = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("新建会话"),
    );
    await act(async () => {
      createButton?.click();
    });
    await flush();
    expect(apiPost).toHaveBeenCalledWith(
      "API-191",
      "/api/v1/copilot-sessions",
      expect.objectContaining({ title: "Copilot 会话" }),
      expect.any(String),
    );
  });

  it("sends a message and renders refused_policies", async () => {
    const container = render();
    await flush();
    const textarea = container.querySelector("textarea");
    expect(textarea).toBeDefined();
    await act(async () => {
      if (textarea) {
        const setter = Object.getOwnPropertyDescriptor(
          window.HTMLTextAreaElement.prototype,
          "value",
        )?.set;
        setter?.call(textarea, "最新 run 怎么样？");
        textarea.dispatchEvent(new Event("input", { bubbles: true }));
      }
    });
    const sendButton = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("发送"),
    );
    await act(async () => {
      sendButton?.click();
    });
    await flush();
    expect(apiPost).toHaveBeenCalledWith(
      "API-192",
      "/api/v1/copilot-sessions/sess-1/messages",
      { content: "最新 run 怎么样？" },
      expect.any(String),
    );
    expect(container.textContent).toContain("cross_project_reference");
  });
});
