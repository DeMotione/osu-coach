import { useEffect, useRef, useState } from "react";

import { useJobs } from "../api/jobs";
import { formatDuration, formatLeft, useSecondsLeft } from "../lib/eta";
import { int } from "../lib/format";
import { AnalysingArt } from "./AnalysingArt";
import { Progress } from "./ui";

/** Seconds since an ISO time, updated every second while ``on``. */
function useElapsed(since: string | undefined, on: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!on) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [on]);
  return since ? Math.max(0, (now - Date.parse(since)) / 1000) : 0;
}

/**
 * Covers the app while an analysis the player started runs (not the one osu! coach starts by itself for a new
 * play): the pages would show the old numbers until it ends anyway. It closes by itself when the analysis ends.
 */
export function AnalysisLock() {
  const job = useJobs().jobs.analysis;
  const running = job?.kind === "analysis" && job.status === "running" && !job.automatic ? job : undefined;
  const ref = useRef<HTMLDialogElement>(null);
  const paced = useSecondsLeft(running ? running.id : null, running?.progress);
  const elapsed = useElapsed(running?.created_at, !!running);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (running && !d.open) {
      if (typeof d.showModal === "function") d.showModal();
      else d.setAttribute("open", "");
    } else if (!running && d.open) {
      if (typeof d.close === "function") d.close();
      else d.removeAttribute("open");
    }
  }, [running]);

  const estimate = running?.estimate_seconds ?? null;
  // the pace once the progress tells it, until then what was expected at the start
  const left = paced ?? (estimate !== null ? Math.max(0, estimate - elapsed) : null);
  return (
    <dialog
      ref={ref}
      className="analysis-lock"
      aria-labelledby="analysis-lock-title"
      aria-describedby="analysis-lock-text"
      onCancel={(e) => e.preventDefault() /* Esc: the analysis goes on, so does this screen */}
    >
      {running && (
        <div className="analysis-lock__body">
          <AnalysingArt />
          <h2 id="analysis-lock-title">Analysing your replays</h2>
          <p id="analysis-lock-text" className="analysis-lock__text">
            Sit back and relax: grab a drink and give your wrists a stretch.
            {running.replays ? ` osu! coach is going through ${int(running.replays)} replays` : " osu! coach is going through your replays"}
            {estimate !== null ? `, which takes ${formatDuration(estimate)}.` : "."} This screen closes by itself when it is done.
          </p>
          <Progress
            value={running.progress}
            text={running.message || "Working…"}
            right={running.progress !== null && running.progress !== undefined ? `${Math.round(running.progress * 100)}%` : undefined}
          />
          <p className="analysis-lock__left" aria-live="polite">
            {left !== null ? (left < 1 && running.progress === 1 ? "Almost done…" : formatLeft(left)) : "Getting ready…"}
          </p>
          <p className="small muted">
            Closing osu! coach stops the analysis. The replays analysed so far are kept, so the next time is quicker.
          </p>
        </div>
      )}
    </dialog>
  );
}
