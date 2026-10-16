import { useEffect, useState } from "react";
import type { Effect } from "@tauri-apps/api/window";

/** Whether the page runs inside the desktop app (Tauri), which has no native title bar. */
export const isDesktop = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

// styles (the title bar height, the sidebar's offset) key off this class on <html>
if (isDesktop) document.documentElement.classList.add("is-desktop");
const isWindowsDesktop = isDesktop && navigator.userAgent.includes("Windows");

// loaded on demand: the web app never needs it
const currentWindow = () => import("@tauri-apps/api/window").then((m) => m.getCurrentWindow());

/**
 * Mica exists from Windows 11, which WebView2 reports as platform version 13 or higher (Windows 10 reports 10).
 * Read from the page: Tauri does not let remote pages call the app's own commands.
 */
async function windowsSupportsMica(): Promise<boolean> {
  const data = (navigator as Navigator & { userAgentData?: { getHighEntropyValues(hints: string[]): Promise<{ platformVersion?: string }> } })
    .userAgentData;
  const version = await data?.getHighEntropyValues(["platformVersion"]);
  return parseInt(version?.platformVersion ?? "0", 10) >= 13;
}

const micaAvailable = isWindowsDesktop
  ? windowsSupportsMica()
      .then(async (supported) => {
        if (supported) {
          document.documentElement.classList.add("is-mica-desktop");
        } else {
          await currentWindow().then((w) => w.setEffects({ effects: [] }));
        }
        return supported;
      })
      .catch((error: unknown) => {
        console.error("Could not configure the Windows window backdrop.", error);
        return false;
      })
  : Promise.resolve(false);

export const minimizeWindow = () => void currentWindow().then((w) => w.minimize());
export const toggleMaximizeWindow = () => void currentWindow().then((w) => w.toggleMaximize());
export const closeWindow = () => void currentWindow().then((w) => w.close());

/** Makes the window's Mica material light or dark like the app (it does not follow the page's own theme). */
export const setWindowMica = (dark: boolean) => {
  if (!isWindowsDesktop) return;
  void micaAvailable
    .then((supported) => {
      if (!supported) return;
      // "micaDark" / "micaLight" exist in Tauri's Rust enum but are missing from its JS typings
      const effect = (dark ? "micaDark" : "micaLight") as Effect;
      return currentWindow().then((w) => w.setEffects({ effects: [effect] }));
    })
    .catch((error: unknown) => console.error("Could not update the Windows Mica backdrop.", error));
};

/** Whether the desktop window is maximized (always false in a browser). */
export function useWindowMaximized(): boolean {
  const [maximized, setMaximized] = useState(false);
  useEffect(() => {
    if (!isDesktop) return;
    let off: (() => void) | undefined;
    let gone = false;
    void currentWindow().then(async (w) => {
      const update = () => void w.isMaximized().then((m) => !gone && setMaximized(m));
      update();
      const unlisten = await w.onResized(update);
      if (gone) unlisten();
      else off = unlisten;
    });
    return () => {
      gone = true;
      off?.();
    };
  }, []);
  return maximized;
}
