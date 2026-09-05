import { createRoot, type Root } from "react-dom/client";
import { act } from "react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const apiGet = vi.fn();
const apiPost = vi.fn();
const apiGetBlob = vi.fn();

vi.mock("@/api/client", () => ({
  api: {
    get: (...args: unknown[]) => apiGet(...args),
    post: (...args: unknown[]) => apiPost(...args),
    getBlob: (...args: unknown[]) => apiGetBlob(...args),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  closed = false;
  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }
  addEventListener = vi.fn();
  close(): void {
    this.closed = true;
  }
}

vi.stubGlobal("EventSource", FakeEventSource);

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

import { EvidenceCenterPage } from "./EvidenceCenterPage";

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

function wrap(initialEntries: string[]) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>
        <EvidenceCenterPage />
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

const EVIDENCE_ITEM = {
  id: "ev-1",
  claim: "login flow failed",
  source_object: { connector: "playwright", resource: "trace/1" },
  subject_type: "case_result",
  subject_id: "cr-1",
  data_classification: "Internal",
};

describe("EvidenceCenterPage", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    apiGet.mockImplementation((apiId: string, path: string) => {
      if (apiId === "API-026") {
        return Promise.resolve({
          data: { items: [EVIDENCE_ITEM] },
          page: { has_more: false, next_cursor: null },
        });
      }
      if (apiId === "API-071") {
        return Promise.resolve({
          data: {
            id: path.split("/").pop(),
            command_type: "evidence_export",
            status: "succeeded",
          },
        });
      }
      return Promise.resolve({ data: { items: [] }, page: { has_more: false } });
    });
    apiPost.mockResolvedValue({
      data: {
        id: "receipt-1",
        command_type: "evidence_export",
        status: "accepted",
        poll: { sse_path: "/api/v1/command-receipts/receipt-1/events" },
      },
    });
    apiGetBlob.mockResolvedValue(new Blob(["package"], { type: "application/zip" }));
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

  it("renders evidence items from API-026", async () => {
    const container = render(["/evidence"]);
    await flush();
    expect(container.textContent).toContain("login flow failed");
    expect(container.textContent).toContain("playwright");
    expect(container.textContent).toContain("Internal");
    expect(apiGet).toHaveBeenCalledWith("API-026", "/api/v1/evidence-objects", expect.anything());
  });

  it("requires subject filters before export", async () => {
    const container = render(["/evidence"]);
    await flush();
    const exportButton = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("导出证据包"),
    );
    expect(exportButton).toBeDefined();
    expect(exportButton?.disabled).toBe(true);
  });

  it("exports with subject scope then enables download after receipt succeeds", async () => {
    const container = render(["/evidence?subject_type=case_result&subject_id=cr-1"]);
    await flush();
    const exportButton = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("导出证据包"),
    );
    expect(exportButton?.disabled).toBe(false);
    await act(async () => {
      exportButton?.click();
    });
    await flush();
    expect(apiPost).toHaveBeenCalledWith(
      "API-028",
      "/api/v1/evidence-objects/export-packages",
      { format: "zip", subject_type: "case_result", subject_id: "cr-1" },
      expect.any(String),
    );
    expect(
      apiGet.mock.calls.some(
        (call) => call[0] === "API-071" && call[1] === "/api/v1/command-receipts/receipt-1",
      ),
    ).toBe(true);
    const downloadButton = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("下载导出包"),
    );
    expect(downloadButton).toBeDefined();
    await act(async () => {
      downloadButton?.click();
    });
    await flush();
    expect(apiGetBlob).toHaveBeenCalledWith(
      "API-223",
      "/api/v1/export-packages/receipt-1/content",
    );
  });
});
