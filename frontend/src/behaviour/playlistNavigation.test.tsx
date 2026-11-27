/**
 * Behaviour: going through a playlist stage's maps, five at a time (#107, #150). A failing test here means the app
 * broke a rule: fix the code, not the test (see "Behaviour tests" in AGENTS.md).
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { StageNav } from "../components/StageNav";
import { FIRST_ROUND, HISTORY, moveRound, type Rounds } from "../lib/playlist";

const nav = (rounds: Rounds) => {
  const onMove = vi.fn();
  render(<StageNav rounds={rounds} first={0} count={5} total={50} onMove={onMove} />);
  return {
    onMove,
    back: screen.getByRole("button", { name: "Back" }),
    forward: screen.getByRole("button", { name: "Forward" }),
    other: screen.getByRole("button", { name: /Other maps/ }),
  };
};

describe("going through a stage's maps", () => {
  it("shows Back and Forward always, in the same place, so the buttons never shift under the pointer", () => {
    for (const r of [FIRST_ROUND, { at: 1, latest: 2 }, { at: 2, latest: 2 }]) {
      const { back, forward } = nav(r);
      expect(back).toBeInTheDocument();
      expect(forward).toBeInTheDocument();
      document.body.innerHTML = "";
    }
  });

  it("turns Forward off on the newest group of maps: there is nothing ahead of it (#150)", () => {
    const { forward, other, onMove } = nav({ at: 2, latest: 2 });
    expect(forward).toBeDisabled();
    fireEvent.click(forward);
    expect(onMove).not.toHaveBeenCalled(); // it never loads new maps: that's what Other maps is for
    fireEvent.click(other);
    expect(onMove).toHaveBeenCalledWith("other");
  });

  it("turns Back off on the first group, and both on in between", () => {
    expect(nav(FIRST_ROUND).back).toBeDisabled();
    document.body.innerHTML = "";
    const { back, forward, onMove } = nav({ at: 1, latest: 2 });
    expect(back).toBeEnabled();
    expect(forward).toBeEnabled();
    fireEvent.click(forward);
    expect(onMove).toHaveBeenCalledWith("forward");
  });

  it("Other maps always brings a new group, and Back goes through the last 20", () => {
    let r = FIRST_ROUND;
    for (let i = 0; i < 30; i++) r = moveRound(r, "other");
    expect(r).toEqual({ at: 30, latest: 30 });
    r = moveRound({ ...r, at: 12 }, "other"); // from an older group: still a new one after the newest
    expect(r).toEqual({ at: 31, latest: 31 });
    for (let i = 0; i < 40; i++) r = moveRound(r, "back");
    expect(r.at).toBe(r.latest - HISTORY + 1);
    expect(HISTORY).toBe(20);
  });
});
