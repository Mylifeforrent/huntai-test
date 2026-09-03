import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/errors";
import type { AuditEventListItem, ListEnvelope, OrganizationCurrentProjection, ResourceEnvelope } from "@/api/types";

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

import { AuditSearchPage } from "./AuditSearchPage";

const auditItem: AuditEventListItem = {
  id: "evt-1",
  created_at: "2026-09-01T00:00:00.000Z",
  data_classification: "Internal",
  actor_user_id: "user-owner",
  action: "organization.capability_tighten",
  resource_type: "organization",
  resource_id: "org-1",
  result: "ok",
};

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

function wrap(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/audit"]}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

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

beforeEach(() => {
  apiGet.mockReset();
  apiPut.mockReset();
  apiGet.mockImplementation((_apiId: string, path: string) => {
    if (path === "/api/v1/organizations/current") {
      return Promise.resolve({
        data: {
          id: "org-1",
          name: "Org",
          slug: "org",
          version: 2,
          is_active: true,
          capability_controls: {},
          siem_export_enabled: false,
          created_at: "2026-09-01T00:00:00.000Z",
          updated_at: "2026-09-01T00:00:00.000Z",
        },
      } satisfies ResourceEnvelope<OrganizationCurrentProjection>);
    }
    if (path.startsWith("/api/v1/audit-events/")) {
      return Promise.resolve({ data: auditItem } satisfies ResourceEnvelope<AuditEventListItem>);
    }
    return Promise.resolve({
      data: { items: [auditItem] },
      page: { has_more: false, next_cursor: null },
    } satisfies ListEnvelope<AuditEventListItem>);
  });
});

afterEach(() => {
  for (const item of mounts.splice(0)) {
    act(() => item.root.unmount());
    item.container.remove();
  }
});

describe("AuditSearchPage", () => {
  it("renders audit action without prompt field", async () => {
    const container = mount(wrap(<AuditSearchPage />));
    await flushReactQuery();
    expect(container.textContent).toContain("organization.capability_tighten");
    expect(container.textContent).not.toContain("prompt");
  });

  it("calls API-040 with expected_version and enabled=false", async () => {
    apiPut.mockResolvedValueOnce({
      data: { enabled: false, version: 3, destination_connector_id: null, credential_present: false },
    });
    const container = mount(wrap(<AuditSearchPage />));
    await flushReactQuery();
    const saveButton = Array.from(container.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("保存 SIEM"),
    );
    expect(saveButton).toBeTruthy();
    await act(async () => {
      saveButton!.click();
    });
    await flushReactQuery();
    expect(apiPut).toHaveBeenCalledWith(
      "API-040",
      "/api/v1/organizations/current/siem-export",
      expect.objectContaining({ expected_version: 2, enabled: false }),
    );
  });

  it("shows permission error for viewer-blocked audit list", async () => {
    apiGet.mockImplementation((_apiId: string, path: string) => {
      if (path === "/api/v1/organizations/current") {
        return Promise.resolve({
          data: {
            id: "org-1",
            version: 2,
            is_active: true,
            capability_controls: {},
            created_at: "",
            updated_at: "",
            name: "Org",
            slug: "org",
          },
        });
      }
      return Promise.reject(
        new ApiError({
          kind: "permission",
          message: "Forbidden",
          httpStatus: 403,
          apiId: "API-024",
          path: "/api/v1/audit-events",
          body: {
            code: "HT-IAM-001",
            class: "permission",
            subclass: "forbidden",
            message: "Forbidden",
            retryable: false,
            trace_id: "trace",
          },
        }),
      );
    });
    const container = mount(wrap(<AuditSearchPage />));
    await flushReactQuery();
    expect(container.textContent).toContain("无权限");
  });
});
