import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const useSession = vi.fn();
const isOidcFailureRecovery = vi.fn(() => false);

vi.mock("@/hooks/useSession", () => ({
  useSession: () => useSession(),
}));

vi.mock("@/api/session", () => ({
  isOidcFailureRecovery: () => isOidcFailureRecovery(),
  currentReturnPath: () => "/",
  startOidcLogin: vi.fn(),
}));

import { SessionGate } from "./SessionGate";
import { ApiError } from "@/api/errors";

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

afterEach(() => {
  for (const item of mounts.splice(0)) {
    act(() => {
      item.root.unmount();
    });
    item.container.remove();
  }
  isOidcFailureRecovery.mockReturnValue(false);
});

describe("SessionGate SSO recovery", () => {
  it("shows enterprise retry copy instead of auto-error retry when oidc failed", () => {
    isOidcFailureRecovery.mockReturnValue(true);
    useSession.mockReturnValue({
      phase: "blocked",
      error: new ApiError({
        apiId: "API-005",
        path: "GET /api/v1/me",
        httpStatus: 401,
        kind: "permission",
        message: "未认证",
        retryable: false,
        body: {
          code: "HT-AUTH-001",
          class: "permission",
          subclass: "unauthenticated",
          message: "未认证",
          retryable: false,
          trace_id: "t",
        },
      }),
      refetch: vi.fn(),
      me: undefined,
    });

    const container = mount(
      <MemoryRouter>
        <Routes>
          <Route element={<SessionGate />}>
            <Route index element={<div>shell</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(container.textContent).toContain("企业 SSO 未成功");
    expect(container.textContent).toContain("使用企业账号重新登录");
    expect(container.textContent).not.toContain("shell");
  });
});
