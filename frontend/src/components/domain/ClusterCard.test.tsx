import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ClusterCard } from "@/components/domain/ClusterCard";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

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
  for (const { root, container } of mounts.splice(0)) {
    act(() => root.unmount());
    container.remove();
  }
});

describe("ClusterCard", () => {
  it("hides apply when confidence is 0.3", () => {
    const container = mount(
      <ClusterCard
        cluster={{
          id: "c1",
          category: "unknown",
          confidence: 0.3,
          blocking: "uncertain",
          canShowApply: true,
          fixes: [{ field: "assertions", current: "1", suggested: "2", reason: "x", confidence: 0.85, can_auto_apply: false }],
        }}
      />,
    );
    expect(container.textContent).not.toContain("可应用");
  });

  it("shows apply and posts handler when confidence is 0.85 and not degraded", () => {
    const onApply = vi.fn();
    const container = mount(
      <ClusterCard
        cluster={{
          id: "c1",
          category: "assertion_real_bug",
          confidence: 0.85,
          blocking: "blocker",
          canShowApply: true,
          ruleFallback: false,
          fixes: [{ field: "assertions", current: "1", suggested: "2", reason: "x", confidence: 0.85, can_auto_apply: false }],
        }}
        onApply={onApply}
      />,
    );
    expect(container.textContent).toContain("可应用");
    const button = container.querySelector("button:last-of-type");
    expect(button).toBeTruthy();
    act(() => {
      button?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(onApply).toHaveBeenCalledTimes(1);
  });
});
