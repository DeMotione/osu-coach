import { describe, expect, it } from "vitest";

import { aimSpot, approachRates, practiseUrl, sliderStretch, streamLengths, streamSpeeds } from "./practise";

describe("practise", () => {
  it("joins the weak stream speeds into ranges", () => {
    expect(streamSpeeds([120, 140, 150, 180, 200])).toEqual({ skill: "speed", focus: "bpm:120-130,140-160,180-190,200-210" });
    expect(streamSpeeds([])).toEqual({ skill: "speed" });
    expect(streamLengths([12, 20])).toEqual({ skill: "stamina", focus: "run:12-20" });
    expect(streamLengths(null)).toEqual({ skill: "stamina" });
  });

  it("reads the weak approach rates, AR 10 and up as AR 10", () => {
    expect(approachRates(["AR 9", "AR 9.5"])).toEqual({ skill: "reading", focus: "ar:9-10" });
    expect(approachRates(["AR 8", "AR 10.5"])).toEqual({ skill: "reading", focus: "ar:8-8.5,10-11" });
    expect(approachRates([])).toEqual({ skill: "reading" });
  });

  it("practises the aim weak spots a map can have", () => {
    expect(aimSpot("quadrant", "top-left")).toEqual({ skill: "aim", focus: "quadrant:top-left" });
    expect(aimSpot("distance", "4+")).toEqual({ skill: "aim", focus: "jump:long" });
    expect(aimSpot("distance", "3-4")).toEqual({ skill: "aim", focus: "jump:long" });
    expect(aimSpot("distance", "2-3")).toEqual({ skill: "aim", focus: "jump:short" });
    expect(aimSpot("distance", "0.5-1")).toEqual({ skill: "flow_aim" });
    expect(aimSpot("distance", "<0.5")).toEqual({ skill: "flow_aim" });
    expect(aimSpot("angle", "sharp (<60°)")).toEqual({ skill: "aim", focus: "angle:sharp" });
    expect(aimSpot("angle", "wide (>120°)")).toEqual({ skill: "aim", focus: "angle:wide" });
    expect(aimSpot("angle", "medium")).toBeNull();
    expect(aimSpot("direction", "up-left")).toBeNull();
  });

  it("practises long, short, fast or slow sliders", () => {
    expect(sliderStretch("length", 7, 8)).toEqual({ skill: "sliders", focus: "slider_length:long" });
    expect(sliderStretch("length", 0, 0)).toEqual({ skill: "sliders", focus: "slider_length:short" });
    expect(sliderStretch("length", 1, 1)).toEqual({ skill: "sliders" });
    expect(sliderStretch("speed", 13, 16)).toEqual({ skill: "sliders", focus: "slider_speed:fast" });
    expect(sliderStretch("speed", 2, 4)).toEqual({ skill: "sliders", focus: "slider_speed:slow" });
  });

  it("links to the playlist", () => {
    expect(practiseUrl({ skill: "aim" })).toBe("/skills?tab=playlist&skill=aim");
    expect(practiseUrl({ skill: "speed", focus: "bpm:120-130" })).toBe("/skills?tab=playlist&skill=speed&focus=bpm%3A120-130");
  });
});
