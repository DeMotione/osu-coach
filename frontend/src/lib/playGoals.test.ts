import { describe, expect, it } from "vitest";

import type { Schemas } from "../api/client";
import {
  exportGoalMaps, GOAL_MODS, goalMods, goalModsOfLabel, goalRequest, matchesMap, modsText, toggleMods, validRate,
} from "./playGoals";

function recommendation(mods: Schemas["GoalMap"]["mods"], rate = mods.includes("DT") ? 1.5 : 1): Schemas["GoalRecommendation"] {
  return {
    map: { md5: "a".repeat(32), beatmap_id: 1, beatmapset_id: 2, artist: "Artist", title: "Title", version: "Hard",
      mods, rate, client: "stable", stars: 4, bpm: 180, ar: 9, od: 8, length_s: 120 },
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
    const mods = (m: string, rate?: number) => goalMods(m, rate)?.mods;
    expect(mods("HDDT")).toBe("HDDT");
    expect(mods("DTHD", 1.5)).toBe("HDDT");
    expect(mods("NCHD")).toBe("HDDT");
    expect(mods("HDHRDTCL")).toBe("HDHRDT");
    expect(mods("HD,DT")).toBe("HDDT");
    expect(mods("NM", 1)).toBe("NM");
    expect(mods("NFSD")).toBe("NM");
    expect(goalMods("EZHD")).toBeUndefined();
    expect(goalMods("HT", 0.75)).toBeUndefined();
    expect(goalMods("HDFL")).toBeUndefined();
  });

  it("keeps a replay's custom DT speed, when a goal can be at it", () => {
    expect(goalMods("HDDT", 1.5)).toEqual({ mods: "HDDT", rate: null });
    expect(goalMods("DTHD", 1.2)).toEqual({ mods: "HDDT", rate: 1.2 });
    expect(goalMods("DT", 1.05)).toBeUndefined(); // from 1.10
    expect(goalMods("HD", 1.2)).toBeUndefined(); // a speed goes with DT
    expect(goalModsOfLabel("HDDT ×1.26")).toEqual({ mods: "HDDT", rate: 1.26 });
    expect(goalModsOfLabel("HR")).toEqual({ mods: "HR", rate: null });
    expect(modsText("HDDT", 1.2)).toBe("+HDDT ×1.20");
    expect(modsText("DT", 1.5)).toBe("+DT");
    expect(modsText("HT", 0.75)).toBe("+HT");
    expect(validRate("DT", 1.234)).toBe(false);
    expect(validRate("DT", null) && validRate("DT", 2) && !validRate("HR", 1.2)).toBe(true);
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
    const maps = exportGoalMaps([recommendation("HD"), recommendation("DT"), recommendation("DT", 1.2)]);
    expect(maps).toHaveLength(1);
    expect(maps[0].stage).toBe("+HD / +DT / +DT ×1.20");
    expect(maps[0].goal).toContain("Play +HD");
    expect(maps[0].goal).toContain("Play +DT");
    expect(maps[0].stars).toBeNull();
    expect(maps[0].url).toBe("https://osu.ppy.sh/beatmaps/1");
  });
});
