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

  it("calls onCorrect with draft values", () => {
    const onCorrect = vi.fn();
    const container = mount(
      <ClusterCard
        cluster={{
          id: "c1",
          category: "unknown",
          confidence: 0.3,
          blocking: "uncertain",
        }}
        onCorrect={onCorrect}
      />,
    );
    const inputs = container.querySelectorAll("input");
    act(() => {
      inputs[0]?.dispatchEvent(new Event("input", { bubbles: true }));
      (inputs[0] as HTMLInputElement).value = "flaky";
      inputs[0]?.dispatchEvent(new Event("change", { bubbles: true }));
    });
    const correctButton = Array.from(container.querySelectorAll("button")).find((el) =>
      el.textContent?.includes("提交修正留痕"),
    );
    act(() => {
      correctButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(onCorrect).toHaveBeenCalled();
  });

  it("shows jira button and invokes handler when allowed", () => {
    const onCreateJira = vi.fn();
    const container = mount(
      <ClusterCard
        cluster={{
          id: "c1",
          category: "assertion_real_bug",
          confidence: 0.85,
          blocking: "blocker",
        }}
        showJiraButton
        onCreateJira={onCreateJira}
      />,
    );
    const button = Array.from(container.querySelectorAll("button")).find((el) =>
      el.textContent?.includes("一键创建 Jira 缺陷"),
    );
    expect(button).toBeTruthy();
    act(() => {
      button?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(onCreateJira).toHaveBeenCalledTimes(1);
  });

  it("hides jira button when showJiraButton is false", () => {
    const container = mount(
      <ClusterCard
        cluster={{
          id: "c1",
          category: "unknown",
          confidence: 0.3,
          blocking: "uncertain",
        }}
        showJiraButton={false}
      />,
    );
    expect(container.textContent).not.toContain("一键创建 Jira 缺陷");
  });

  it("renders empty similar list copy", () => {
    const container = mount(
      <ClusterCard
        cluster={{
          id: "c1",
          category: "unknown",
          confidence: 0.3,
          blocking: "uncertain",
          similarItems: [],
        }}
      />,
    );
    expect(container.textContent).toContain("无相似失败");
  });
});
