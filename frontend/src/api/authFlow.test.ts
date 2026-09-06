import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./errors";
import {
  handleAuthApiError,
  isOidcFailureRecovery,
  resetAuthRedirectState,
  startOidcLogin,
  stripOidcFailureMarker,
} from "./authFlow";

afterEach(() => {
  resetAuthRedirectState();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function envelope(code: string): ApiError {
  return toAuthError(code);
}

function toAuthError(code: string): ApiError {
  return new ApiError({
    apiId: "API-005",
    path: "GET /api/v1/me",
    httpStatus: 401,
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

describe("oidc failure recovery helpers", () => {
  it("keeps unrelated query params when stripping the failure marker", () => {
    expect(stripOidcFailureMarker("/approvals?status=PENDING&oidc=failed")).toBe(
      "/approvals?status=PENDING",
    );
  });
});

describe("startOidcLogin", () => {
  it("sends prompt=login on enterprise retry", async () => {
    const assign = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        assign,
        pathname: "/home",
        search: "?oidc=failed",
        origin: "http://localhost",
        href: "http://localhost/home?oidc=failed",
      },
    });
    const fetchMock = vi.fn(async (input: RequestInfo) => {
      const url = String(input);
      expect(url).toContain("prompt=login");
      expect(url).not.toContain("oidc=failed");
      return new Response(JSON.stringify({ authorization_url: "https://idp.example/authorize" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    await startOidcLogin("/home?oidc=failed", { prompt: "login" });
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(assign).toHaveBeenCalledWith("https://idp.example/authorize");
  });
});

describe("handleAuthApiError", () => {
  it("does not auto-start OIDC when already on the recovery marker", () => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        assign: vi.fn(),
        pathname: "/",
        search: "?oidc=failed",
        origin: "http://localhost",
        href: "http://localhost/?oidc=failed",
      },
    });
    expect(isOidcFailureRecovery()).toBe(true);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    expect(handleAuthApiError(envelope("HT-AUTH-001"))).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not auto-start OIDC on HT-AUTH-003", () => {
    const replaceState = vi.fn();
    Object.defineProperty(window, "history", {
      configurable: true,
      value: { replaceState },
    });
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        assign: vi.fn(),
        pathname: "/home",
        search: "",
        origin: "http://localhost",
        href: "http://localhost/home",
      },
    });
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    expect(handleAuthApiError(envelope("HT-AUTH-003"))).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(replaceState).toHaveBeenCalled();
  });
});
