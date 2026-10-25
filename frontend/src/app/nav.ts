import type { ComponentType, SVGProps } from "react";

import {
  IconBulb,
  IconSliders,
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

interface NavItem {
  path: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  /** Needs an analysed profile to show anything: dimmed in the sidebar until one exists. */
  needsAnalysis?: boolean;
  /** What the page is for, in a sentence (the setup guide's tour). */
  about: string;
}

interface NavGroup {
  group: string;
  /** What the group's pages have in common (the setup guide's tour). */
  about: string;
  items: NavItem[];
}

/** The sidebar, top to bottom: where replays come from, what they say, what to do about it. */
export const NAV: NavGroup[] = [
  {
    group: "Replays",
    about: "Where it starts: the replays osu! coach reads, and single plays up close.",
    items: [
      {
        path: "/replays",
        label: "Replays",
        icon: IconFolder,
        about: "Find and analyse your replays. Come back after you have played to analyse again: every page updates.",
      },
      {
        path: "/check",
        label: "Detailed Map Analysis",
        icon: IconMagnify,
        about: "One play on its own: every miss and combo break with its time in the map, and your timing through it.",
      },
    ],
  },
  {
    group: "Analysis",
    about: "What your replays say about how you play, measured note by note.",
    items: [
      {
        path: "/overview",
        label: "Overview",
        icon: IconGauge,
        needsAnalysis: true,
        about: "Your level, your skills and why you miss, at a glance. The best place to start.",
      },
      {
        path: "/progress",
        label: "Progress",
        icon: IconTrend,
        needsAnalysis: true,
        about: "Every analysis is saved, so you can see how you improve by month, week or day.",
      },
      {
        path: "/aim",
        label: "Aim",
        icon: IconTarget,
        needsAnalysis: true,
        about: "Where and how your aim misses: screen areas, jump directions and distances, over- and underaim.",
      },
      {
        path: "/tapping",
        label: "Tapping",
        icon: IconKeys,
        needsAnalysis: true,
        about: "Timing spread and bias, how fast you can stream, your stamina and how you use your keys.",
      },
      {
        path: "/sliders-reading",
        label: "Sliders & Reading",
        icon: IconWave,
        needsAnalysis: true,
        about: "Slider control, and how approach rate and dense parts change your misses.",
      },
    ],
  },
  {
    group: "Improve",
    about: "What to do about it: tips, settings to try and maps to practise on.",
    items: [
      {
        path: "/tips",
        label: "Tips",
        icon: IconBulb,
        needsAnalysis: true,
        about: "Concrete tips from your numbers on what to practise, and a practice plan.",
      },
      {
        path: "/setup",
        label: "Setup Tips",
        icon: IconSliders,
        needsAnalysis: true,
        about: "What to change in your tablet area, sensitivity, offset or keys, with the exact values, and what to keep.",
      },
      {
        path: "/maps",
        label: "Skill Development",
        icon: IconMap,
        needsAnalysis: true,
        about: "Maps at your comfort level that train your weak skills, ready to put into osu! as a collection.",
      },
      {
        path: "/skills",
        label: "Goals & Training",
        icon: IconStairs,
        needsAnalysis: true,
        about: "Goals for your skills, and playlists (warm-up, comfort, push) to train one skill at a time.",
      },
    ],
  },
];

/** The pages in sidebar order, for the Alt+number shortcuts. */
export const PAGES: NavItem[] = NAV.flatMap((g) => g.items);

const isActive = (item: NavItem, pathname: string) => pathname === item.path || pathname.startsWith(`${item.path}/`);

export function currentPage(pathname: string): { group: NavGroup; item: NavItem } | null {
  for (const group of NAV) {
    const item = group.items.find((i) => isActive(i, pathname));
    if (item) return { group, item };
  }
  return null;
}
