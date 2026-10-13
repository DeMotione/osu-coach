import { useEffect, useRef } from "react";

/** Call ``fn`` once ``value`` has stopped changing for ``ms`` (skips the first value). */
export function useDebouncedEffect<T>(value: T, ms: number, fn: (value: T) => void): void {
  const first = useRef(true);
  const latest = useRef(fn);
  useEffect(() => {
    latest.current = fn;
  });
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    const id = window.setTimeout(() => latest.current(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
}

/** The page's name in the browser tab. */
export function useTitle(title: string): void {
  useEffect(() => {
    document.title = `${title} · osu! coach`;
  }, [title]);
}
