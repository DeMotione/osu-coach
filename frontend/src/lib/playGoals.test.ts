import { describe, expect, it } from "vitest";

import type { Schemas } from "../api/client";
import { exportGoalMaps, GOAL_MODS, goalMods, goalRequest, matchesMap, toggleMods } from "./playGoals";

function recommendation(mods: Schemas["GoalMap"]["mods"]): Schemas["GoalRecommendation"] {
  return {
    map: { md5: "a".repeat(32), beatmap_id: 1, beatmapset_id: 2, artist: "Artist", title: "Title", version: "Hard",
      mods, client: "stable", stars: 4, bpm: 180, ar: 9, od: 8, length_s: 120 },
    why: "Stream control", objective: `Play +${mods}, aim for 95%, no combo breaks.`,
    step_up: "Return after two clean attempts", practice_accuracy: 0.95, achieved: false, stage: "Starter",
  };
}

describe("play goals", () => {
  it("uses explicit configuration defaults and preserves remembered inputs", () => {
    const request = goalRequest("fc");
    expect(request.client).toBe("lazer");
    expect(request.mods).toBe("NM");
    expect(goalRequest("mod", { ...request, training_mod: "DT", client: "stable" })).toMatchObject({
      goal: "mod", training_mod: "DT", client: "lazer",
    });
    expect(GOAL_MODS).toHaveLength(8);
  });

  it("reads a replay's mods as a goal combination, in any order (#127)", () => {
    expect(goalMods("HDDT")).toBe("HDDT");
    expect(goalMods("DTHD")).toBe("HDDT");
    expect(goalMods("NCHD")).toBe("HDDT");
    expect(goalMods("HDHRDTCL")).toBe("HDHRDT");
    expect(goalMods("HD,DT")).toBe("HDDT");
    expect(goalMods("NM")).toBe("NM");
    expect(goalMods("NFSD")).toBe("NM");
    expect(goalMods("EZHD")).toBeUndefined();
    expect(goalMods("HT")).toBeUndefined();
    expect(goalMods("HDFL")).toBeUndefined();
  });

  it("finds a map by every word of the search, in any case and order", () => {
    const map = "VOID – Tech Occultism [Proeza]";
    expect(matchesMap(map, "")).toBe(true);
    expect(matchesMap(map, "  proeza  tech ")).toBe(true);
    expect(matchesMap(map, "void occultism")).toBe(true);
    expect(matchesMap(map, "tech insane")).toBe(false);
  });

  it("builds a training mod combination from toggles", () => {
    expect(toggleMods("HD", "DT", true)).toBe("HDDT");
    expect(toggleMods("HDDT", "HD", false)).toBe("DT");
    expect(toggleMods("HR", "EZ", true)).toBe("EZ");
    expect(toggleMods("EZDT", "HR", true)).toBe("HRDT");
    expect(toggleMods("DT", "DT", false)).toBe("DT");
    expect(toggleMods("DT", "DT", false, true)).toBe("NM");
    expect(toggleMods("NM", "HD", true, true)).toBe("HD");
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
