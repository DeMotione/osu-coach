/* eslint-disable react-refresh/only-export-components -- the provider and its hook belong together */
import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { ApiError, api, unwrap, type Job } from "./client";
import { invalidateLibrary, invalidateResults } from "./queries";

/** One slot per kind of background work: starting a new job replaces the slot's last one. */
type JobKind = Job["kind"];
type Slots = Partial<Record<JobKind, Job>>;

interface JobsContext {
  jobs: Slots;
  /** Start a job (the request that answers with it) and follow it until it has finished. */
  start: (request: Promise<Job>) => Promise<Job>;
  dismiss: (kind: JobKind) => void;
  /** Ask the slot's running job to stop (only ``cancellable`` jobs); polling picks up when it has. */
  cancel: (kind: JobKind) => Promise<void>;
}

const Ctx = createContext<JobsContext | null>(null);
const POLL_MS = 450;
const DISCOVER_MS = 4000;

export function JobsProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [jobs, setJobs] = useState<Slots>({});
  const polling = useRef(new Set<string>());

  const seen = useRef(new Set<string>());

  const finished = useCallback(
    (job: Job) => {
      if (job.status !== "succeeded") return;
      if (job.kind === "scan") void invalidateLibrary(qc);
      if (job.kind === "analysis") {
        void invalidateResults(qc);
        if (job.result?.new_plays?.length) void invalidateLibrary(qc); // the new plays were added to the library
      }
      if (job.kind === "play_goal") void qc.invalidateQueries({ queryKey: ["play-goals"] });
    },
    [qc],
  );

  const follow = useCallback(
    (job: Job) => {
      seen.current.add(job.id);
      setJobs((s) => ({ ...s, [job.kind]: job }));
      if (job.status !== "running") {
        finished(job);
        return;
      }
      if (polling.current.has(job.id)) return;
      polling.current.add(job.id);
      const tick = async () => {
        let next: Job;
        try {
          next = await unwrap(api.GET("/api/jobs/{job_id}", { params: { path: { job_id: job.id } } }));
        } catch (e) {
          if (e instanceof ApiError && e.status === 404) {
            // the server restarted: the job is gone
            polling.current.delete(job.id);
            setJobs((s) => ({ ...s, [job.kind]: { ...job, status: "failed", error: "The app was restarted." } }));
            return;
          }
          window.setTimeout(tick, POLL_MS * 4);
          return;
        }
        setJobs((s) => (s[next.kind]?.id === next.id || !s[next.kind] ? { ...s, [next.kind]: next } : s));
        if (next.status === "running") {
          window.setTimeout(tick, POLL_MS);
        } else {
          polling.current.delete(job.id);
          finished(next);
        }
      };
      window.setTimeout(tick, POLL_MS);
    },
    [finished],
  );

  // after a reload: follow the jobs still running on the server
  useEffect(() => {
    unwrap(api.GET("/api/jobs"))
      .then((running) => running.forEach(follow))
      .catch(() => undefined);
  }, [follow]);

  // jobs the server starts by itself (a new play analysed, #71): look every few seconds, also for the ones that
  // finished in between, so a short one isn't missed
  useEffect(() => {
    let since = new Date().toISOString();
    const id = window.setInterval(() => {
      const asked = new Date().toISOString();
      unwrap(api.GET("/api/jobs", { params: { query: { finished_after: since } } }))
        .then((jobs) => {
          since = asked;
          jobs.filter((j) => !seen.current.has(j.id)).forEach(follow);
        })
        .catch(() => undefined);
    }, DISCOVER_MS);
    return () => window.clearInterval(id);
  }, [follow]);

  const start = useCallback(
    async (request: Promise<Job>) => {
      const job = await request;
      follow(job);
      return job;
    },
    [follow],
  );

  const dismiss = useCallback((kind: JobKind) => {
    setJobs((s) => {
      const next = { ...s };
      if (next[kind]?.status !== "running") delete next[kind];
      return next;
    });
  }, []);

  const cancel = useCallback(
    async (kind: JobKind) => {
      const job = jobs[kind];
      if (!job || job.status !== "running" || !job.cancellable) return;
      const next = await unwrap(api.POST("/api/jobs/{job_id}/cancel", { params: { path: { job_id: job.id } } }));
      setJobs((s) => (s[next.kind]?.id === next.id ? { ...s, [next.kind]: next } : s));
    },
    [jobs],
  );

  const value = useMemo(() => ({ jobs, start, dismiss, cancel }), [jobs, start, dismiss, cancel]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useJobs(): JobsContext {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useJobs outside JobsProvider");
  return ctx;
}

/** The slot's job and a function to start a new one; ``error`` = why the start was refused. */
export function useJob(kind: JobKind) {
  const { jobs, start, dismiss, cancel } = useJobs();
  const [error, setError] = useState<ApiError | null>(null);
  const job = jobs[kind];
  const run = useCallback(
    async (request: () => Promise<Job>) => {
      setError(null);
      try {
        return await start(request());
      } catch (e) {
        setError(e instanceof ApiError ? e : new ApiError(0, "error", String(e)));
        return null;
      }
    },
    [start],
  );
  return {
    job,
    running: job?.status === "running",
    error,
    run,
    cancel: () => {
      setError(null);
      cancel(kind).catch((e) => setError(e instanceof ApiError ? e : new ApiError(0, "error", String(e))));
    },
    dismiss: () => {
      setError(null);
      dismiss(kind);
    },
  };
}
