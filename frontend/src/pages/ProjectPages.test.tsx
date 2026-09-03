import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  ListEnvelope,
  MeProjection,
  ProjectListItem,
  ProjectMemberItem,
  ResourceEnvelope,
} from "@/api/types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const apiGet = vi.fn();

vi.mock("@/api/client", () => ({
  api: {
    get: (...args: unknown[]) => apiGet(...args),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

import { ProjectOverviewPage } from "./ProjectOverviewPage";
import { ProjectSettingsPage } from "./ProjectSettingsPage";

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

function wrap(ui: ReactNode, initialPath: string, routePath: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path={routePath} element={ui} />
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

afterEach(() => {
  for (const item of mounts.splice(0)) {
    act(() => {
      item.root.unmount();
    });
    item.container.remove();
  }
  vi.clearAllMocks();
});

beforeEach(() => {
  apiGet.mockReset();
});

describe("ProjectOverviewPage", () => {
  it("renders list items from typed API-011 data", async () => {
    const payload: ListEnvelope<ProjectListItem> = {
      data: {
        items: [
          {
            id: "proj-1",
            name: "Alpha",
            version: 1,
            my_role: "owner",
            jira_project_key: "ALP",
          },
        ],
      },
      page: { next_cursor: null, has_more: false },
    };
    apiGet.mockResolvedValue(payload);

    const container = mount(wrap(<ProjectOverviewPage />, "/projects", "/projects"));
    await flushReactQuery();

    expect(apiGet).toHaveBeenCalled();
    expect(container.textContent).toContain("Alpha");
    expect(container.textContent).toContain("ALP");
    expect(container.querySelector('[data-testid="project-list-item"]')).not.toBeNull();
  });
});

describe("ProjectSettingsPage members tab", () => {
  function mockApis(role: "owner" | "viewer") {
    const me: ResourceEnvelope<MeProjection> = {
      data: {
        user: { id: "u1", display_name: "Me", is_disabled: false },
        organization: {
          id: "o1",
          name: "Org",
          slug: "org",
          version: 1,
          is_active: true,
          capability_controls: {},
        },
        memberships: [{ project_id: "proj-1", project_name: "P", role }],
        reauth_required: false,
      },
    };
    const members: ListEnvelope<ProjectMemberItem> = {
      data: {
        items: [
          {
            user_id: "u1",
            role,
            display_name: "Me",
            ...(role === "owner" ? { email: "me@example.com" } : {}),
          },
        ],
      },
      page: { next_cursor: null, has_more: false },
    };
    apiGet.mockImplementation(async (apiId: string) => {
      if (apiId === "API-005") return me;
      if (apiId === "API-013") return members;
      throw new Error(`unexpected api ${apiId}`);
    });
  }

  it("shows write UI for owner", async () => {
    mockApis("owner");
    const container = mount(
      wrap(<ProjectSettingsPage />, "/projects/proj-1/settings", "/projects/:projectId/settings"),
    );
    await flushReactQuery();
    expect(container.querySelector('[data-testid="add-member-form"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="remove-member"]')).not.toBeNull();
  });

  it("hides write UI for viewer", async () => {
    mockApis("viewer");
    const container = mount(
      wrap(<ProjectSettingsPage />, "/projects/proj-1/settings", "/projects/:projectId/settings"),
    );
    await flushReactQuery();
    expect(container.textContent).toContain("viewer 只读");
    expect(container.querySelector('[data-testid="add-member-form"]')).toBeNull();
    expect(container.querySelector('[data-testid="remove-member"]')).toBeNull();
  });
});
