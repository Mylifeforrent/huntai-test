import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ListEnvelope, ResourceEnvelope } from "@/api/types";
import { CaseDetailPage } from "./CaseDetailPage";

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
      user: { id: "user-1", display_name: "Tester", is_disabled: false },
      organization: {
        id: "org-1",
        name: "Org",
        slug: "org",
        version: 1,
        is_active: true,
        capability_controls: {},
      },
      memberships: [{ project_id: "proj-1", role: "owner" as const }],
      reauth_required: false,
    },
    error: null,
    refetch: vi.fn(),
  }),
}));

let root: Root | null = null;
let container: HTMLDivElement | null = null;

function mockCaseDetail(
  data: Record<string, unknown>,
  versions: Record<string, unknown>[] = [],
) {
  apiGet.mockImplementation((apiId: string) => {
    if (apiId === "API-031") {
      return Promise.resolve({ data } satisfies ResourceEnvelope<Record<string, unknown>>);
    }
    if (apiId === "API-037") {
      return Promise.resolve({
        data: { items: versions },
        page: { has_more: false, next_cursor: null },
      } satisfies ListEnvelope<Record<string, unknown>>);
    }
    return Promise.resolve({ data: {} });
  });
}

function renderPage(caseId = "case-1") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root?.render(
      <Wrapper>
        <MemoryRouter initialEntries={[`/test-center/cases/${caseId}`]}>
          <Routes>
            <Route path="/test-center/cases/:caseId" element={<CaseDetailPage />} />
          </Routes>
        </MemoryRouter>
      </Wrapper>,
    );
  });
}

async function flush(times = 3) {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
  }
}

const baseCase = {
  id: "case-1",
  project_id: "proj-1",
  case_type: "web",
  lifecycle_status: "ACTIVE",
  validity: "valid",
  version: 2,
  current_version_id: "ver-1",
  steps: [],
  evidence_preview: {
    screenshot_artifact_ids: [],
    video_artifact_ids: [],
    trace_artifact_ids: [],
  },
};

describe("CaseDetailPage heal apply", () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiPost.mockReset();
  });

  afterEach(() => {
    act(() => {
      root?.unmount();
    });
    container?.remove();
    root = null;
    container = null;
  });

  it("hides apply button when fix confidence < 0.7", async () => {
    mockCaseDetail({
      ...baseCase,
      locator_health: [
        {
          locator_id: "loc-1",
          strategy: "css",
          expression: "#old",
          is_primary: true,
          health: "stale",
          failure_cluster_id: "cluster-1",
          fix_preview: {
            field: "locator_health",
            current: "#old",
            suggested: '{"locator_health":[]}',
            reason: "low",
            confidence: 0.5,
          },
        },
      ],
      locator_stale_cluster_confidence: 0.85,
    });
    renderPage();
    await flush();
    expect(container?.textContent).not.toContain("可应用");
  });

  it("shows apply button and posts API-120 when confidence >= 0.7", async () => {
    mockCaseDetail({
      ...baseCase,
      locator_health: [
        {
          locator_id: "loc-1",
          strategy: "css",
          expression: "#old",
          is_primary: true,
          health: "stale",
          failure_cluster_id: "cluster-1",
          fix_preview: {
            field: "locator_health",
            current: "#old",
            suggested: '{"locator_health":[{"locator_id":"loc-1","expression":"#new"}]}',
            reason: "match",
            confidence: 0.85,
          },
        },
      ],
      locator_stale_cluster_confidence: 0.85,
    });
    apiPost.mockResolvedValue({
      data: { gate: "REQUIRE_APPROVAL", approval_request_id: "appr-1" },
    });
    renderPage();
    await flush();
    expect(container?.textContent).toContain("可应用");
    const applyButton = Array.from(container?.querySelectorAll("button") ?? []).find((el) =>
      el.textContent?.includes("可应用"),
    );
    expect(applyButton).toBeTruthy();
    await act(async () => {
      applyButton?.click();
    });
    expect(apiPost).toHaveBeenCalledWith(
      "API-120",
      "/api/v1/action-previews",
      expect.objectContaining({
        action_type: "heal_apply",
        target_object_type: "test_case",
        payload: expect.objectContaining({
          failure_cluster_id: "cluster-1",
          fix_confidence: 0.85,
        }),
      }),
    );
  });

  it("shows degraded hint without apply button", async () => {
    mockCaseDetail({
      ...baseCase,
      locator_health: [
        {
          locator_id: "loc-1",
          strategy: "css",
          expression: "#old",
          is_primary: true,
          health: "stale",
          human_repair_hint: "Check DOM manually",
        },
      ],
      locator_stale_cluster_confidence: 0.85,
    });
    renderPage();
    await flush();
    expect(container?.textContent).toContain("人工修复提示");
    expect(container?.textContent).toContain("Check DOM manually");
    expect(container?.textContent).not.toContain("可应用");
  });

  it("rolls back to previous version via API-039", async () => {
    mockCaseDetail(
      {
        ...baseCase,
        locator_health: [],
      },
      [
        { id: "ver-2", version_seq: 2, is_current: true, data_classification: "Internal" },
        { id: "ver-1", version_seq: 1, is_current: false, data_classification: "Internal" },
      ],
    );
    apiPost.mockResolvedValue({ data: { id: "case-1", version: 3 } });
    renderPage();
    await flush();
    const rollbackButton = Array.from(container?.querySelectorAll("button") ?? []).find((el) =>
      el.textContent?.includes("回滚"),
    );
    expect(rollbackButton).toBeTruthy();
    await act(async () => {
      rollbackButton?.click();
    });
    expect(apiPost).toHaveBeenCalledWith(
      "API-039",
      "/api/v1/test-cases/case-1/rollback",
      expect.objectContaining({
        target_version_id: "ver-1",
        expected_version: 2,
      }),
    );
  });
});
