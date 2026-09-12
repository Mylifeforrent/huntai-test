import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { MutateOnly, PageHeader } from "./PageState";
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

describe("PageHeader viewport split", () => {
  it("keeps browseActions and hides command actions under 1024px", () => {
    const container = mount(
      <ViewportContext.Provider value={valueForWidth(800)}>
        <PageHeader
          title="用例库"
          browseActions={<a href="/review">生成审阅</a>}
          actions={<button type="button">Excel 导入</button>}
        />
      </ViewportContext.Provider>,
    );
    expect(container.textContent).toContain("生成审阅");
    expect(container.textContent).not.toContain("Excel 导入");
  });

  it("shows both browse and command actions on desktop", () => {
    const container = mount(
      <PageHeader
        title="用例库"
        browseActions={<a href="/review">生成审阅</a>}
        actions={<button type="button">Excel 导入</button>}
      />,
    );
    expect(container.textContent).toContain("生成审阅");
    expect(container.textContent).toContain("Excel 导入");
  });
});

describe("MutateOnly", () => {
  it("renders children when canMutate", () => {
    const container = mount(
      <MutateOnly>
        <button type="button">签发</button>
      </MutateOnly>,
    );
    expect(container.textContent).toContain("签发");
  });

  it("hides children under 1024px", () => {
    const container = mount(
      <ViewportContext.Provider value={valueForWidth(800)}>
        <MutateOnly>
          <button type="button">签发</button>
        </MutateOnly>
      </ViewportContext.Provider>,
    );
    expect(container.textContent).not.toContain("签发");
  });
});
