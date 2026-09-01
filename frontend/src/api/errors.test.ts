import { describe, expect, it } from "vitest";
import {
  classifyHttpFailure,
  isErrorEnvelope,
  isRequireReauth,
  isUnauthenticated,
  toApiError,
} from "./errors";
import { currentReturnPath, validateReturnPath } from "./authFlow";

describe("api error classifier", () => {
  it("treats fetch failures as undeveloped", () => {
    const error = toApiError({
      apiId: "API-020",
      path: "GET /api/v1/workbench",
      cause: new TypeError("Failed to fetch"),
    });
    expect(error.kind).toBe("undeveloped");
  });

  it("treats 404 without envelope as undeveloped", () => {
    expect(classifyHttpFailure(404, null)).toBe("undeveloped");
  });

  it("keeps HT-RES-001 as not_found", () => {
    expect(
      classifyHttpFailure(404, {
        code: "HT-RES-001",
        class: "permission",
        subclass: "not_found",
        message: "资源不存在",
        retryable: false,
        trace_id: "t",
      }),
    ).toBe("not_found");
  });

  it("classifies HT-AUTH-001 envelope 401 as permission not undeveloped", () => {
    const error = toApiError({
      apiId: "API-005",
      path: "GET /api/v1/me",
      httpStatus: 401,
      payload: {
        error: {
          code: "HT-AUTH-001",
          class: "permission",
          subclass: "unauthenticated",
          message: "未认证",
          retryable: false,
          trace_id: "t",
        },
      },
    });
    expect(error.kind).toBe("permission");
    expect(isUnauthenticated(error)).toBe(true);
  });

  it("classifies HT-AUTH-002 envelope 401 as permission", () => {
    const error = toApiError({
      apiId: "API-112",
      path: "POST /api/v1/approval-requests/x/decisions",
      httpStatus: 401,
      payload: {
        error: {
          code: "HT-AUTH-002",
          class: "permission",
          subclass: "require_reauth",
          message: "需再认证",
          retryable: false,
          trace_id: "t",
        },
      },
    });
    expect(error.kind).toBe("permission");
    expect(isRequireReauth(error)).toBe(true);
  });

  it("treats API-005 reauth_required hint as non-error (no bootstrap step-up)", () => {
    const mePayload = {
      data: {
        user: { id: "u1", display_name: "Test", is_disabled: false },
        organization: {
          id: "o1",
          name: "Org",
          slug: "org",
          version: 1,
          is_active: true,
          capability_controls: {},
        },
        memberships: [],
        reauth_required: true,
      },
    };
    expect(isErrorEnvelope(mePayload)).toBe(false);
    expect(isRequireReauth(mePayload)).toBe(false);
  });

  it("detects error envelope", () => {
    expect(
      isErrorEnvelope({
        error: {
          code: "HT-VAL-001",
          class: "business",
          subclass: "validation",
          message: "invalid",
          retryable: false,
          trace_id: "t",
        },
      }),
    ).toBe(true);
  });
});

describe("session helpers", () => {
  it("validates return_path whitelist", () => {
    expect(validateReturnPath("/projects")).toBe(true);
    expect(validateReturnPath("/projects?tab=1")).toBe(true);
    expect(validateReturnPath("//evil.com")).toBe(false);
    expect(validateReturnPath("https://evil.com")).toBe(false);
    expect(validateReturnPath("projects")).toBe(false);
  });

  it("builds current return path from location", () => {
    expect(currentReturnPath()).toMatch(/^\//);
  });

  it("does not reuse OIDC callback URL as return_path", () => {
    const original = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        pathname: "/api/v1/auth/oidc/callback",
        search: "?code=x&state=y",
      },
    });
    expect(currentReturnPath()).toBe("/");
    Object.defineProperty(window, "location", {
      configurable: true,
      value: original,
    });
  });
});
