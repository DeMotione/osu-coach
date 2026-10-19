import { useEffect } from "react";

/** The page's name in the browser tab. */
export function useTitle(title: string): void {
  useEffect(() => {
    document.title = `${title} · osu! coach`;
  }, [title]);
}
