import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ResourceEnvelope } from "@/api/types";
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

function wrap(ui: ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/approvals?tab=preview"]}>
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
  it("renders preview form and queue undeveloped tab", async () => {
    const container = mount(wrap(<ApprovalCenterPage />));
    await flushReactQuery();
    expect(container.textContent).toContain("发起 Preview");
    expect(container.textContent).toContain("action_type");
    expect(container.textContent).not.toContain("API-110");
  });

  it("owner can submit preview mock without queue API-110", async () => {
    const preview: ActionPreview = {
      preview_id: "preview-1",
      action_type: "jira_write",
      gate: "REQUIRE_APPROVAL",
      param_hash: "abc123",
      side_effect_level: "L2",
      created_at: "2026-08-31T00:00:00Z",
      approval_request_id: "appr-1",
      card_payload: {
        action: { action_type: "jira_write", summary: "写入 Jira" },
        resource: { target_object_type: "failure_cluster", target_object_id: "t-1" },
        diff: {},
        data_source: { source_summary: "test" },
        model_and_skill_version: {},
        risk_level: { side_effect_level: "L2" },
        cost_estimate: { unknown_reason: "n/a" },
        rollback: { capability: "none", none_declared: true },
        param_hash: "abc123",
      },
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
    expect(apiGet).not.toHaveBeenCalledWith("API-110", expect.anything(), expect.anything());
    expect(container.textContent).toContain("REQUIRE_APPROVAL");
    expect(container.textContent).toContain("abc123");
  });
});
