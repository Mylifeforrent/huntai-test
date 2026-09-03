import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ListEnvelope, TestRunListItem } from "@/api/types";

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

import { TestRunListPage } from "./TestRunListPage";

const waitingItem: TestRunListItem = {
  id: "run-wait",
  project_id: "proj-1",
  env_id: "env-1",
  execution_source: "script",
  trigger_type: "manual",
  status: "WAITING_APPROVAL",
  version: 2,
  dwell_seconds: 95,
  created_at: "2026-09-01T00:00:00.000Z",
  updated_at: "2026-09-01T00:01:35.000Z",
};

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

function wrap(ui: ReactNode, initialEntry = "/projects/proj-1/runs") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/projects/:projectId/runs" element={ui} />
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
  apiGet.mockResolvedValue({
    data: { items: [waitingItem] },
    page: { has_more: false, next_cursor: null },
  } satisfies ListEnvelope<TestRunListItem>);
});

afterEach(() => {
  for (const { root, container } of mounts.splice(0)) {
    act(() => root.unmount());
    container.remove();
  }
});

describe("TestRunListPage", () => {
  it("shows dwell_seconds for waiting runs and does not dump snapshot", async () => {
    const container = mount(<TestRunListPage />);
    await flush();
    expect(container.textContent).toContain("95s");
    expect(container.textContent).not.toContain("snapshot_summary");
    expect(container.textContent).not.toContain("params_redacted");
    expect(apiGet).toHaveBeenCalledWith(
      "API-060",
      "/api/v1/test-runs",
      expect.objectContaining({ project_id: "proj-1" }),
    );
  });
});
