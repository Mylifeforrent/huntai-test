import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const handleReauth = vi.fn<() => Promise<void>>();

vi.mock("@/api/session", () => ({
  handleReauth: () => handleReauth(),
  currentReturnPath: () => "/dashboard",
}));

import { SessionReauthNotice } from "./SessionReauthNotice";

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

beforeEach(() => {
  handleReauth.mockReset();
  handleReauth.mockResolvedValue(undefined);
});

afterEach(() => {
  for (const item of mounts.splice(0)) {
    act(() => {
      item.root.unmount();
    });
    item.container.remove();
  }
});

describe("SessionReauthNotice", () => {
  it("renders nothing when the server does not require re-auth", () => {
    const container = mount(<SessionReauthNotice active={false} />);
    expect(container.textContent).toBe("");
  });

  it("surfaces the step-up prompt when API-006 reports reauth_required", () => {
    const container = mount(<SessionReauthNotice active />);
    expect(container.textContent).toContain("需要重新认证");
    expect(container.textContent).toContain("重新认证");
  });

  it("starts the existing re-auth flow on click", async () => {
    const container = mount(<SessionReauthNotice active />);
    const button = container.querySelector("button");
    expect(button).not.toBeNull();

    await act(async () => {
      button?.click();
    });

    expect(handleReauth).toHaveBeenCalledTimes(1);
  });

  it("shows the failure message and re-enables the action when re-auth fails", async () => {
    handleReauth.mockRejectedValue(new Error("再认证失败"));
    const container = mount(<SessionReauthNotice active />);

    await act(async () => {
      container.querySelector("button")?.click();
    });

    expect(container.textContent).toContain("再认证失败");
    expect(container.querySelector("button")?.hasAttribute("disabled")).toBe(false);
  });
});
