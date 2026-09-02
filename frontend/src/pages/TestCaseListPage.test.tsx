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

import { TestCaseListPage } from "./TestCaseListPage";

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

function wrap(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/projects/proj-1/cases"]}>
        <Routes>
          <Route path="/projects/:projectId/cases" element={ui} />
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

describe("TestCaseListPage", () => {
  beforeEach(() => {
    apiGet.mockImplementation((apiId: string) => {
      if (apiId === "API-030") {
        return Promise.resolve({
          data: {
            items: [{ id: "case-1", title: "List pets", lifecycle_status: "DRAFT", validity: "valid", version: 1 }],
          },
          page: { has_more: false, next_cursor: null },
        });
      }
      return Promise.resolve({ data: { items: [] }, page: { has_more: false } });
    });
  });

  afterEach(() => {
    mounts.forEach(({ root, container }) => {
      root.unmount();
      container.remove();
    });
    mounts.length = 0;
    vi.clearAllMocks();
  });

  it("lists title and uses tags query param", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    mounts.push({ root, container });
    await act(async () => {
      root.render(wrap(<TestCaseListPage />));
    });
    await flush();
    expect(container.textContent).toContain("List pets");

    const tagInput = container.querySelector("input[placeholder*='tags']") as HTMLInputElement;
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      "value",
    )?.set;
    await act(async () => {
      nativeInputValueSetter?.call(tagInput, "ai-generated");
      tagInput.dispatchEvent(new Event("input", { bubbles: true }));
      tagInput.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await flush();

    const listCall = apiGet.mock.calls.filter((call) => call[0] === "API-030").at(-1);
    expect(listCall?.[2]?.tags).toBe("ai-generated");
  });

  it("keeps excel import undeveloped", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    mounts.push({ root, container });
    await act(async () => {
      root.render(wrap(<TestCaseListPage />));
    });
    await flush();
    const importBtn = Array.from(container.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("Excel 导入"),
    );
    await act(async () => {
      importBtn?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flush();
    expect(container.textContent).toMatch(/未实现|API-200/);
    expect(apiPost).not.toHaveBeenCalled();
  });
});
