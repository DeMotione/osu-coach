import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AnalysisLock } from "./AnalysisLock";

const state: { job: unknown } = { job: undefined };

vi.mock("../api/jobs", () => ({ useJobs: () => ({ jobs: { analysis: state.job } }) }));

const analysis = (status: string, more: Record<string, unknown> = {}) => ({
  id: "j1",
  kind: "analysis",
  status,
  progress: 0.25,
  message: "Analysing replays… 125/500",
  created_at: new Date().toISOString(),
  automatic: false,
  replays: 500,
  estimate_seconds: 190,
  result: null,
  ...more,
});

describe("AnalysisLock", () => {
  beforeEach(() => {
    state.job = undefined;
  });

  it("covers the app while an analysis the player started runs", () => {
    state.job = analysis("running");
    render(<AnalysisLock />);
    const dialog = screen.getByRole("dialog", { name: "Analysing your replays" });
    expect(dialog).toHaveAttribute("open");
    expect(dialog).toHaveTextContent("going through 500 replays, which takes about 3 minutes");
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "25");
    expect(screen.getByRole("img", { name: /relaxing with a cup of tea/ })).toBeInTheDocument();
  });

  it("stays away for a new play osu! coach analyses by itself, and once the analysis is over", () => {
    state.job = analysis("running", { automatic: true });
    const { rerender } = render(<AnalysisLock />);
    expect(screen.queryByRole("dialog")).toBeNull();
    state.job = analysis("succeeded");
    rerender(<AnalysisLock />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
