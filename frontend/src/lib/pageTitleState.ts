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

/** Shows the toolbar title once the page heading has left the content's scroll area. */
export function useReportTitleVisibility(ref: RefObject<Element | null>) {
  const { setVisible } = useContext(PageTitleContext);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), {
      root: el.closest(".workspace__scroll"),
    });
    observer.observe(el);
    return () => {
      observer.disconnect();
      setVisible(true);
    };
  }, [ref, setVisible]);
}
