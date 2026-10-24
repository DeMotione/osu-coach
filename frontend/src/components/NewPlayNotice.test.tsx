import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { NewPlayNotice } from "./NewPlayNotice";

const state: { job: unknown } = { job: undefined };

vi.mock("../api/jobs", () => ({ useJobs: () => ({ jobs: { analysis: state.job } }) }));

const analysis = (id: string, status: string, newPlays: { path: string; map: string }[]) => ({
  id,
  kind: "analysis",
  status,
  result: { analysed: 3, skipped: 0, best_replays: null, profile_ready: true, warnings: [], new_plays: newPlays },
});

const show = () =>
  render(
    <MemoryRouter>
      <NewPlayNotice />
    </MemoryRouter>,
  );

describe("NewPlayNotice", () => {
  beforeEach(() => {
    state.job = undefined;
  });

  it("names the new play and links to it", () => {
    state.job = analysis("j1", "succeeded", [{ path: "C:/osu/Data/r/a b.osr", map: "Artist - Title [Insane]" }]);
    show();
    expect(screen.getByText("New play analysed")).toBeInTheDocument();
    expect(screen.getByText(/Artist - Title \[Insane\]/)).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", "/check?path=C%3A%2Fosu%2FData%2Fr%2Fa%20b.osr");
  });

  it("closes", () => {
    state.job = analysis("j1", "succeeded", [{ path: "p", map: "m" }]);
    show();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("says nothing for an analysis started by hand or still running", () => {
    state.job = analysis("j2", "succeeded", []);
    const { container, rerender } = show();
    expect(container).toBeEmptyDOMElement();
    state.job = analysis("j3", "running", [{ path: "p", map: "m" }]);
    rerender(
      <MemoryRouter>
        <NewPlayNotice />
      </MemoryRouter>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
