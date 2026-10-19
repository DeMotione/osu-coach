import { describe, expect, it } from "vitest";

import { formatLeft, secondsLeft } from "./eta";

describe("secondsLeft", () => {
  it("projects the pace so far to the end", () => {
    // 10% → 30% in 20 s: 10 s per 10%, so 70 s for the last 70%
    expect(secondsLeft({ t: 0, p: 0.1 }, { t: 20_000, p: 0.3 }, 20_000)).toBeCloseTo(70);
  });

  it("counts down between progress updates", () => {
    expect(secondsLeft({ t: 0, p: 0.1 }, { t: 20_000, p: 0.3 }, 30_000)).toBeCloseTo(60);
    expect(secondsLeft({ t: 0, p: 0.1 }, { t: 20_000, p: 0.3 }, 500_000)).toBe(0);
  });

  it("waits until there is something to go on", () => {
    expect(secondsLeft({ t: 0, p: 0.1 }, { t: 2_000, p: 0.3 }, 2_000)).toBeNull(); // too soon
    expect(secondsLeft({ t: 0, p: 0.1 }, { t: 60_000, p: 0.11 }, 60_000)).toBeNull(); // barely moved
    expect(secondsLeft({ t: 0, p: 0.1 }, { t: 60_000, p: 1 }, 60_000)).toBeNull(); // finished
  });
});

describe("formatLeft", () => {
  it("rounds like an estimate", () => {
    expect(formatLeft(10)).toBe("less than a minute left");
    expect(formatLeft(70)).toBe("about a minute left");
    expect(formatLeft(200)).toBe("about 3 minutes left");
    expect(formatLeft(59 * 60)).toBe("about 59 minutes left");
    expect(formatLeft(3600 + 22 * 60)).toBe("about 1 h 20 min left");
    expect(formatLeft(2 * 3600 + 59 * 60)).toBe("about 3 h left");
  });
});
