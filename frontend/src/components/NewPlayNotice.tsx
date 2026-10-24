import { useEffect, useState } from "react";
import { Link } from "react-router";

import { useJobs } from "../api/jobs";
import { IconCheck, IconX } from "./icons";

const SHOW_MS = 20_000;

/** "New play analysed": for an analysis that took in plays osu! just saved (auto-analyse, #71), until closed or
 * after a while. */
export function NewPlayNotice() {
  const { jobs } = useJobs();
  const job = jobs.analysis;
  const [closed, setClosed] = useState<string | null>(null);
  const plays = job?.kind === "analysis" && job.status === "succeeded" && job.id !== closed ? (job.result?.new_plays ?? []) : [];
  const id = plays.length ? job?.id : undefined;

  useEffect(() => {
    if (!id) return;
    const timer = window.setTimeout(() => setClosed(id), SHOW_MS);
    return () => window.clearTimeout(timer);
  }, [id]);

  if (!id || !plays.length) return null;
  const last = plays[plays.length - 1];
  const close = () => setClosed(id);
  return (
    <div className="notice" role="status">
      <IconCheck />
      <div className="notice__body">
        <strong>{plays.length === 1 ? "New play analysed" : `${plays.length} new plays analysed`}</strong>
        <span className="notice__text">{last.map} · your pages are up to date.</span>
        <Link to={`/check?path=${encodeURIComponent(last.path)}`} onClick={close}>
          Open in Detailed Map Analysis
        </Link>
      </div>
      <button type="button" className="btn btn--ghost btn--sm" aria-label="Close" onClick={close}>
        <IconX />
      </button>
    </div>
  );
}
