import { describe, expect, it } from "vitest";

import type { Schemas } from "../api/client";
import { blockedSkills } from "./goals";

const goal = (skill: string, state: Schemas["GoalOut"]["state"]) => ({ skill, state, target: 78, deadline: "2026-11-15" }) as Schemas["GoalOut"];

describe("blockedSkills", () => {
  it("blocks skills with an open goal and skills at 100, not paused goals", () => {
    const goals = {
      skills: [
        { key: "aim", label: "Jump aim", score: 80 },
        { key: "sliders", label: "Slider control", score: 100 },
        { key: "stamina", label: "Stamina", score: 68 },
        { key: "speed", label: "Tapping speed", score: 66 },
      ],
      open: [goal("aim", "behind"), goal("stamina", "paused")],
    } as Schemas["GoalsOut"];
    expect([...blockedSkills(goals)]).toEqual([
      ["sliders", "at 100 already"],
      ["aim", "goal: 78 by 2026-11-15"],
    ]);
  });
});
