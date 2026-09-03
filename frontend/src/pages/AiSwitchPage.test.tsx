import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { OrganizationCapabilityControls, ProjectRole, ResourceEnvelope } from "@/api/types";

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
      organization: { id: "org-1", name: "Org", slug: "org", version: 2, is_active: true, capability_controls: {} },
      memberships: [{ project_id: "proj-1", role: "owner" as ProjectRole }],
      reauth_required: false,
    },
    error: null,
    refetch: vi.fn(),
  }),
}));

import { AiSwitchPage } from "./AiSwitchPage";

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

function wrap(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
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
  apiPost.mockReset();
  apiGet.mockResolvedValue({
    data: {
      id: "org-1",
      version: 2,
      capability_controls: {
        ai_global_tightened: false,
        tightened_capabilities: [],
        tightened_modules: [],
        tightened_connectors: [],
      },
    },
  });
});

afterEach(() => {
  for (const item of mounts.splice(0)) {
    act(() => item.root.unmount());
    item.container.remove();
  }
});

describe("AiSwitchPage", () => {
  it("calls API-199 tighten with expected_version and target", async () => {
    apiPost.mockResolvedValueOnce({
      data: {
        version: 3,
        tightened: true,
        effective_scope: { level: "global" },
        banner: { scope: "global" },
      } satisfies OrganizationCapabilityControls,
    } satisfies ResourceEnvelope<OrganizationCapabilityControls>);

    const container = mount(wrap(<AiSwitchPage />));
    await flushReactQuery();

    const tightenButton = Array.from(container.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("关停 (L1)"),
    );
    expect(tightenButton).toBeTruthy();
    await act(async () => {
      tightenButton!.click();
    });
    await flushReactQuery();
    const confirm = Array.from(document.body.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("立即关停"),
    );
    expect(confirm).toBeTruthy();
    await act(async () => {
      confirm!.click();
    });
    await flushReactQuery();

    expect(apiPost).toHaveBeenCalledWith(
      "API-199",
      "/api/v1/organizations/current/capability-controls/tighten",
      expect.objectContaining({
        expected_version: 2,
        target: expect.objectContaining({ level: expect.any(String) }),
      }),
    );
  });

  it("posts API-120 for restore, not API-199", async () => {
    apiGet.mockResolvedValueOnce({
      data: {
        id: "org-1",
        version: 2,
        capability_controls: {
          ai_global_tightened: true,
          tightened_capabilities: [],
          tightened_modules: [],
          tightened_connectors: [],
          banner_scope: "global",
        },
      },
    });
    apiPost.mockResolvedValueOnce({ data: { approval_request_id: "appr-1" } });

    const container = mount(wrap(<AiSwitchPage />));
    await flushReactQuery();

    const restoreButton = Array.from(container.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("申请恢复"),
    );
    expect(restoreButton).toBeTruthy();
    await act(async () => {
      restoreButton!.click();
    });
    await flushReactQuery();
    const confirm = Array.from(document.body.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("发起恢复审批"),
    );
    expect(confirm).toBeTruthy();
    await act(async () => {
      confirm!.click();
    });
    await flushReactQuery();

    expect(apiPost).toHaveBeenCalledWith(
      "API-120",
      "/api/v1/action-previews",
      expect.objectContaining({ action_type: "kill_switch_restore" }),
    );
    expect(apiPost).not.toHaveBeenCalledWith(
      "API-199",
      "/api/v1/organizations/current/capability-controls/tighten",
      expect.objectContaining({ direction: "restore" }),
    );
  });
});
