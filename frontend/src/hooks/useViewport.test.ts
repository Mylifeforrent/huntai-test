import { describe, expect, it } from "vitest";
import { modeForWidth, valueForWidth } from "./useViewport";

describe("viewport breakpoints", () => {
  it("treats >=1280 as full-function desktop", () => {
    expect(modeForWidth(1280)).toBe("desktop");
    expect(valueForWidth(1440).canMutate).toBe(true);
    expect(valueForWidth(1440).sidebarIconOnly).toBe(false);
  });

  it("treats 1024–1279 as usable compact with icon sidebar", () => {
    expect(modeForWidth(1024)).toBe("compact");
    expect(modeForWidth(1279)).toBe("compact");
    expect(valueForWidth(1100).canMutate).toBe(true);
    expect(valueForWidth(1100).sidebarIconOnly).toBe(true);
  });

  it("treats <1024 as read-only browse", () => {
    expect(modeForWidth(1023)).toBe("readonly");
    expect(valueForWidth(800).canMutate).toBe(false);
    expect(valueForWidth(800).sidebarIconOnly).toBe(true);
  });
});
