const loaders: Record<string, () => Promise<unknown>> = {
  "/replays": () => import("../pages/ReplaysPage"),
  "/check": () => import("../pages/CheckPage"),
  "/overview": () => import("../pages/OverviewPage"),
  "/progress": () => import("../pages/ProgressPage"),
  "/aim": () => import("../pages/AimPage"),
  "/tapping": () => import("../pages/TappingPage"),
  "/sliders-reading": () => import("../pages/SlidersReadingPage"),
  "/tips": () => import("../pages/TipsPage"),
  "/maps": () => import("../pages/MapsPage"),
  "/skills": () => import("../pages/SkillsPage"),
};

/** Starts loading a page's code before it is opened; the module cache makes repeats free. */
export function prefetchPage(path: string) {
  void loaders[path]?.().catch(() => undefined);
}
