import { describe, expect, it } from "vitest";

import { averageAlong, jumpAngle, jumpDirection, jumpDistance, overshoot, screenPart } from "./aimWords";

describe("aim words", () => {
  it("names the groups of jumps as a player would", () => {
    expect(jumpDirection("up-right")).toBe("jumps moving up-right");
    expect(jumpDistance("<0.5")).toBe("very short jumps (under 0.5 circle)");
    expect(jumpDistance("1.5-2")).toBe("jumps of 1.5–2 circle widths");
    expect(jumpDistance("4+")).toBe("long jumps (4+ circle widths)");
    expect(jumpAngle("sharp (<60°)")).toBe("back-and-forth jumps (sharp turns)");
    expect(screenPart("top-left")).toBe("notes in the top left of the screen");
  });

  it("says over- and undershoot in circle widths, and nothing for noise", () => {
    expect(overshoot(0.04)).toMatch(/judge jump distance well/);
    expect(overshoot(0.3)).toBe("You overshoot: your clicks land about a tenth of a circle past the notes, along the jump.");
    expect(overshoot(-0.5)).toBe("You undershoot: your clicks land about a fifth of a circle short of the notes, along the jump.");
    expect(overshoot(null)).toBeNull();
  });

  it("averages the over/undershoot of the groups with enough notes", () => {
    const rows = [{ along: 0.2, objects: 100 }, { along: -0.2, objects: 300 }, { along: 5, objects: 3 }];
    expect(averageAlong(rows, 40)).toBeCloseTo(-0.1);
    expect(averageAlong([{ along: null, objects: 500 }], 40)).toBeNull();
  });
});
