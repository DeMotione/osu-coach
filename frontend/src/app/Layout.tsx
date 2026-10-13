import { Suspense, useState } from "react";
import { Link, NavLink, Outlet } from "react-router";

import { OFFLINE, isApiError } from "../api/client";
import { useJobs } from "../api/jobs";
import { useAnalysisStatus, useHealth, useProfileSummary } from "../api/queries";
import { IconBook, IconMenu, IconMonitor, IconMoon, IconSun, IconWarn } from "../components/icons";
import { Progress, Segmented } from "../components/ui";
import { stars } from "../lib/format";
import { useTheme, type ThemeChoice } from "../lib/theme";
import { NAV } from "./nav";

function Brand({ onClick }: { onClick?: () => void }) {
  return (
    <Link className="brand" to="/replays" onClick={onClick}>
      <img src="/favicon.svg" alt="" />
      <span>osu! coach</span>
    </Link>
  );
}

function StatusLine() {
  const status = useAnalysisStatus();
  const summary = useProfileSummary(!!status.data && status.data.profile_replays !== null);
  const s = summary.data;
  if (!s) return <p className="status-line">Start on the Replays page.</p>;
  return (
    <p className="status-line">
      <strong>{s.player_label || "(no name)"}</strong> · {s.replays} {s.replay_set === "best" ? "best replays" : "replays"}
      <br />
      {s.notes.toLocaleString("en-US")} notes · level {stars(s.level_stars)}
    </p>
  );
}

function RunningJob() {
  const { jobs } = useJobs();
  const job = jobs.analysis?.status === "running" ? jobs.analysis : jobs.scan?.status === "running" ? jobs.scan : null;
  if (!job) return null;
  return <Progress value={job.progress} text={job.kind === "scan" ? "Scanning…" : "Analysing…"} />;
}

const THEMES = [
  { value: "system" as ThemeChoice, label: <IconMonitor width={15} height={15} aria-label="System theme" /> },
  { value: "light" as ThemeChoice, label: <IconSun width={15} height={15} aria-label="Light theme" /> },
  { value: "dark" as ThemeChoice, label: <IconMoon width={15} height={15} aria-label="Dark theme" /> },
];

function OfflineBanner() {
  const health = useHealth();
  if (!health.isError || !isApiError(health.error, OFFLINE)) return null;
  return (
    <div className="banner" role="alert">
      <IconWarn width={18} height={18} style={{ color: "var(--warn)" }} />
      <span>osu! coach isn't running. Start it again (osu-coach ui) — this page reconnects by itself.</span>
    </div>
  );
}

export function Layout() {
  const [open, setOpen] = useState(false);
  const { choice, setChoice } = useTheme();
  const close = () => setOpen(false);

  return (
    <div className={open ? "app nav-open" : "app"}>
      <header className="topbar">
        <button type="button" className="btn btn--ghost btn--icon" aria-label="Menu" onClick={() => setOpen(true)}>
          <IconMenu />
        </button>
        <Brand />
      </header>
      <div className="scrim" onClick={close} />
      <aside className="sidebar" aria-label="Pages">
        <Brand onClick={close} />
        <nav className="nav">
          {NAV.map((g) => (
            <div key={g.group} className="nav__group">
              <span className="nav__label">{g.group}</span>
              {g.items.map(({ path, label, icon: Icon }) => (
                <NavLink key={path} to={path} className="nav__link" onClick={close}>
                  <Icon />
                  {label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar__foot">
          <RunningJob />
          <StatusLine />
          <div className="sidebar__links">
            <Segmented label="Theme" icons options={THEMES} value={choice} onChange={setChoice} />
            <a className="btn btn--ghost btn--sm" href="/docs" target="_blank" rel="noreferrer" title="API reference">
              <IconBook /> API
            </a>
          </div>
        </div>
      </aside>
      <main className="main">
        <Suspense fallback={<div className="page" />}>
          <Outlet />
        </Suspense>
      </main>
      <OfflineBanner />
    </div>
  );
}
