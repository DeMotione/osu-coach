import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, it, vi } from "vitest";

import type { Schemas } from "../api/client";
import SettingsPage from "./SettingsPage";

const STABLE = "C:\\Users\\Motion\\AppData\\Local\\osu!";
const LAZER = "C:\\Users\\Motion\\AppData\\Roaming\\osu";
const settings = { rating_engine: "comfort", skipped_installs: [LAZER], download_maps: true } as Schemas["AppSettings"];
const patch = vi.fn();

vi.mock("../api/queries", () => ({
  useSettings: () => ({ data: settings, isPending: false, error: null }),
  useMeta: () => ({ data: { rating_engines: [] } }),
  usePatchSettings: () => ({ mutate: patch, isPending: false, isSuccess: false, isError: false }),
  useInstalls: () => ({
    data: [
      { kind: "stable", root: STABLE, label: `osu!stable – ${STABLE}` },
      { kind: "lazer", root: LAZER, label: `osu!lazer – ${LAZER}` },
    ],
    isPending: false,
  }),
}));

it("chooses the osu! installs a scan reads and whether missing beatmaps are downloaded", () => {
  render(<MemoryRouter><SettingsPage /></MemoryRouter>);
  const stable = screen.getByRole("checkbox", { name: /^osu!stable/ });
  const lazer = screen.getByRole("checkbox", { name: /^osu!lazer/ });
  expect(stable).toBeChecked();
  expect(lazer).not.toBeChecked();

  fireEvent.click(lazer);
  expect(patch).toHaveBeenLastCalledWith({ skipped_installs: [] });
  fireEvent.click(stable);
  expect(patch).toHaveBeenLastCalledWith({ skipped_installs: [LAZER, STABLE] });

  const download = screen.getByRole("checkbox", { name: /^Download beatmaps that aren't on this computer/ });
  expect(download).toBeChecked();
  fireEvent.click(download);
  expect(patch).toHaveBeenLastCalledWith({ download_maps: false });
});
