import { Suspense, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { prefetchPage } from "./prefetch";

import { OFFLINE, isApiError } from "../api/client";
import { useJobs } from "../api/jobs";
import { useAnalysisStatus, useHealth, useMeta, useProfileSummary } from "../api/queries";
import {
  IconBook,
  IconMenu,
  IconMonitor,
  IconMoon,
  IconSidebar,
  IconSun,
  IconWarn,
  IconWinMaximize,
  IconWinMinimize,
  IconWinRestore,
  IconX,
} from "../components/icons";
import { closeWindow, isDesktop, minimizeWindow, toggleMaximizeWindow, useWindowMaximized } from "../lib/desktop";
import { stars } from "../lib/format";
import { PageTitleProvider } from "../lib/pageTitle";
import { usePageTitleVisible } from "../lib/pageTitleState";
import { useSidebarCollapsed } from "../lib/sidebar";
import { useTheme, type ThemeChoice } from "../lib/theme";
import { NAV, PAGES, currentPage } from "./nav";

function Brand({ onClick }: { onClick?: () => void }) {
  return (
    <Link className="brand" to="/replays" onClick={onClick} aria-label="osu! coach">
      <svg className="brand__mark" viewBox="0 0 256 256" aria-hidden="true">
        <circle cx="128" cy="128" r="120" className="brand__disc" />
        <circle cx="128" cy="128" r="85" className="brand__ring" />
        <circle cx="128" cy="128" r="36" className="brand__dot" />
      </svg>
      <span className="brand__name">
        osu!<b>coach</b>
      </span>
    </Link>
  );
}

/** Whether replays were analysed: until then the analysis pages have nothing to show. */
function useHasAnalysis() {
  const status = useAnalysisStatus();
  return !!status.data && status.data.profile_replays !== null;
}

function PlayerCard({ onClick }: { onClick?: () => void }) {
  const has = useHasAnalysis();
  const summary = useProfileSummary(has);
  const s = has ? summary.data : undefined;
  const name = s ? s.player_label || "(no name)" : "No player yet";
  return (
    <Link className="player" to="/replays" onClick={onClick} title={s ? `${name} · level ${stars(s.level_stars)}` : "Start on the Replays page"}>
      <span className="player__avatar" aria-hidden="true">
        {s ? (name.trim()[0] ?? "?").toUpperCase() : "?"}
      </span>
      <span className="player__text">
        <strong>{name}</strong>
        <span>{s ? `Level ${stars(s.level_stars)}` : "Scan your replays"}</span>
      </span>
    </Link>
  );
}

function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const has = useHasAnalysis();
  return (
    <nav className="sidenav" aria-label="Pages">
      {NAV.map((g) => (
        <div key={g.group} className="sidenav__group">
          <span className="sidenav__label">{g.group}</span>
          {g.items.map(({ path, label, icon: Icon, needsAnalysis }) => {
            const pending = needsAnalysis && !has;
            return (
              <NavLink
                key={path}
                to={path}
                onClick={onNavigate}
                onPointerEnter={() => prefetchPage(path)}
                onFocus={() => prefetchPage(path)}
                title={label}
                className={({ isActive: on }) => `sidenav__link${on ? " active" : ""}${pending ? " pending" : ""}`}
              >
                <Icon />
                <span className="sidenav__text">{label}</span>
                {!has && path === "/replays" && <span className="sidenav__start" title="Start here">Start</span>}
              </NavLink>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

const THEMES: { value: ThemeChoice; label: string; icon: ReactNode }[] = [
  { value: "system", label: "System", icon: <IconMonitor /> },
  { value: "light", label: "Light", icon: <IconSun /> },
  { value: "dark", label: "Dark", icon: <IconMoon /> },
];

/** All three theme choices at once as icons (named for screen readers and on hover), the current one marked. */
function ThemeSwitch() {
  const { choice, setChoice } = useTheme();
  const index = THEMES.findIndex((t) => t.value === choice);
  return (
    <div className="themeswitch" role="radiogroup" aria-label="Theme" style={{ "--i": index } as CSSProperties}>
      <span className="themeswitch__thumb" aria-hidden="true" />
      {THEMES.map((t) => (
        <label key={t.value} className={`themeswitch__option${t.value === choice ? " checked" : ""}`} title={`${t.label} theme`}>
          <input type="radio" name="theme" checked={t.value === choice} onChange={() => setChoice(t.value)} />
          {t.icon}
          <span className="visually-hidden">{t.label}</span>
        </label>
      ))}
    </div>
  );
}

/** Minimise, maximise and close for the desktop app, whose window has no native title bar. */
function WindowControls() {
  const maximized = useWindowMaximized();
  return (
    <div className="winctl">
      <button type="button" className="winctl__btn" aria-label="Minimise" title="Minimise" onClick={minimizeWindow}>
        <IconWinMinimize />
      </button>
      <button
        type="button"
        className="winctl__btn"
        aria-label={maximized ? "Restore" : "Maximise"}
        title={maximized ? "Restore" : "Maximise"}
        onClick={toggleMaximizeWindow}
      >
        {maximized ? <IconWinRestore /> : <IconWinMaximize />}
      </button>
      <button type="button" className="winctl__btn winctl__btn--close" aria-label="Close" title="Close" onClick={closeWindow}>
        <IconX />
      </button>
    </div>
  );
}

function Toolbar({ collapsed, onToggleSidebar, onOpenDrawer }: { collapsed: boolean; onToggleSidebar: () => void; onOpenDrawer: () => void }) {
  const meta = useMeta();
  const { pathname } = useLocation();
  const here = currentPage(pathname);
  const headingVisible = usePageTitleVisible();
  return (
    <header className={`toolbar${isDesktop ? " toolbar--desktop" : ""}`} data-tauri-drag-region>
      <button type="button" className="btn btn--ghost btn--icon toolbar__drawer" aria-label="Menu" onClick={onOpenDrawer}>
        <IconMenu />
      </button>
      {isDesktop && (
        <div className="toolbar__brand">
          <Brand />
        </div>
      )}
      <button
        type="button"
        className="btn btn--ghost btn--icon toolbar__fold"
        aria-label={collapsed ? "Show sidebar" : "Hide sidebar"}
        title={`${collapsed ? "Show" : "Hide"} sidebar (Ctrl+B)`}
        aria-pressed={!collapsed}
        onClick={onToggleSidebar}
      >
        <IconSidebar />
      </button>
      {here && (
        <div className={`toolbar__title${headingVisible ? "" : " shown"}`} data-testid="toolbar-title" aria-hidden={headingVisible} data-tauri-drag-region>
          {here.item.label}
        </div>
      )}
      <div className="toolbar__end">
        <ThemeSwitch />
        {meta.data?.api_docs && (
          <a className="btn btn--ghost btn--icon" href="/docs" target="_blank" rel="noreferrer" title="API reference" aria-label="API reference">
            <IconBook />
          </a>
        )}
      </div>
      {isDesktop && <WindowControls />}
    </header>
  );
}

/** What is running right now, or that nothing is. */
function JobIndicator() {
  const { jobs } = useJobs();
  const job = jobs.analysis?.status === "running" ? jobs.analysis : jobs.scan?.status === "running" ? jobs.scan : null;
  if (!job) return null;
  const known = job.progress !== null && job.progress !== undefined && Number.isFinite(job.progress);
  const label = job.kind === "scan" ? "Scanning replays…" : "Analysing replays…";
  return (
    <span className="statusbar__item statusbar__job" role="status">
      <span className="approach" aria-hidden="true" />
      <span>{job.message || label}</span>
      <span
        className={known ? "statusbar__bar" : "statusbar__bar indeterminate"}
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={known ? Math.round((job.progress as number) * 100) : undefined}
      >
        <span style={{ width: `${known ? (job.progress as number) * 100 : 35}%` }} />
      </span>
      {known && <span className="num">{Math.round((job.progress as number) * 100)}%</span>}
    </span>
  );
}

function StatusBar() {
  const health = useHealth();
  const has = useHasAnalysis();
  const summary = useProfileSummary(has);
  const offline = health.isError && isApiError(health.error, OFFLINE);
  const s = has ? summary.data : undefined;
  return (
    <footer className="statusbar">
      {offline ? (
        <span className="statusbar__item statusbar__offline" role="alert">
          <IconWarn width={14} height={14} />
          osu! coach isn't running. Start it again (osu-coach ui) — this page reconnects by itself.
        </span>
      ) : (
        <>
          <span className="statusbar__item" title="The local analysis server">
            <span className="dot statusbar__dot" aria-hidden="true" />
            {health.data ? "Connected" : "Connecting…"}
          </span>
          {s ? (
            <p className="statusbar__item status-line">
              {s.player_label || "(no name)"} · {s.replays} {s.replay_set === "best" ? "best replays" : "replays"}
            </p>
          ) : (
            <p className="statusbar__item status-line">No replays analysed yet</p>
          )}
          <JobIndicator />
        </>
      )}
      <span className="statusbar__item statusbar__version">v{health.data?.version ?? ""}</span>
    </footer>
  );
}

/** Ctrl/⌘+B folds the sidebar, Alt+1…0 jump to a page, Escape closes the drawer. */
function useShortcuts({ toggleSidebar, closeDrawer }: { toggleSidebar: () => void; closeDrawer: () => void }) {
  const navigate = useNavigate();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
      if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "b") {
        e.preventDefault();
        toggleSidebar();
      } else if (e.altKey && !e.ctrlKey && !e.metaKey && /^[0-9]$/.test(e.key) && !typing) {
        const page = PAGES[(e.key === "0" ? 10 : Number(e.key)) - 1];
        if (page) {
          e.preventDefault();
          void navigate(page.path);
        }
      } else if (e.key === "Escape") closeDrawer();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate, toggleSidebar, closeDrawer]);
}

export function Layout() {
  return (
    <PageTitleProvider>
      <Shell />
    </PageTitleProvider>
  );
}

function Shell() {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [collapsed, toggleCollapsed] = useSidebarCollapsed();
  const { pathname } = useLocation();
  const close = () => setOpen(false);
  useShortcuts({ toggleSidebar: toggleCollapsed, closeDrawer: close });

  // a page starts at its top
  useEffect(() => {
    scrollRef.current?.scrollTo(0, 0);
  }, [pathname]);

  const cls = ["app", open ? "nav-open" : "", collapsed ? "is-rail" : ""].filter(Boolean).join(" ");
  return (
    <div className={cls}>
      <aside className="sidebar">
        {!isDesktop && (
          <div className="sidebar__head">
            <Brand onClick={close} />
          </div>
        )}
        <SidebarNav onNavigate={close} />
        <div className="sidebar__foot">
          <PlayerCard onClick={close} />
        </div>
      </aside>
      <div className="scrim" onClick={close} />
      <div className="workspace">
        <Toolbar collapsed={collapsed} onToggleSidebar={toggleCollapsed} onOpenDrawer={() => setOpen(true)} />
        <div className="workspace__scroll" ref={scrollRef}>
          <main className="main">
            <Suspense fallback={<div className="page" />}>
              <div className="route" key={pathname}>
                <Outlet />
              </div>
            </Suspense>
          </main>
        </div>
        <StatusBar />
      </div>
    </div>
  );
}
