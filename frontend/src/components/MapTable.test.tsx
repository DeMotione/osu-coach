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
