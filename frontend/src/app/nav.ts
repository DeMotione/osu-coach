import type { ComponentType, SVGProps } from "react";

import {
  IconBulb,
  IconFolder,
  IconGauge,
  IconKeys,
  IconMagnify,
  IconMap,
  IconStairs,
  IconTarget,
  IconTrend,
  IconWave,
} from "../components/icons";

export interface NavItem {
  path: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  /** Needs an analysed profile to show anything: dimmed in the sidebar until one exists. */
  needsAnalysis?: boolean;
}

export interface NavGroup {
  group: string;
  items: NavItem[];
}

/** The sidebar, top to bottom: where replays come from, what they say, what to do about it. */
export const NAV: NavGroup[] = [
  {
    group: "Replays",
    items: [
      { path: "/replays", label: "Replays", icon: IconFolder },
      { path: "/check", label: "Detailed Map Analysis", icon: IconMagnify },
    ],
  },
  {
    group: "Analysis",
    items: [
      { path: "/overview", label: "Overview", icon: IconGauge, needsAnalysis: true },
      { path: "/progress", label: "Progress", icon: IconTrend, needsAnalysis: true },
      { path: "/aim", label: "Aim", icon: IconTarget, needsAnalysis: true },
      { path: "/tapping", label: "Tapping", icon: IconKeys, needsAnalysis: true },
      { path: "/sliders-reading", label: "Sliders & Reading", icon: IconWave, needsAnalysis: true },
    ],
  },
  {
    group: "Improve",
    items: [
      { path: "/tips", label: "Tips & Setup", icon: IconBulb, needsAnalysis: true },
      { path: "/maps", label: "Map Suggestion", icon: IconMap, needsAnalysis: true },
      { path: "/skills", label: "Skill Development", icon: IconStairs, needsAnalysis: true },
    ],
  },
];

/** The pages in sidebar order, for the Alt+number shortcuts. */
export const PAGES: NavItem[] = NAV.flatMap((g) => g.items);

export const isActive = (item: NavItem, pathname: string) => pathname === item.path || pathname.startsWith(`${item.path}/`);

export function currentPage(pathname: string): { group: NavGroup; item: NavItem } | null {
  for (const group of NAV) {
    const item = group.items.find((i) => isActive(i, pathname));
    if (item) return { group, item };
  }
  return null;
}
