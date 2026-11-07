import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

import type { Schemas } from "../api/client";
import type { RecommendationOptions } from "../components/RecommendationControls";
import SkillsPage from "./SkillsPage";

const NAMES: Record<string, string> = { flow_aim: "Spaced streams", stamina: "Stamina" };

/** A playlist per skill: one stage of 12 maps, so it has a second group of five. */
function playlist(skill: string): Schemas["Playlist"] {
  const maps = Array.from({ length: 12 }, (_, i) => ({
    md5: `${skill}-${i}`.padEnd(32, "0"), beatmap_id: i + 1, beatmapset_id: i + 1,
    artist: "Artist", title: `${NAMES[skill]} map ${i + 1}`, version: "Hard",
    stars: 6, mods: "", rate: 1, bpm: 200, ar: 9, length_s: 120, why: NAMES[skill], url: `https://osu.ppy.sh/beatmaps/${i + 1}`,
  }));
  return {
    skill, has_profile: true, comfort: 6.27, collection_name: `osu-coach: ${NAMES[skill]} (6.3★)`,
    preferred_client: "lazer", measured_abilities: { flow_aim: 52, stamina: 54.6 }, skill_adjusted_stars: 6.3,
    stages: [{ stage: "Comfort", goal: "", maps, eligible: maps.length, target_stars: 6.3, target_demand: 50 }],
  } as unknown as Schemas["Playlist"];
}

vi.mock("../api/queries", () => ({
  // the default playlist is for the weakest skill
  usePlaylist: (options: RecommendationOptions) => ({ data: playlist(options.skill ?? "flow_aim"), isPending: false, error: null }),
  useGoals: () => ({ isPending: true }),
  useAddPlan: () => ({ mutate: vi.fn() }),
  useRemoveGoal: () => ({ mutate: vi.fn() }),
  useMeta: () => ({ data: null }),
}));

vi.mock("../api/jobs", () => ({
  useJob: () => ({ job: undefined, running: false, error: null, run: vi.fn(), cancel: vi.fn(), dismiss: vi.fn() }),
}));

vi.mock("../components/ExportPanel", () => ({ ExportPanel: () => null }));

beforeEach(() => sessionStorage.clear());

const collection = () => screen.getByText(/^osu-coach: /).textContent;

it("keeps the playlist made for a skill when going to the other tab and back (#107)", () => {
  render(<MemoryRouter initialEntries={["/skills?tab=playlist"]}><SkillsPage /></MemoryRouter>);
  expect(collection()).toBe("osu-coach: Spaced streams (6.3★)");

  fireEvent.change(screen.getByRole("combobox", { name: /Target skill/ }), { target: { value: "stamina" } });
  fireEvent.click(screen.getByRole("button", { name: "Show maps" }));
  fireEvent.click(screen.getByRole("button", { name: /Other maps/ }));
  expect(collection()).toBe("osu-coach: Stamina (6.3★)");
  expect(screen.getByText(/showing 6–10 of 12/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("tab", { name: "Training plan & goals" }));
  expect(screen.queryByText(/^osu-coach: /)).toBeNull();
  fireEvent.click(screen.getByRole("tab", { name: "Playlist for a skill" }));

  expect(collection()).toBe("osu-coach: Stamina (6.3★)");
  expect(screen.getByRole("combobox", { name: /Target skill/ })).toHaveValue("stamina");
  expect(screen.getByText(/showing 6–10 of 12/)).toBeInTheDocument();
  expect(screen.getByRole("table", { name: "Maps" })).toHaveTextContent("Stamina map 6 ");
});

it("keeps it when leaving the page and coming back", () => {
  const page = render(<MemoryRouter initialEntries={["/skills?tab=playlist"]}><SkillsPage /></MemoryRouter>);
  fireEvent.change(screen.getByRole("combobox", { name: /Target skill/ }), { target: { value: "stamina" } });
  fireEvent.click(screen.getByRole("button", { name: "Show maps" }));
  fireEvent.click(screen.getByRole("button", { name: /Other maps/ }));
  page.unmount();

  render(<MemoryRouter initialEntries={["/skills?tab=playlist"]}><SkillsPage /></MemoryRouter>);
  expect(collection()).toBe("osu-coach: Stamina (6.3★)");
  expect(screen.getByText(/showing 6–10 of 12/)).toBeInTheDocument();
});

it("starts with the best maps again when a new playlist is made", () => {
  render(<MemoryRouter initialEntries={["/skills?tab=playlist"]}><SkillsPage /></MemoryRouter>);
  fireEvent.click(screen.getByRole("button", { name: /Other maps/ }));
  expect(screen.getByText(/showing 6–10 of 12/)).toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: /Target skill/ }), { target: { value: "stamina" } });
  fireEvent.click(screen.getByRole("button", { name: "Show maps" }));
  expect(screen.getByText(/showing 1–5 of 12/)).toBeInTheDocument();
});
