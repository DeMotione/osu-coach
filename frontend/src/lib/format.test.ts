import { describe, expect, it } from "vitest";

import { clock, esc, fmt, int, isoDay, localTime, mapName, pct, shortLabel, signed, span, stars } from "./format";

describe("number formats", () => {
  it("shows a dash for missing values", () => {
    for (const f of [fmt, int, pct, signed, stars, clock]) {
      expect(f(null)).toBe("–");
      expect(f(undefined)).toBe("–");
      expect(f(Number.NaN)).toBe("–");
    }
  });

  it("formats numbers, percentages and stars", () => {
    expect(fmt(1234.567, 1)).toBe("1,234.6");
    expect(fmt(3.5, 0, " min")).toBe("4 min");
    expect(int(10347)).toBe("10,347");
    expect(pct(0.9123)).toBe("91.2%");
    expect(pct(0.9123, 0)).toBe("91%");
    expect(stars(7.271)).toBe("7.27★");
  });

  it("signs with a real minus and ± for zero", () => {
    expect(signed(3.456, 1, " ms")).toBe("+3.5 ms");
    expect(signed(-0.4, 1, "%")).toBe("−0.4%");
    expect(signed(0.01, 1)).toBe("±0.0");
  });

  it("formats durations", () => {
    expect(clock(83.9)).toBe("1:23");
    expect(clock(5)).toBe("0:05");
    expect(span(10)).toBe("10 s");
    expect(span(120)).toBe("2 min");
  });
});

describe("dates", () => {
  it("shows UTC times on the local clock", () => {
    const iso = "2026-09-13T20:16:02Z";
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    expect(localTime(iso)).toBe(
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`,
    );
    expect(localTime("not a date")).toBe("–");
  });

  it("counts days on the local calendar", () => {
    expect(isoDay(28, new Date(2026, 9, 13))).toBe("2026-11-10");
    expect(isoDay(-13, new Date(2026, 0, 5))).toBe("2025-12-23");
  });
});

describe("text", () => {
  it("shortens skill labels and names maps", () => {
    expect(shortLabel("Flow aim (spaced streams)")).toBe("Flow aim");
    expect(mapName({ artist: "xi", title: "FREEDOM DiVE", version: "FOUR DIMENSIONS" })).toBe("xi – FREEDOM DiVE [FOUR DIMENSIONS]");
  });

  it("escapes HTML for chart tooltips", () => {
    expect(esc(`<img src=x onerror="a">&'`)).toBe("&lt;img src=x onerror=&quot;a&quot;&gt;&amp;&#39;");
  });
});
