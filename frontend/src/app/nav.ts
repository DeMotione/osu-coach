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
}

export const NAV: { group: string; items: NavItem[] }[] = [
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
      { path: "/overview", label: "Overview", icon: IconGauge },
      { path: "/progress", label: "Progress", icon: IconTrend },
      { path: "/aim", label: "Aim", icon: IconTarget },
      { path: "/tapping", label: "Tapping", icon: IconKeys },
      { path: "/sliders-reading", label: "Sliders & Reading", icon: IconWave },
    ],
  },
  {
    group: "Improve",
    items: [
      { path: "/tips", label: "Tips & Setup", icon: IconBulb },
      { path: "/maps", label: "Map Suggestion", icon: IconMap },
      { path: "/skills", label: "Skill Development", icon: IconStairs },
    ],
  },
];
