/**
 * Behaviour: "Practise this" on an analysis page makes a playlist for exactly the weak spot found (#144). A failing
 * test here means the app broke a rule: fix the code, not the test (see "Behaviour tests" in AGENTS.md).
 */
import { describe, expect, it } from "vitest";

import { NO_PLAYLIST, practised, type SavedPlaylist } from "../lib/playlist";
import { aimSpot, approachRates, practiseUrl, sliderStretch, streamLengths, streamSpeeds } from "../lib/practise";

describe("Practise this", () => {
  it("Tapping: the weak stream speeds, neighbours joined", () => {
    expect(streamSpeeds([120, 140, 150, 180, 200])).toEqual({ skill: "speed", focus: "bpm:120-130,140-160,180-190,200-210" });
  });

  it("Tapping: stamina at the stream length where it gives in", () => {
    expect(streamLengths([12, 20])).toEqual({ skill: "stamina", focus: "run:12-20" });
  });

  it("Aim: each weak spot a map can have; a jump direction no map statistic tells, so it has no button", () => {
    expect(aimSpot("quadrant", "bottom-right")).toEqual({ skill: "aim", focus: "quadrant:bottom-right" });
    expect(aimSpot("distance", "4+")).toEqual({ skill: "aim", focus: "jump:long" });
    expect(aimSpot("angle", "sharp (<60°)")).toEqual({ skill: "aim", focus: "angle:sharp" });
    expect(aimSpot("direction", "up-left")).toBeNull();
  });

  it("Sliders & Reading: long or fast sliders, and the weak approach rates", () => {
    expect(sliderStretch("length", 7, 8)).toEqual({ skill: "sliders", focus: "slider_length:long" });
    expect(sliderStretch("speed", 13, 16)).toEqual({ skill: "sliders", focus: "slider_speed:fast" });
    expect(approachRates(["AR 9", "AR 9.5"])).toEqual({ skill: "reading", focus: "ar:9-10" });
  });

  it("opens the playlist page with the playlist made again for it, without mods; a plain link drops an old focus", () => {
    expect(practiseUrl({ skill: "speed", focus: "bpm:120-130" })).toBe("/skills?tab=playlist&skill=speed&focus=bpm%3A120-130");
    const saved: SavedPlaylist = { ...NO_PLAYLIST, options: { skill: "aim", allow_hd: true, adjustable_dt: true } };
    const focused = practised(saved, "speed", "bpm:120-130");
    expect(focused.options).toMatchObject({ skill: "speed", focus: "bpm:120-130", allow_hd: false, adjustable_dt: false });
    expect(focused.playlist).toBeNull(); // made again, not the old one
    expect(practised(focused, "aim").options.focus).toBeUndefined();
  });
});
