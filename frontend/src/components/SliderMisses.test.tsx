import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import type { Schemas } from "../api/client";
import type { Option } from "../charts/echarts";
import { chartTheme, type ChartTheme } from "../charts/palette";
import { SliderMissesCard } from "./SliderMisses";

const drawn: { option: Option } = { option: {} };
vi.mock("../charts/Chart", () => ({
  Chart: ({ build }: { build: (t: ChartTheme) => Option }) => {
    drawn.option = build(chartTheme(true));
    return null;
  },
}));

const cell = (length: number, speed: number, n: number, head: number, broke: number) => ({ length, speed, n, head, broke });
const misses: Schemas["SliderMisses"] = {
  length_top: 8,
  speed_top: 16,
  cells: [cell(1, 7, 3000, 20, 5), cell(1, 13, 300, 12, 2), cell(6, 13, 30, 5, 2), cell(2, 0, 4, 0, 0)],
};

const show = (m: Schemas["SliderMisses"] | null) => render(<MemoryRouter><SliderMissesCard misses={m} /></MemoryRouter>);
const labels = () => {
  const base = (drawn.option as { baseOption: { xAxis: { data: string[] }; series: { label: { formatter: (p: unknown) => string } }[] } }).baseOption;
  return Object.fromEntries(base.xAxis.data.map((l, i) => [l, base.series[0].label.formatter({ dataIndex: i })]));
};

describe("SliderMissesCard", () => {
  it("has a button per speed with its misses, and every length from 0\u20131 to 8+", () => {
    show(misses);
    expect(screen.getAllByRole("button")).toHaveLength(18); // All, 0 to 15 and 16+
    expect(screen.getByRole("button", { name: "Speed 13: 21 of 330 sliders missed" })).toHaveTextContent("1321");
    expect(screen.getByRole("button", { name: /^Speed 9:/ })).toBeDisabled(); // no such sliders
    expect(Object.keys(labels())).toEqual(["0\u20131", "1\u20132", "2\u20133", "3\u20134", "4\u20135", "5\u20136", "6\u20137", "7\u20138", "8+"]);
    expect(labels()["1\u20132"]).toBe("1.2%\n39/3300");
    expect(screen.getByRole("status")).toHaveTextContent("Sliders at speed 13: 21 of 330 missed (6.4%)");
  });

  it("shows the lengths of the speeds pressed, several together, and all again without any", () => {
    show(misses);
    fireEvent.click(screen.getByRole("button", { name: /^Speed 13:/ }));
    expect(labels()["1\u20132"]).toBe("4.7%\n14/300");
    expect(screen.getByRole("status")).toHaveTextContent("At speed 13: 21 of 330 missed");
    fireEvent.click(screen.getByRole("button", { name: /^Speed 7:/ }));
    expect(labels()["1\u20132"]).toBe("1.2%\n39/3300");
    expect(screen.getByRole("status")).toHaveTextContent("At speeds 7 and 13");
    fireEvent.click(screen.getByRole("button", { name: /^Speed 13:/ }));
    fireEvent.click(screen.getByRole("button", { name: /^Speed 7:/ }));
    expect(screen.getAllByRole("button")[0]).toHaveAttribute("aria-pressed", "true"); // All
  });

  it("says when a speed has too few sliders, and when there are too few at all", () => {
    const { unmount } = show(misses);
    fireEvent.click(screen.getByRole("button", { name: /^Speed 0:/ }));
    expect(screen.getByRole("status")).toHaveTextContent("0 of 4 missed (0.0%) \u2014 too few sliders to tell.");
    unmount();
    show(null);
    expect(screen.getByText("Needs 100+ sliders.")).toBeInTheDocument();
  });
});
