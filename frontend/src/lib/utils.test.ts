import { describe, expect, it } from "vitest";
import { extractResourceId, tokenRemainingProjection } from "./utils";

describe("extractResourceId", () => {
  it("reads CommandReceipt.resource_id", () => {
    expect(extractResourceId({ resource_id: "run-1", status: "accepted" })).toBe("run-1");
  });

  it("reads ResourceEnvelope data.id", () => {
    expect(extractResourceId({ data: { id: "run-2", status: "PENDING" } })).toBe("run-2");
  });

  it("does not invent an id from empty payloads", () => {
    expect(extractResourceId(null)).toBeUndefined();
    expect(extractResourceId({})).toBeUndefined();
  });
});

describe("tokenRemainingProjection", () => {
  it("displays only server token_remaining", () => {
    expect(tokenRemainingProjection({ token_remaining: 42, token_budget: 100, token_reserved: 10, token_consumed: 20 })).toBe(
      "42",
    );
  });

  it("does not compute budget - reserved - consumed", () => {
    expect(
      tokenRemainingProjection({
        token_budget: 100,
        token_reserved: 10,
        token_consumed: 20,
      }),
    ).toBeUndefined();
  });
});
