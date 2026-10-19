/** How long a background job still needs, judged by its progress so far. */
import { useEffect, useRef, useState } from "react";

/** A job's progress (0–1) at a moment (ms). */
export interface Sample {
  t: number;
  p: number;
}

const MIN_PROGRESS = 0.02;
const MIN_MS = 3000;

/** Seconds left at ``now`` (ms) at the pace from ``first`` to ``last``; null while there is too little to go on. */
export function secondsLeft(first: Sample, last: Sample, now: number): number | null {
  const dp = last.p - first.p;
  const dt = last.t - first.t;
  if (dp < MIN_PROGRESS || dt < MIN_MS || last.p >= 1) return null;
  const end = first.t + (dt / dp) * (1 - first.p);
  return Math.max(0, (end - now) / 1000);
}

/** "about 3 minutes left": rounded, as an estimate should be. */
export function formatLeft(seconds: number): string {
  if (seconds < 50) return "less than a minute left";
  const minutes = Math.round(seconds / 60);
  if (minutes <= 1) return "about a minute left";
  if (minutes < 60) return `about ${minutes} minutes left`;
  const rounded = Math.round(minutes / 5) * 5;
  const h = Math.floor(rounded / 60);
  const m = rounded % 60;
  return m ? `about ${h} h ${m} min left` : `about ${h} h left`;
}

/**
 * Seconds a job (``key``) still needs at its pace so far, updated every second; null until its progress has moved
 * enough to tell. Progress that goes back (the next phase of a job: downloads, then the analysis) starts afresh.
 */
export function useSecondsLeft(key: string | null, progress: number | null | undefined): number | null {
  const samples = useRef<{ key: string | null; first: Sample | null; last: Sample | null }>({ key: null, first: null, last: null });
  const [left, setLeft] = useState<{ key: string; seconds: number | null } | null>(null);

  useEffect(() => {
    const s = samples.current;
    const now = performance.now();
    const known = progress !== null && progress !== undefined && Number.isFinite(progress) && progress > 0;
    if (s.key !== key || !known || !s.last || progress < s.last.p) {
      s.key = key;
      s.first = known ? { t: now, p: progress } : null;
    }
    s.last = known ? { t: now, p: progress } : null;
  }, [key, progress]);

  useEffect(() => {
    if (!key) return;
    const id = window.setInterval(() => {
      const { first, last } = samples.current;
      setLeft({ key, seconds: first && last && samples.current.key === key ? secondsLeft(first, last, performance.now()) : null });
    }, 1000);
    return () => window.clearInterval(id);
  }, [key]);

  return left && left.key === key ? left.seconds : null;
}
