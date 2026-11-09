import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import type { Schemas } from "../api/client";
import MapsPage from "./MapsPage";

/** Suggestions for one weak skill: 12 maps, so it has a second group of five; κ shows in the map names. */
function suggestions(options: { kappa?: number }): Schemas["Suggestions"] {
  const maps = Array.from({ length: 12 }, (_, i) => ({
    md5: `speed-${options.kappa ?? 0.5}-${i}`.padEnd(32, "0"), beatmap_id: i + 1, beatmapset_id: i + 1,
    artist: "Artist", title: `Stream map ${i + 1} at κ ${options.kappa ?? 0.5}`, version: "Hard",
    stars: 6, mods: "", rate: 1, bpm: 200, ar: 9, length_s: 120, why: "Tapping speed", url: `https://osu.ppy.sh/beatmaps/${i + 1}`,
  }));
  return {
    has_profile: true, hidden: 0, unmeasured_skills: [], collection_name: "osu-coach: weak skills", preferred_client: "lazer",
    sections: [{ skill: "speed", title: "Tapping speed", maps, eligible: maps.length, skill_adjusted_stars: 6.3, target_stars: 6.3, target_demand: 50 }],
  } as unknown as Schemas["Suggestions"];
}

vi.mock("../api/queries", () => ({
  useSuggestions: (options: { kappa?: number }) => ({ data: suggestions(options), isPending: false, error: null }),
  useHideMaps: () => ({ mutate: vi.fn(), isPending: false, isError: false }),
  useMeta: () => ({ data: null }),
}));

vi.mock("../components/ExportPanel", () => ({ ExportPanel: () => null }));

beforeEach(() => sessionStorage.clear());

it("keeps the settings applied and the maps shown when leaving the page and coming back (#107)", () => {
  const page = render(<MapsPage />);
  fireEvent.change(screen.getByRole("spinbutton", { name: /Skill star adjustment/ }), { target: { value: "0.8" } });
  fireEvent.click(screen.getByRole("button", { name: "Show maps" }));
  fireEvent.click(screen.getByRole("button", { name: /Other maps/ }));
  expect(screen.getByText(/showing 6–10 of 12/)).toBeInTheDocument();
  page.unmount();

  render(<MapsPage />);
  expect(screen.getByRole("spinbutton", { name: /Skill star adjustment/ })).toHaveValue(0.8);
  expect(screen.getByRole("table", { name: "Maps" })).toHaveTextContent("Stream map 6 at κ 0.8");
  expect(screen.getByText(/showing 6–10 of 12/)).toBeInTheDocument();
});

it("starts with the best maps again when settings are applied, even the same ones", () => {
  render(<MapsPage />);
  fireEvent.click(screen.getByRole("button", { name: /Other maps/ }));
  expect(screen.getByText(/showing 6–10 of 12/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show maps" }));
  expect(screen.getByText(/showing 1–5 of 12/)).toBeInTheDocument();
});
