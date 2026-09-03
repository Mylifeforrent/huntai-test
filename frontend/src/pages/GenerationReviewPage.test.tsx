import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
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

import { GenerationReviewPage } from "./GenerationReviewPage";

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

function wrap(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/projects/proj-1/cases/generation-review?generationId=gen-1"]}>
        <Routes>
          <Route path="/projects/:projectId/cases/generation-review" element={ui} />
          <Route path="/projects/:projectId/cases" element={<div>cases list</div>} />
        </Routes>
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

describe("GenerationReviewPage", () => {
  beforeEach(() => {
    apiGet.mockImplementation((apiId: string) => {
      if (apiId === "API-010") {
        return Promise.resolve({ data: { capability_controls: {} } });
      }
      if (apiId === "API-181") {
        return Promise.resolve({ data: { status: "partial", degraded: false } });
      }
      if (apiId === "API-182") {
        return Promise.resolve({
          data: {
            status: "partial",
            cases: [{ name: "list pets", case_type: "api", priority: "P2", steps: [], assertions: [] }],
            failed_items: [{ endpoint: "/broken", reason: "Path item must be an object" }],
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
    apiPost.mockResolvedValue({ data: { generation_id: "gen-1" } });
  });

  afterEach(() => {
    mounts.forEach(({ root, container }) => {
      root.unmount();
      container.remove();
    });
    mounts.length = 0;
    vi.clearAllMocks();
  });

  it("shows generation failure instead of hanging on disabled drafts query", async () => {
    apiGet.mockImplementation((apiId: string) => {
      if (apiId === "API-010") {
        return Promise.resolve({ data: { capability_controls: {} } });
      }
      if (apiId === "API-181") {
        return Promise.resolve({
          data: { status: "failed", error: { message: "批次未产生可用草稿" } },
        });
      }
      return Promise.resolve({ data: {} });
    });
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    mounts.push({ root, container });
    await act(async () => {
      root.render(wrap(<GenerationReviewPage />));
    });
    await flush();
    expect(container.textContent).toContain("生成失败");
    expect(container.textContent).toContain("批次未产生可用草稿");
  });

  it("shows failed_items and adopts via API-032 without lifecycle_status", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    mounts.push({ root, container });
    await act(async () => {
      root.render(wrap(<GenerationReviewPage />));
    });
    await flush();
    expect(container.textContent).toContain("/broken");
    expect(container.textContent).toContain("Path item must be an object");

    const adoptButton = Array.from(container.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("采纳"),
    );
    expect(adoptButton).toBeTruthy();
    await act(async () => {
      adoptButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flush();

    const adoptCall = apiPost.mock.calls.find((call) => call[0] === "API-032");
    expect(adoptCall).toBeTruthy();
    const body = adoptCall?.[2] as Record<string, unknown>;
    expect(body.lifecycle_status).toBeUndefined();
    expect(body.project_id).toBe("proj-1");
    expect(body.drafts).toBeTruthy();
    expect(apiPost.mock.calls.some((call) => call[0] === "API-035")).toBe(false);
  });
});
