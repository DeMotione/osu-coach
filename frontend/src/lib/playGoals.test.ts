import { describe, expect, it } from "vitest";

import type { Schemas } from "../api/client";
import { exportGoalMaps, GOAL_MODS, goalRequest } from "./playGoals";

function recommendation(mods: Schemas["GoalMap"]["mods"]): Schemas["GoalRecommendation"] {
  return {
    map: { md5: "a".repeat(32), beatmap_id: 1, beatmapset_id: 2, artist: "Artist", title: "Title", version: "Hard",
      mods, client: "stable", stars: 4, bpm: 180, ar: 9, od: 8, length_s: 120 },
    why: "Stream control", objective: `Play +${mods}; aim for 95% without breaks.`,
    step_up: "Return after two clean attempts", practice_accuracy: 0.95, achieved: false, stage: "Starter",
  };
}

describe("play goals", () => {
  it("uses explicit configuration defaults and preserves remembered inputs", () => {
    const request = goalRequest("fc");
    expect(request.client).toBe("stable");
    expect(request.mods).toBe("NM");
    expect(goalRequest("mod", { ...request, training_mod: "DT", client: "lazer" })).toMatchObject({
      goal: "mod", training_mod: "DT", client: "lazer",
    });
    expect(GOAL_MODS).toHaveLength(8);
  });

  it("exports each map once but retains instructions for every configuration", () => {
    const maps = exportGoalMaps([recommendation("HD"), recommendation("DT")]);
    expect(maps).toHaveLength(1);
    expect(maps[0].stage).toBe("+HD / +DT");
    expect(maps[0].goal).toContain("Play +HD");
    expect(maps[0].goal).toContain("Play +DT");
    expect(maps[0].stars).toBeNull();
    expect(maps[0].url).toBe("https://osu.ppy.sh/beatmaps/1");
  });
});
