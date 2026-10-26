/** A small set of line icons (24 × 24, stroke = currentColor). */
import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement>;

function I({ children, ...p }: P) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.9} strokeLinecap="round"
      strokeLinejoin="round" aria-hidden="true" {...p}>
      {children}
    </svg>
  );
}

export const IconFolder = (p: P) => (
  <I {...p}><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></I>
);
export const IconSearch = (p: P) => (
  <I {...p}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></I>
);
export const IconMagnify = (p: P) => (
  <I {...p}><circle cx="10" cy="10" r="6" /><path d="m20 20-5.6-5.6M7.5 10h5M10 7.5v5" /></I>
);
export const IconGauge = (p: P) => (
  <I {...p}><path d="M4 18a8 8 0 1 1 16 0" /><path d="m12 18 4-6" /><path d="M8 18h8" /></I>
);
export const IconTrend = (p: P) => (
  <I {...p}><path d="m3 17 6-6 4 4 8-8" /><path d="M15 7h6v6" /></I>
);
export const IconTarget = (p: P) => (
  <I {...p}><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1.5" /></I>
);
export const IconKeys = (p: P) => (
  <I {...p}><rect x="3" y="6" width="18" height="12" rx="2" /><path d="M7 10h.01M11 10h.01M15 10h.01M7 14h10" /></I>
);
export const IconWave = (p: P) => (
  <I {...p}><path d="M3 12c2.5-5 5.5-5 8 0s5.5 5 8 0" /><circle cx="3" cy="12" r="1" /><circle cx="21" cy="12" r="1" /></I>
);
export const IconBulb = (p: P) => (
  <I {...p}><path d="M9 18h6M10 21h4" /><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z" /></I>
);
export const IconMap = (p: P) => (
  <I {...p}><path d="m9 4-6 2v14l6-2 6 2 6-2V4l-6 2z" /><path d="M9 4v14M15 6v14" /></I>
);
export const IconStairs = (p: P) => (
  <I {...p}><path d="M3 20h5v-5h5v-5h5V5h3" /></I>
);
export const IconInfo = (p: P) => (
  <I {...p}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></I>
);
export const IconHelp = (p: P) => (
  <I {...p}><circle cx="12" cy="12" r="9" /><path d="M9.6 9.3a2.5 2.5 0 0 1 4.8 1c0 1.7-2.4 2.2-2.4 3.7M12 17h.01" /></I>
);
export const IconWarn = (p: P) => (
  <I {...p}><path d="M12 4 2.5 20h19z" /><path d="M12 10v4M12 17h.01" /></I>
);
export const IconCheck = (p: P) => (
  <I {...p}><circle cx="12" cy="12" r="9" /><path d="m8 12 3 3 5-6" /></I>
);
export const IconX = (p: P) => (
  <I {...p}><path d="M6 6l12 12M18 6 6 18" /></I>
);
export const IconWinMinimize = (p: P) => (
  <I {...p} strokeWidth={1.4}><path d="M6 12h12" /></I>
);
export const IconWinMaximize = (p: P) => (
  <I {...p} strokeWidth={1.4}><rect x="6.5" y="6.5" width="11" height="11" rx="1.5" /></I>
);
export const IconWinRestore = (p: P) => (
  <I {...p} strokeWidth={1.4}><rect x="5.5" y="9.5" width="9" height="9" rx="1.5" /><path d="M9.5 9.5v-2a1.5 1.5 0 0 1 1.5-1.5h6a1.5 1.5 0 0 1 1.5 1.5v6a1.5 1.5 0 0 1-1.5 1.5h-2" /></I>
);
export const IconMenu = (p: P) => (
  <I {...p}><path d="M4 7h16M4 12h16M4 17h16" /></I>
);
export const IconDownload = (p: P) => (
  <I {...p}><path d="M12 4v11M7 10l5 5 5-5M5 20h14" /></I>
);
export const IconUpload = (p: P) => (
  <I {...p}><path d="M12 20V9M7 14l5-5 5 5M5 4h14" /></I>
);
export const IconPlay = (p: P) => (
  <I {...p}><circle cx="12" cy="12" r="9" /><path d="m10 8.5 6 3.5-6 3.5z" /></I>
);
export const IconSun = (p: P) => (
  <I {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></I>
);
export const IconMoon = (p: P) => (
  <I {...p}><path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" /></I>
);
export const IconMonitor = (p: P) => (
  <I {...p}><rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" /></I>
);
export const IconBook = (p: P) => (
  <I {...p}><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z" /><path d="M4 19V5M9 7h6" /></I>
);
export const IconExternal = (p: P) => (
  <I {...p}><path d="M14 4h6v6M20 4l-9 9" /><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></I>
);
export const IconPlus = (p: P) => (
  <I {...p}><path d="M12 5v14M5 12h14" /></I>
);
export const IconTrash = (p: P) => (
  <I {...p}><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" /></I>
);
export const IconRefresh = (p: P) => (
  <I {...p}><path d="M20 11a8 8 0 1 0-2.3 5.7" /><path d="M20 4v7h-7" /></I>
);
export const IconList = (p: P) => (
  <I {...p}><path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01" /></I>
);
export const IconSliders = (p: P) => (
  <I {...p}><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0" /><circle cx="16" cy="6" r="2" /><circle cx="10" cy="12" r="2" /><circle cx="18" cy="18" r="2" /></I>
);
export const IconSidebar = (p: P) => (
  <I {...p}><rect x="3" y="4" width="18" height="16" rx="3" /><path d="M9 4v16" /></I>
);
export const IconArrowLeft = (p: P) => (
  <I {...p}><path d="M19 12H5M11 6l-6 6 6 6" /></I>
);
export const IconArrowRight = (p: P) => (
  <I {...p}><path d="M5 12h14M13 6l6 6-6 6" /></I>
);
export const IconChevronLeft = (p: P) => (
  <I {...p}><path d="m15 6-6 6 6 6" /></I>
);
export const IconChevronRight = (p: P) => (
  <I {...p}><path d="m9 6 6 6-6 6" /></I>
);
export const IconCalendar = (p: P) => (
  <I {...p}><rect x="3.5" y="5" width="17" height="15.5" rx="2.5" /><path d="M3.5 10h17M8 3v4M16 3v4" /></I>
);
export const IconMouse = (p: P) => (
  <I {...p}><rect x="6" y="3" width="12" height="18" rx="6" /><path d="M12 7v3.5" /></I>
);
export const IconPen = (p: P) => (
  <I {...p}><path d="M15.5 4.5 19.5 8.5 9 19H5v-4z" /><path d="m13 7 4 4" /></I>
);
export const IconBolt = (p: P) => (
  <I {...p}><path d="M13 2 4.5 13.5H11L10 22l8.5-11.5H12z" /></I>
);
export const IconKeypad = (p: P) => (
  <I {...p}><rect x="3" y="6" width="18" height="12" rx="3" /><rect x="6.5" y="9.5" width="4.5" height="5" rx="1" /><rect x="13" y="9.5" width="4.5" height="5" rx="1" /></I>
);
export const IconCompass = (p: P) => (
  <I {...p}><circle cx="12" cy="12" r="9" /><path d="m15.5 8.5-2 5-5 2 2-5z" /></I>
);
export const IconOsu = (p: P) => (
  <I {...p}><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="4.5" /></I>
);
export const IconTriangles = (p: P) => (
  <I {...p}><path d="M12 3.5 21 19H3z" /><path d="m12 11 3.5 6h-7z" /></I>
);
export const IconLock = (p: P) => (
  <I {...p}><rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></I>
);
