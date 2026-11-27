import { describe, expect, it } from "vitest";

import type { Schemas } from "../api/client";
import { bestAndWorst } from "./skillVerdict";

const skill = (key: string, score: number | null, stars: number | null = null, state = "measured") =>
  ({ key, label: key, score, stars, state }) as unknown as Schemas["SkillScore"];

// the scores of #151: consistency is the weakest on the Comfort Score chart
const skills = [
  skill("aim", 83, 7.0), skill("flow_aim", 76, 6.4), skill("speed", 70, 6.5), skill("stamina", 81, 6.5),
  skill("accuracy", 46, 7.2), skill("sliders", 90, 8.4), skill("reading", 54, 7.2), skill("consistency", 24, null),
];

describe("the weakest and strongest skill (Overview: Work on … first)", () => {
  it("Comfort Score: every skill on the chart counts, consistency too (#151)", () => {
    const found = bestAndWorst(skills, false)!;
    expect(found.worst.key).toBe("consistency");
    expect(found.best.key).toBe("sliders");
    expect(found.value(found.best) - found.value(found.worst)).toBe(66);
  });

  it("Star Levels: by the star rating each skill holds up on; consistency has none, so it isn't compared", () => {
    const found = bestAndWorst(skills, true)!;
    expect(found.worst.key).toBe("flow_aim");
    expect(found.best.key).toBe("sliders");
  });

  it("leaves out a skill only known to be at least something, and needs two measured skills", () => {
    const untested = [...skills.slice(0, 7), skill("consistency", 10, null, "untested")];
    expect(bestAndWorst(untested, false)!.worst.key).toBe("accuracy");
    expect(bestAndWorst([skill("aim", 50, 6)], false)).toBeNull();
  });
});
