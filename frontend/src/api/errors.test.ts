import { describe, expect, it } from "vitest";
import { classifyHttpFailure, isErrorEnvelope, toApiError } from "./errors";

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
