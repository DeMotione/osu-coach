import { createContext, useContext, useEffect, type RefObject } from "react";

export interface PageTitleState {
  /** Whether the page's own heading is in view. */
  visible: boolean;
  setVisible: (visible: boolean) => void;
}

export const PageTitleContext = createContext<PageTitleState>({ visible: true, setVisible: () => undefined });

export function usePageTitleVisible(): boolean {
  return useContext(PageTitleContext).visible;
}

/** Reports whether the heading is below the sticky toolbar, so the toolbar can show the title once it has scrolled away. */
export function useReportTitleVisibility(ref: RefObject<Element | null>) {
  const { setVisible } = useContext(PageTitleContext);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const toolbar = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--toolbar-h")) || 56;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), {
      rootMargin: `-${toolbar}px 0px 0px 0px`,
    });
    observer.observe(el);
    return () => {
      observer.disconnect();
      setVisible(true);
    };
  }, [ref, setVisible]);
}
