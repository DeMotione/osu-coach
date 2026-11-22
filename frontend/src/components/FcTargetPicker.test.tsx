import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, expect, it, vi } from "vitest";

import type { Schemas } from "../api/client";
import { replayAt, uploadFiles, useCheckReplays } from "../api/queries";
import { goalRequest } from "../lib/playGoals";
import { FcTargetPicker } from "./FcTargetPicker";

type Replay = Schemas["CheckReplay"];
type Request = Schemas["PlayGoalRequest"];

const replay = (path: string, map: string, mods: string, accuracy: number, analysable = true): Replay => ({
  path, map, mods, accuracy, analysable, played_at: "2026-11-20T18:00:00Z", player: "Mot1one", beatmap_md5: path,
  reason: analysable ? null : "relax / autopilot / autoplay replays aren't checked",
});

const REPLAYS = [
  replay("a.osr", "VOID – Tech Occultism [Proeza]", "HDDT", 0.9712),
  replay("b.osr", "VOID – Tech Occultism [Proeza]", "NM", 0.9501),
  replay("c.osr", "Roselia – Ringing Bloom [Everyone's voice becomes my voice]", "HD", 0.9822),
  replay("d.osr", "Roselia – Ringing Bloom [Insane]", "RX", 0.99, false),
];

vi.mock("../api/queries", () => ({
  useCheckReplays: vi.fn(() => ({ data: { available: true, replays: REPLAYS, selected: "a.osr" }, isPending: false, error: null })),
  uploadFiles: vi.fn(),
  replayAt: vi.fn(),
}));

afterEach(() => vi.useRealTimers());

/** The picker with the page's request state; ``changes``: every patch it sends. */
function Picker({ changes, start = {} }: { changes: Partial<Request>[]; start?: Partial<Request> }) {
  const [request, setRequest] = useState<Request>({ ...goalRequest("fc"), ...start });
  return <FcTargetPicker request={request} update={(patch) => {
    changes.push(patch);
    setRequest((r) => ({ ...r, ...patch }));
  }} />;
}

const mapCells = () => screen.getAllByRole("row").slice(1).map((row) => row.querySelector("td")?.textContent);

it("finds a map by name in all your replays and picks one of its replays with its mods (#127)", () => {
  vi.useFakeTimers();
  const changes: Partial<Request>[] = [];
  render(<Picker changes={changes} />);
  expect(screen.getByText(/No target yet/)).toBeInTheDocument();
  // a replay that can't be analysed isn't offered
  expect(mapCells()).toHaveLength(3);

  fireEvent.change(screen.getByRole("searchbox", { name: "Find the map you want to FC" }), { target: { value: "proeza tech" } });
  // the list follows each key; all replays are searched once typing stops
  expect(mapCells()).toEqual(["VOID – Tech Occultism [Proeza]", "VOID – Tech Occultism [Proeza]"]);
  act(() => vi.advanceTimersByTime(300));
  expect(vi.mocked(useCheckReplays)).toHaveBeenLastCalledWith(null, false, "proeza tech");

  fireEvent.click(screen.getByRole("cell", { name: "+HDDT" }));
  expect(changes.at(-1)).toEqual({ replay_path: "a.osr", beatmap: null, mods: "HDDT" });
  expect(screen.getByText(/^Target:/)).toHaveTextContent("Target: VOID – Tech Occultism [Proeza] +HDDT, 97.12%");

  fireEvent.click(screen.getByRole("button", { name: "Clear" }));
  expect(changes.at(-1)).toEqual({ replay_path: null, beatmap: null });

  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "camellia" } });
  expect(screen.getByText("No replay of a map like that")).toBeInTheDocument();
});

it("takes a beatmap link from the dialog", () => {
  const changes: Partial<Request>[] = [];
  render(<Picker changes={changes} />);
  fireEvent.click(screen.getByRole("button", { name: "Replay file or beatmap link…" }));
  const dialog = screen.getByRole("dialog", { name: "Replay file or beatmap link" });
  expect(screen.getByRole("button", { name: "Use this beatmap" })).toBeDisabled();
  fireEvent.change(screen.getByRole("textbox", { name: "Beatmap link" }), { target: { value: " https://osu.ppy.sh/beatmapsets/1#osu/2 " } });
  fireEvent.click(screen.getByRole("button", { name: "Use this beatmap" }));
  expect(changes.at(-1)).toEqual({ beatmap: "https://osu.ppy.sh/beatmapsets/1#osu/2", replay_path: null });
  expect(dialog).not.toBeInTheDocument();
  expect(screen.getByText(/^Target:/)).toHaveTextContent("Target: https://osu.ppy.sh/beatmapsets/1#osu/2 (beatmap link)");
});

it("takes a replay file from the dialog with its mods, and says why one can't be used", async () => {
  const changes: Partial<Request>[] = [];
  render(<Picker changes={changes} />);
  const drop = async (name: string, read: Replay) => {
    vi.mocked(uploadFiles).mockResolvedValueOnce([{ id: name, name, path: `uploads/${name}`, kind: "replay" }] as Schemas["UploadedFile"][]);
    vi.mocked(replayAt).mockResolvedValueOnce(read);
    const input = document.querySelector<HTMLInputElement>("dialog input[type=file]")!;
    fireEvent.change(input, { target: { files: [new File(["osr"], name)] } });
    await waitFor(() => expect(replayAt).toHaveBeenCalledWith(`uploads/${name}`));
  };
  fireEvent.click(screen.getByRole("button", { name: "Replay file or beatmap link…" }));
  await drop("relax.osr", replay("uploads/relax.osr", "Some – Map [Hard]", "RX", 0.99, false));
  expect(await screen.findByText(/This replay can't be used: relax/)).toBeInTheDocument();
  expect(changes).toEqual([]);

  await drop("play.osr", replay("uploads/play.osr", "Some – Map [Hard]", "NCHD", 0.97));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(changes.at(-1)).toEqual({ replay_path: "uploads/play.osr", beatmap: null, mods: "HDDT" });
});
