import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  ApprovalRequestDetail,
  ApprovalRequestListItem,
  ListEnvelope,
  ResourceEnvelope,
} from "@/api/types";
import type { ActionPreview } from "@/api/types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const apiGet = vi.fn();
const apiPost = vi.fn();

vi.mock("@/api/client", () => ({
  api: {
    get: (...args: unknown[]) => apiGet(...args),
    post: (...args: unknown[]) => apiPost(...args),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("@/hooks/useSession", () => ({
  useSession: () => ({
    phase: "ready" as const,
    me: {
      user: { id: "user-owner", display_name: "Owner", is_disabled: false },
      organization: { id: "org-1", name: "Org", slug: "org", version: 1, is_active: true, capability_controls: {} },
      memberships: [{ project_id: "proj-1", role: "owner" as const }],
      reauth_required: false,
    },
    error: null,
    refetch: vi.fn(),
  }),
}));

import { ApprovalCenterPage } from "./ApprovalCenterPage";

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

function wrap(ui: ReactNode, initialEntry = "/approvals?tab=preview") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/approvals" element={ui} />
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

const cardPayload = {
  action: { action_type: "jira_write", summary: "写入 Jira" },
  resource: { target_object_type: "failure_cluster", target_object_id: "t-1", display_name: "fc:t-1" },
  diff: {},
  data_source: { source_summary: "test" },
  model_and_skill_version: {},
  risk_level: { side_effect_level: "L2" },
  cost_estimate: { unknown_reason: "n/a" },
  rollback: { capability: "none", none_declared: true },
  param_hash: "abc123",
};

const queueItem: ApprovalRequestListItem = {
  id: "appr-1",
  action_type: "jira_write",
  target_object_type: "failure_cluster",
  target_object_id: "t-1",
  param_hash: "abc123",
  card_payload: cardPayload,
  status: "PENDING",
  initiator_id: "user-initiator",
  expires_at: "2026-08-31T00:00:00Z",
  side_effect_level: "L2",
  version: 1,
  four_eyes_self: false,
  created_at: "2026-08-31T00:00:00Z",
  updated_at: "2026-08-31T00:00:00Z",
};

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
  apiPost.mockReset();
});

describe("ApprovalCenterPage", () => {
  it("renders preview form and queue tab", async () => {
    apiGet.mockResolvedValue({
      data: { items: [] },
      page: { next_cursor: null, has_more: false },
    } satisfies ListEnvelope<ApprovalRequestListItem>);
    const previewContainer = mount(wrap(<ApprovalCenterPage />));
    await flushReactQuery();
    expect(previewContainer.textContent).toContain("发起 Preview");

    const queueContainer = mount(wrap(<ApprovalCenterPage />, "/approvals?tab=queue"));
    await flushReactQuery();
    expect(queueContainer.textContent).toContain("审批队列");
  });

  it("owner can submit preview mock without queue API-110 on preview tab", async () => {
    const preview: ActionPreview = {
      preview_id: "preview-1",
      action_type: "jira_write",
      gate: "REQUIRE_APPROVAL",
      param_hash: "abc123",
      side_effect_level: "L2",
      created_at: "2026-08-31T00:00:00Z",
      approval_request_id: "appr-1",
      card_payload: cardPayload,
      target: { object_type: "failure_cluster", object_id: "t-1" },
    };
    apiPost.mockResolvedValueOnce({ data: preview } satisfies ResourceEnvelope<ActionPreview>);

    const container = mount(wrap(<ApprovalCenterPage />));
    await flushReactQuery();

    const targetInput = container.querySelector("#preview-target-id");
    expect(targetInput).toBeTruthy();
    await act(async () => {
      const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        "value",
      )?.set;
      nativeInputValueSetter?.call(targetInput, "11111111-1111-4111-8111-111111111111");
      targetInput?.dispatchEvent(new Event("input", { bubbles: true }));
    });

    const submit = Array.from(container.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("提交 Preview"),
    );
    expect(submit).toBeTruthy();
    await act(async () => {
      submit?.click();
    });
    await flushReactQuery();

    expect(apiPost).toHaveBeenCalledWith(
      "API-120",
      "/api/v1/action-previews",
      expect.objectContaining({ action_type: "jira_write" }),
    );
    expect(container.textContent).toContain("REQUIRE_APPROVAL");
    expect(container.textContent).toContain("abc123");
  });

  it("owner can load queue mock and four-eyes grey on self-initiated card", async () => {
    const selfItem: ApprovalRequestListItem = {
      ...queueItem,
      initiator_id: "user-owner",
      four_eyes_self: true,
    };
    apiGet.mockImplementation((apiId: string, path: string) => {
      if (apiId === "API-110") {
        return Promise.resolve({
          data: { items: [selfItem] },
          page: { next_cursor: null, has_more: false },
        } satisfies ListEnvelope<ApprovalRequestListItem>);
      }
      if (apiId === "API-111") {
        return Promise.resolve({
          data: { ...selfItem, action_payload_redacted: { summary: "x" } },
        } satisfies ResourceEnvelope<ApprovalRequestDetail>);
      }
      return Promise.reject(new Error(`unexpected ${apiId} ${path}`));
    });

    const container = mount(
      wrap(<ApprovalCenterPage />, "/approvals?tab=queue&id=appr-1&perspective=inbox"),
    );
    await flushReactQuery();

    expect(apiGet).toHaveBeenCalledWith(
      "API-110",
      "/api/v1/approval-requests",
      expect.objectContaining({ perspective: "inbox" }),
    );
    expect(container.textContent).toContain("发起人本人不可批准");
    const approveBtn = Array.from(container.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("批准"),
    );
    expect(approveBtn?.disabled).toBe(true);
  });

  it("submits approve decision mock via API-112", async () => {
    apiGet.mockImplementation((apiId: string) => {
      if (apiId === "API-110") {
        return Promise.resolve({
          data: { items: [queueItem] },
          page: { next_cursor: null, has_more: false },
        } satisfies ListEnvelope<ApprovalRequestListItem>);
      }
      if (apiId === "API-111") {
        return Promise.resolve({
          data: { ...queueItem, action_payload_redacted: { summary: "x" } },
        } satisfies ResourceEnvelope<ApprovalRequestDetail>);
      }
      return Promise.reject(new Error(`unexpected ${apiId}`));
    });
    apiPost.mockResolvedValueOnce({
      data: { ...queueItem, status: "APPROVED", version: 2 },
    } satisfies ResourceEnvelope<ApprovalRequestListItem>);

    const container = mount(
      wrap(<ApprovalCenterPage />, "/approvals?tab=queue&id=appr-1&perspective=inbox"),
    );
    await flushReactQuery();

    const approveBtn = Array.from(container.querySelectorAll("button")).find((btn) =>
      btn.textContent?.includes("批准"),
    );
    expect(approveBtn).toBeTruthy();
    await act(async () => {
      approveBtn?.click();
    });
    await flushReactQuery();

    expect(apiPost).toHaveBeenCalledWith(
      "API-112",
      "/api/v1/approval-requests/appr-1/decisions",
      expect.objectContaining({ decision: "approve", expected_version: 1 }),
    );
  });
});
