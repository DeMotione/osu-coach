/* eslint-disable react-refresh/only-export-components -- the provider and its hook belong together */
import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useState, type ReactNode } from "react";
import { flushSync } from "react-dom";

import { setWindowMica } from "./desktop";

export type ThemeChoice = "system" | "light" | "dark";
const KEY = "osu-coach:theme";

interface ThemeContext {
  choice: ThemeChoice;
  dark: boolean;
  setChoice: (c: ThemeChoice) => void;
}

const Ctx = createContext<ThemeContext | null>(null);

function stored(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

const systemDark = () => typeof window !== "undefined" && !window.matchMedia?.("(prefers-color-scheme: light)").matches;

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [choice, setChoiceState] = useState<ThemeChoice>(stored);
  const [sysDark, setSysDark] = useState(systemDark);

  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: light)");
    if (!mq) return;
    const onChange = () => setSysDark(!mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  // a layout effect, so the view transition below sees the new theme in the page it snapshots
  useLayoutEffect(() => {
    const root = document.documentElement;
    if (choice === "system") delete root.dataset.theme;
    else root.dataset.theme = choice;
  }, [choice]);

  const dark = choice === "system" ? sysDark : choice === "dark";
  useEffect(() => setWindowMica(dark), [dark]);

  const setChoice = useCallback((c: ThemeChoice) => {
    // where the browser can, the whole page cross-fades between two snapshots (see ::view-transition-* in base.css)
    if (typeof document.startViewTransition === "function") {
      document.startViewTransition(() => flushSync(() => setChoiceState(c)));
    } else {
      setChoiceState(c);
    }
    try {
      if (c === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, c);
    } catch {
      /* private window: the choice lasts until the tab closes */
    }
  }, []);

  const value = useMemo(
    () => ({ choice, dark, setChoice }),
    [choice, dark, setChoice],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useTheme(): ThemeContext {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useTheme outside ThemeProvider");
  return ctx;
}
