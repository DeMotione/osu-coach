import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { ApiError, OFFLINE, type Job } from "../api/client";
import { IconFolder, IconInfo, IconWarn } from "./icons";
import { Alert, Card, Progress } from "./ui";

export function EmptyState({ title, children, icon, action, tone }: { title: string; children?: ReactNode; icon?: ReactNode; action?: ReactNode; tone?: "warn" }) {
  return (
    <div className={tone ? `state state--${tone}` : "state"}>
      {icon ?? <IconInfo />}
      <div className="state__title">{title}</div>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

/**
 * Placeholder blocks shaped like the page that is loading (keeps the layout from jumping). They fade in after a
 * short delay (`.later`), so a local API that answers at once never flashes them before the real content.
 */
export function LoadingPage({ tiles = 4 }: { tiles?: number }) {
  return (
    <>
      <div className={`tiles tiles--${tiles} later`}>
        {Array.from({ length: tiles }, (_, i) => (
          <div key={i} className="skeleton" style={{ height: 96 }} />
        ))}
      </div>
      <div className="row later">
        <div className="skeleton" style={{ height: 380 }} />
        <div className="skeleton" style={{ height: 380 }} />
      </div>
    </>
  );
}

const NO_ANALYSIS = "No replays analysed yet";

export function NoAnalysis({ message }: { message?: string }) {
  // the API's message repeats the title unless it says something else (e.g. Best replays is empty)
  const text = message && !message.startsWith(NO_ANALYSIS) ? message : undefined;
  return (
    <Card>
      <EmptyState
        icon={<IconFolder />}
        title={text ? "Nothing to show with these choices" : NO_ANALYSIS}
        action={
          <Link className="btn btn--primary" to="/replays">
            Go to Replays
          </Link>
        }
      >
        {text ?? "Scan your replays on the Replays page and press Analyse replays."}
      </EmptyState>
    </Card>
  );
}

export function ErrorCard({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const e = error instanceof ApiError ? error : null;
  const offline = e?.code === OFFLINE;
  return (
    <Card>
      <EmptyState
        icon={<IconWarn />}
        tone="warn"
        title={offline ? "osu! coach isn't running" : "Something went wrong"}
        action={
          onRetry && (
            <button className="btn" type="button" onClick={onRetry}>
              Try again
            </button>
          )
        }
      >
        {e ? e.message : String(error)}
      </EmptyState>
    </Card>
  );
}

/**
 * The data of a page query, or what to show instead: a skeleton while loading, "analyse first" before replays
 * were analysed (409 no_profile), an error card otherwise.
 */
export function QueryView<T>({
  query,
  children,
  tiles,
}: {
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
  tiles?: number;
}) {
  if (query.data !== undefined) return <>{children(query.data)}</>;
  if (query.isPending) return <LoadingPage tiles={tiles} />;
  if (query.error instanceof ApiError && query.error.code === "no_profile") return <NoAnalysis message={query.error.message} />;
  return <ErrorCard error={query.error} onRetry={() => void query.refetch()} />;
}

/** A background job's progress, or how it ended. */
export function JobStatus({ job, error, done }: { job?: Job; error?: ApiError | null; done?: (job: Job) => ReactNode }) {
  if (error) return <Alert tone="bad">{error.message}</Alert>;
  if (!job) return null;
  if (job.status === "running")
    return (
      <Progress
        value={job.progress}
        text={job.message || "Working…"}
        right={job.progress !== null && job.progress !== undefined ? `${Math.round(job.progress * 100)}%` : undefined}
      />
    );
  if (job.status === "failed") return <Alert tone="bad">{job.error}</Alert>;
  return done ? <>{done(job)}</> : null;
}
