import { createRoot, type Root } from "react-dom/client";
import { act, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EvidenceViewer } from "./EvidenceViewer";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const apiGet = vi.fn();
const apiGetBlob = vi.fn();

vi.mock("@/api/client", () => ({
  api: {
    get: (...args: unknown[]) => apiGet(...args),
    getBlob: (...args: unknown[]) => apiGetBlob(...args),
  },
}));

async function flush() {
  for (let index = 0; index < 12; index += 1) {
    await Promise.resolve();
  }
}

function render(ui: ReactNode) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root: Root = createRoot(container);
  act(() => {
    root.render(ui);
  });
  return { container, root };
}

describe("EvidenceViewer", () => {
  beforeEach(() => {
    apiGet.mockReset();
    apiGetBlob.mockReset();
    apiGet.mockRejectedValue(new Error("API-220 must not be required to fetch content"));
    apiGetBlob.mockResolvedValue(new Blob(["bytes"], { type: "image/png" }));
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:artifact"),
      revokeObjectURL: vi.fn(),
    });
  });

  afterEach(() => {
    document.body.innerHTML = "";
    vi.unstubAllGlobals();
  });

  it("does not use object_key as media src", async () => {
    const { container } = render(
      <EvidenceViewer screenshotArtifactId="shot-1" traceArtifactId="trace-1" />,
    );
    await act(async () => {
      await flush();
    });
    const img = container.querySelector("img");
    expect(img?.getAttribute("src")).toBe("blob:artifact");
    expect(container.textContent).not.toContain("org/artifact/file.png");
    expect(apiGetBlob).toHaveBeenCalledWith("API-221", "/api/v1/artifacts/shot-1/content");
  });

  it("shows empty screenshot state without artifact id", async () => {
    const { container } = render(<EvidenceViewer />);
    await act(async () => {
      await flush();
    });
    expect(container.textContent).toContain("无截图");
    expect(container.textContent).not.toContain("org/artifact");
  });
});
