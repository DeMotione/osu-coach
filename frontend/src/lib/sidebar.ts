import { useCallback, useState } from "react";

const KEY = "osu-coach:sidebar";

/** Whether the sidebar is folded to its icon rail (kept between visits). */
export function useSidebarCollapsed(): [boolean, () => void] {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(KEY) === "rail";
    } catch {
      return false;
    }
  });
  const toggle = useCallback(() => {
    setCollapsed((c) => {
      try {
        localStorage.setItem(KEY, c ? "full" : "rail");
      } catch {
        /* private window: the choice lasts until the tab closes */
      }
      return !c;
    });
  }, []);
  return [collapsed, toggle];
}
