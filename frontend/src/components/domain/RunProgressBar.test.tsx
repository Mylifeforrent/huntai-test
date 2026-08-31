import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, afterEach } from "vitest";
import { RunProgressBar } from "./RunProgressBar";

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

describe("RunProgressBar", () => {
  it("shows WAITING_EXTERNAL only for execution_source=external_ci", () => {
    const script = mount(
      <MemoryRouter>
        <RunProgressBar status="RUNNING" source="script" />
      </MemoryRouter>,
    );
    expect(script.textContent?.includes("WAITING_EXTERNAL")).toBe(false);

    const ci = mount(
      <MemoryRouter>
        <RunProgressBar status="WAITING_EXTERNAL" source="external_ci" />
      </MemoryRouter>,
    );
    expect(ci.textContent?.includes("WAITING_EXTERNAL")).toBe(true);
  });

  it("links WAITING_APPROVAL to /approvals", () => {
    const container = mount(
      <MemoryRouter>
        <RunProgressBar status="WAITING_APPROVAL" source="script" />
      </MemoryRouter>,
    );
    const link = container.querySelector('a[title="跳转审批中心"]');
    expect(link?.getAttribute("href")).toBe("/approvals");
  });
});
