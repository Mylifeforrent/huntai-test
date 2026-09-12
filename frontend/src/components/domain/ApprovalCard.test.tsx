import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { describe, expect, it, afterEach } from "vitest";
import { ApprovalCard, approvalCardFromRequest } from "./ApprovalCard";
import { ViewportContext, valueForWidth } from "@/hooks/useViewport";

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
});

describe("approval card zones", () => {
  it("keeps frozen zone order: invalid banner → 1–6 → actions", () => {
    const container = mount(
      <ApprovalCard
        card={{
          id: "ar-1",
          action: "jira_write",
          target: "cluster-1",
          status: "PENDING",
          risk: "L2",
          invalidated: true,
          diff: [{ field: "summary", from: "a", to: "b" }],
        }}
      />,
    );
    const zones = [...container.querySelectorAll("[data-zone]")].map((node) => node.getAttribute("data-zone"));
    expect(zones).toEqual(["invalid", "1", "2", "3", "4", "5", "6", "actions"]);
  });

  it("maps nine elements from card_payload, not invented fields", () => {
    const card = approvalCardFromRequest({
      id: "ar-2",
      status: "PENDING",
      action_type: "heal_apply",
      side_effect_level: "L3",
      initiator_id: "user-1",
      param_hash: "top-hash",
      version: 3,
      card_payload: {
        action: { action_type: "heal_apply", summary: "apply locator" },
        resource: { target_object_type: "test_case", target_object_id: "tc-1", display_name: "Login" },
        diff: { before: { locator: "#a" }, after: { locator: "#b" } },
        data_source: { source_summary: "cluster FC-1" },
        model_and_skill_version: { model: "gpt-4o", prompt_version: "v1" },
        risk_level: { side_effect_level: "L3" },
        cost_estimate: { amount: 0.02, unit: "USD" },
        rollback: { capability: "snapshot", snapshot_ref: "snap-1" },
        param_hash: "payload-hash",
      },
    });
    expect(card.action).toBe("apply locator");
    expect(card.target).toBe("Login");
    expect(card.risk).toBe("L3");
    expect(card.paramHash).toBe("payload-hash");
    expect(card.cost).toBe("0.02 USD");
    expect(card.diff?.[0]).toEqual({ field: "locator", from: "#a", to: "#b" });
  });

  it("keeps action zone but hides command buttons under 1024px", () => {
    const container = mount(
      <ViewportContext.Provider value={valueForWidth(800)}>
        <ApprovalCard
          card={{
            id: "ar-ro",
            action: "jira_write",
            target: "cluster-1",
            status: "PENDING",
            risk: "L1",
          }}
        />
      </ViewportContext.Provider>,
    );
    const zones = [...container.querySelectorAll("[data-zone]")].map((node) => node.getAttribute("data-zone"));
    expect(zones).toEqual(["1", "2", "3", "4", "5", "6", "actions"]);
    expect(container.textContent).toContain("只读浏览");
    const labels = [...container.querySelectorAll("button")].map((node) => node.textContent);
    expect(labels).not.toContain("批准");
    expect(labels).not.toContain("拒绝（附理由）");
  });
});
