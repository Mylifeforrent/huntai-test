import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/errors";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const get = vi.fn();

vi.mock("@/api/client", () => ({
  api: { get: (...args: unknown[]) => get(...args) },
}));

import { useReauthRequired, useSession, type SessionPhase } from "./useSession";

function apiError(code: string, httpStatus: number): ApiError {
  return new ApiError({
    apiId: "API-005",
    path: "GET /api/v1/me",
    httpStatus,
    kind: "permission",
    message: code,
    retryable: false,
    body: {
      code,
      class: "permission",
      subclass: "unauthenticated",
      message: code,
      retryable: false,
      trace_id: "t",
    },
  });
}

const mounts: Array<{ root: Root; container: HTMLDivElement }> = [];

/** Render a probe component and let the query + effects settle. */
async function renderProbe(node: ReactNode): Promise<void> {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const root = createRoot(container);
  await act(async () => {
    root.render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
  });
  mounts.push({ root, container });
}

async function until(predicate: () => boolean, timeoutMs = 2000): Promise<void> {
  const started = Date.now();
  while (!predicate()) {
    if (Date.now() - started > timeoutMs) {
      throw new Error("timed out waiting for condition");
    }
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 5));
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
  get.mockReset();
});

describe("useSession", () => {
  it("keeps the shell browsable when the L3+ step-up window elapsed", async () => {
    get.mockRejectedValue(apiError("HT-AUTH-002", 401));
    const seen: { phase: SessionPhase; error: unknown } = {
      phase: "bootstrapping",
      error: null,
    };

    function Probe() {
      const session = useSession();
      seen.phase = session.phase;
      seen.error = session.error;
      return null;
    }

    await renderProbe(<Probe />);
    await until(() => seen.phase !== "bootstrapping");

    expect(seen.phase).toBe("ready");
    expect(seen.error).toBeNull();
  });

  it("still blocks the shell when the session has no org context", async () => {
    get.mockRejectedValue(apiError("HT-IAM-001", 403));
    const seen: { phase: SessionPhase } = { phase: "bootstrapping" };

    function Probe() {
      seen.phase = useSession().phase;
      return null;
    }

    await renderProbe(<Probe />);
    await until(() => seen.phase !== "bootstrapping");

    expect(seen.phase).toBe("blocked");
  });
});

describe("useReauthRequired", () => {
  it("reflects API-006's reauth_required flag", async () => {
    get.mockResolvedValue({
      expires_at: "2030-01-01T00:00:00+00:00",
      reauth_required: true,
    });
    const seen: { value: boolean } = { value: false };

    function Probe() {
      seen.value = useReauthRequired();
      return null;
    }

    await renderProbe(<Probe />);
    await until(() => seen.value);

    expect(get.mock.calls[0]?.[0]).toBe("API-006");
    expect(get.mock.calls[0]?.[1]).toBe("/api/v1/auth/session");
  });

  it("does not prompt when the server reports no re-auth needed", async () => {
    get.mockResolvedValue({
      expires_at: "2030-01-01T00:00:00+00:00",
      reauth_required: false,
    });
    const seen: { value: boolean | null } = { value: null };

    function Probe() {
      seen.value = useReauthRequired();
      return null;
    }

    await renderProbe(<Probe />);
    await until(() => seen.value !== null);

    expect(seen.value).toBe(false);
  });
});
