import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

/** Breakpoints from frontend_design_spec §7: 1280 desktop / 1024 usable / below read-only. */
export const VIEWPORT_DESKTOP_MIN = 1280;
export const VIEWPORT_USABLE_MIN = 1024;

export type ViewportMode = "desktop" | "compact" | "readonly";

export interface ViewportValue {
  mode: ViewportMode;
  width: number;
  canMutate: boolean;
  sidebarIconOnly: boolean;
}

const DESKTOP: ViewportValue = {
  mode: "desktop",
  width: VIEWPORT_DESKTOP_MIN,
  canMutate: true,
  sidebarIconOnly: false,
};

export const ViewportContext = createContext<ViewportValue>(DESKTOP);

export function modeForWidth(width: number): ViewportMode {
  if (width < VIEWPORT_USABLE_MIN) {
    return "readonly";
  }
  if (width < VIEWPORT_DESKTOP_MIN) {
    return "compact";
  }
  return "desktop";
}

export function valueForWidth(width: number): ViewportValue {
  const mode = modeForWidth(width);
  return {
    mode,
    width,
    canMutate: mode !== "readonly",
    sidebarIconOnly: mode !== "desktop",
  };
}

export function useViewportWidth(): number {
  const [width, setWidth] = useState(() =>
    typeof window === "undefined" ? VIEWPORT_DESKTOP_MIN : window.innerWidth,
  );
  useEffect(() => {
    const onResize = () => setWidth(window.innerWidth);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return width;
}

export function ViewportProvider({ children }: { children: ReactNode }) {
  const width = useViewportWidth();
  return <ViewportContext.Provider value={valueForWidth(width)}>{children}</ViewportContext.Provider>;
}

export function useViewport(): ViewportValue {
  return useContext(ViewportContext);
}
