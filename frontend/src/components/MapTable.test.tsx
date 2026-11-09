import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import type { Schemas } from "../api/client";
import { MapTable } from "./MapTable";

vi.mock("../api/queries", () => ({ useMeta: () => ({ data: null }) }));

it("moves a custom playback rate from the map name to the Mods badge", () => {
  const map: Schemas["MapRow"] = {
    md5: "a".repeat(32), beatmap_id: 1, beatmapset_id: 1,
    artist: "Pyxis", title: "Koise yo Minna, Hai! (TV Size)", version: "Hai!",
    stars: 6.94, mods: "DT", rate: 1.36, bpm: 218, ar: 10.1,
    length_s: 22, why: "Jumps", url: "https://osu.ppy.sh/beatmaps/1",
  };
  render(<MapTable maps={[map]} />);
  const row = within(screen.getByRole("table", { name: "Maps" })).getAllByRole("row")[1];
  const cells = within(row).getAllByRole("cell");
  expect(cells[0]).toHaveTextContent("Pyxis – Koise yo Minna, Hai! (TV Size) [Hai!]");
  expect(cells[0]).not.toHaveTextContent("1.36×");
  expect(within(cells[1]).getByRole("img", { name: "Double Time 1.36×" })).toHaveTextContent("1.36×");
});

it("keeps the table narrow: F(m) opens its calculation, the links are icons, Skill demand is centred", () => {
  const map: Schemas["MapRow"] = {
    md5: "b".repeat(32), beatmap_id: 2, beatmapset_id: 2,
    artist: "LeaF", title: "Wizdomiot", version: "Lunatic",
    stars: 6.31, mods: "", rate: 1, bpm: 200, ar: 9.4, length_s: 148, why: "evenly hard", url: "https://osu.ppy.sh/beatmaps/2",
    skill_demand: 48.4, formula_score: -0.021, breakdown: { star_term: -0.01 },
  };
  render(<MapTable maps={[map]} />);
  const table = screen.getByRole("table", { name: "Maps" });
  const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent);
  expect(headers).not.toContain("Breakdown");
  const cells = within(within(table).getAllByRole("row")[1]).getAllByRole("cell");
  expect(cells[headers.indexOf("Skill demand")]).toHaveClass("center");
  expect(within(cells[headers.indexOf("Link")]).getByRole("link", { name: "Open on the osu! website" })).toHaveAttribute(
    "href", "https://osu.ppy.sh/beatmaps/2",
  );
  expect(cells[headers.indexOf("F(m)")]).toHaveTextContent("-0.0210");
});
