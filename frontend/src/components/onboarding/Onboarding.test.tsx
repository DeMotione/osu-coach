import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Schemas } from "../../api/client";
import { Onboarding } from "./Onboarding";

const SETUP: Schemas["SetupModel"] = {
  device: "tablet",
  handedness: "right",
  client: "stable",
  screen_w_px: 1920,
  screen_h_px: 1080,
  keyboard: "standard",
};

const api = vi.hoisted(() => ({
  save: vi.fn(),
  patch: vi.fn(),
}));

vi.mock("../../api/queries", () => ({
  useSetup: () => ({ data: SETUP }),
  useSaveSetup: () => ({ mutate: api.save, reset: () => undefined, isPending: false, isError: false }),
  usePatchSettings: () => ({ mutate: api.patch }),
  useSettings: () => ({ data: { latest: 500, folders: "", date_range: "all", player: null, onboarded: false } }),
  useInstalls: () => ({ data: [], isPending: false }),
  useAddInstall: () => ({ mutate: vi.fn(), isPending: false, isError: false, isSuccess: false }),
  useAnalysisStatus: () => ({ data: { analysed: 0, player_label: "", profile_replays: null } }),
  useMeta: () => ({ data: undefined }),
  uploadFiles: vi.fn(),
}));

vi.mock("../../api/jobs", () => ({
  useJob: () => ({ job: undefined, running: false, error: null, run: vi.fn(), dismiss: () => undefined }),
}));

function Where() {
  return <span data-testid="where">{useLocation().pathname}</span>;
}

function show(first: boolean, onClose = vi.fn()) {
  render(
    <MemoryRouter initialEntries={["/somewhere"]}>
      <Onboarding first={first} onClose={onClose} />
      <Where />
    </MemoryRouter>,
  );
  return onClose;
}

const heading = (name: string | RegExp) => screen.getByRole("heading", { level: 2, name });
const click = (name: string | RegExp) => fireEvent.click(screen.getByRole("button", { name }));

describe("the setup guide", () => {
  beforeEach(() => {
    sessionStorage.clear();
    api.save.mockReset().mockImplementation((_setup, opts?: { onSuccess?: () => void }) => opts?.onSuccess?.());
    api.patch.mockReset();
  });

  it("goes through every step, saving the setup on the way", () => {
    const onClose = show(true);
    expect(heading("Which osu! do you play?")).toHaveFocus();
    expect(screen.getByText(/osu!stable wasn't found automatically/)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "osu!stable" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "osu!lazer" })).toHaveAccessibleDescription(/new client/);
    fireEvent.click(screen.getByRole("radio", { name: "osu!lazer" }));
    expect(screen.getByText(/osu!lazer wasn't found automatically/)).toBeInTheDocument();
    click(/Continue/);
    expect(api.save).toHaveBeenLastCalledWith(expect.objectContaining({ client: "lazer" }), expect.anything());

    expect(heading("How do you play?")).toBeInTheDocument();
    expect(screen.getByLabelText("Area width (mm)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Mouse" }));
    fireEvent.change(screen.getByLabelText("Mouse DPI"), { target: { value: "1600" } });
    fireEvent.click(screen.getByRole("radio", { name: "SayoDevice" }));
    fireEvent.change(screen.getByLabelText(/^RT Trigger/), { target: { value: "0.15" } });
    expect(screen.queryByLabelText("Area width (mm)")).toBeNull();
    click(/Continue/);
    expect(api.save).toHaveBeenLastCalledWith(
      expect.objectContaining({ client: "lazer", device: "mouse", mouse_dpi: 1600, keyboard: "sayo", sayo_rt_trigger_mm: 0.15, sayo_rt: true }),
      expect.anything(),
    );

    expect(heading("Find your replays")).toBeInTheDocument();
    click("Skip for now");
    expect(heading("Want a quick tour?")).toBeInTheDocument();
    click(/Show me around/);
    for (const group of ["Replays", "Analysis"]) {
      expect(heading(group)).toBeInTheDocument();
      click(/Next/);
    }
    expect(heading("Improve")).toBeInTheDocument();
    expect(screen.getByText("Map Suggestion")).toBeInTheDocument();
    click(/Finish the tour/);

    expect(heading("You're all set!")).toBeInTheDocument();
    expect(screen.getByText("Mouse · 1,600 DPI")).toBeInTheDocument();
    expect(screen.getByText("SayoDevice")).toBeInTheDocument();
    click(/Start using osu! coach/);
    expect(api.patch).toHaveBeenCalledWith({ onboarded: true });
    expect(onClose).toHaveBeenCalled();
    expect(screen.getByTestId("where")).toHaveTextContent("/replays"); // nothing analysed yet
    expect(sessionStorage.length).toBe(0);
  });

  it("goes back through the stepper and skips the tour", () => {
    show(true);
    click(/Continue/);
    click(/Continue/);
    click("Skip for now");
    fireEvent.click(screen.getByTitle("Back to: Playstyle"));
    expect(heading("How do you play?")).toBeInTheDocument();
    click(/Continue/);
    click("Skip for now");
    click("Skip");
    expect(heading("You're all set!")).toBeInTheDocument();
  });

  it("remembers the step over a reload", () => {
    show(true);
    click(/Continue/);
    expect(heading("How do you play?")).toBeInTheDocument();
    document.body.innerHTML = "";
    show(true);
    expect(heading("How do you play?")).toBeInTheDocument();
  });

  it("can be skipped on the first start, and is then not shown again", () => {
    const onClose = show(true);
    click("Skip setup");
    expect(api.patch).toHaveBeenCalledWith({ onboarded: true });
    expect(onClose).toHaveBeenCalled();
    expect(screen.getByTestId("where")).toHaveTextContent("/somewhere");
  });

  it("opened again later, closes without changing anything", () => {
    const onClose = show(false);
    expect(screen.getByRole("dialog", { name: "Setup guide" })).toBeInTheDocument();
    fireEvent.keyDown(heading("Which osu! do you play?"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    click("Close");
    expect(onClose).toHaveBeenCalledTimes(2);
    expect(api.patch).not.toHaveBeenCalled();
  });
});
