/* eslint-disable react-refresh/only-export-components -- the provider and its hook belong together */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { setWindowTheme } from "./desktop";

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
  const applied = useRef<ThemeChoice | null>(null);
  const fade = useRef(0);

  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: light)");
    if (!mq) return;
    const onChange = () => setSysDark(!mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    // fade only on a real change: not on the first paint, nor on StrictMode's second effect run
    if (applied.current !== null && applied.current !== choice) {
      root.classList.add("theme-fade");
      window.clearTimeout(fade.current);
      fade.current = window.setTimeout(() => root.classList.remove("theme-fade"), 350);
    }
    applied.current = choice;
    if (choice === "system") delete root.dataset.theme;
    else root.dataset.theme = choice;
    setWindowTheme(choice === "system" ? null : choice);
  }, [choice]);

  const setChoice = useCallback((c: ThemeChoice) => {
    setChoiceState(c);
    try {
      if (c === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, c);
    } catch {
      /* private window: the choice lasts until the tab closes */
    }
  }, []);

  const value = useMemo(
    () => ({ choice, dark: choice === "system" ? sysDark : choice === "dark", setChoice }),
    [choice, sysDark, setChoice],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useTheme(): ThemeContext {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useTheme outside ThemeProvider");
  return ctx;
}
