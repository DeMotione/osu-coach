import { describe, expect, it } from "vitest";

import type { Schemas } from "../api/client";
import { blockedSkills, goalLeft, goalValue, nextTarget } from "./goals";

const goal = (skill: string, state: Schemas["GoalOut"]["state"]) =>
  ({ skill, state, target: 78, unit: "score", deadline: "2026-11-15" }) as Schemas["GoalOut"];
const skill = (key: string, label: string, score: number) => ({ key, label, score, value: score, unit: "score" as const });

describe("blockedSkills", () => {
  it("blocks skills with an open goal and skills at 100, not paused goals", () => {
    const goals = {
      skills: [skill("aim", "Jump aim", 80), skill("sliders", "Slider control", 100), skill("stamina", "Stamina", 68), skill("speed", "Tapping speed", 66)],
      open: [goal("aim", "behind"), goal("stamina", "paused")],
    } as Schemas["GoalsOut"];
    expect([...blockedSkills(goals)]).toEqual([
      ["sliders", "at 100 already"],
      ["aim", "goal: 78 by 2026-11-15"],
    ]);
  });
});

describe("goal values", () => {
  it("shows a score as a whole number and stars as a star rating (#129)", () => {
    expect(goalValue(40.4)).toBe("40");
    expect(goalValue(6.8, "stars")).toBe("6.8★");
    expect(goalValue(6.834, "stars")).toBe("6.83★");
    expect(goalValue(null, "stars")).toBe("–");
    expect(goalLeft(12)).toBe("12 points");
    expect(goalLeft(0.42, "stars")).toBe("0.42★");
  });

  it("steps a target 10 points or half a star up", () => {
    expect(nextTarget(41.6)).toBe(52);
    expect(nextTarget(95)).toBe(100);
    expect(nextTarget(6.83, "stars")).toBe(7.3);
  });

  it("blocks a skill with an open goal, and a score at 100 (a star level has no top)", () => {
    const goals = {
      skills: [
        { key: "aim", label: "Jumps", score: 100, value: 100, unit: "score" },
        { key: "speed", label: "Tapping speed", score: 99, value: 9.9, unit: "stars" },
      ],
      open: [{ skill: "speed", state: "on track", target: 10.4, unit: "stars", deadline: "2026-12-01" }],
    } as unknown as Schemas["GoalsOut"];
    const blocked = blockedSkills(goals);
    expect(blocked.get("aim")).toBe("at 100 already");
    expect(blocked.get("speed")).toBe("goal: 10.4★ by 2026-12-01");
  });
});
