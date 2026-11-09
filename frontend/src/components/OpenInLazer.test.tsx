import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { OpenInLazer } from "./OpenInLazer";

const meta = vi.hoisted(() => ({ data: { lazer_found: true } as { lazer_found: boolean } | null }));
const post = vi.hoisted(() => vi.fn());

vi.mock("../api/queries", () => ({ useMeta: () => meta }));
vi.mock("../api/client", () => ({
  api: { POST: post },
  unwrap: async (call: Promise<{ data?: unknown; error?: { detail: string } }>) => {
    const res = await call;
    if (res.error) throw new Error(res.error.detail);
    return res.data;
  },
}));

beforeEach(() => {
  meta.data = { lazer_found: true };
  post.mockReset();
});

it("asks osu! coach to open the map in lazer", async () => {
  post.mockResolvedValue({ data: { link: "osu://b/2768184" } });
  render(<OpenInLazer beatmapId={2768184} />);
  fireEvent.click(screen.getByRole("button", { name: "in lazer" }));
  expect(post).toHaveBeenCalledWith("/api/exports/lazer-open", { body: { beatmap_id: 2768184 } });
  await waitFor(() => expect(screen.getByRole("button", { name: "in lazer" })).toBeEnabled());
});

it("shows why it couldn't", async () => {
  post.mockResolvedValue({ error: { detail: "osu!lazer wasn't found on this computer." } });
  render(<OpenInLazer beatmapId={5} />);
  fireEvent.click(screen.getByRole("button", { name: "in lazer" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "in lazer" })).toHaveAttribute(
      "title",
      "osu!lazer wasn't found on this computer.",
    ),
  );
});

it("isn't there without lazer or without a map on the osu! website", () => {
  const { rerender } = render(<OpenInLazer beatmapId={0} />);
  expect(screen.queryByRole("button")).toBeNull();
  meta.data = { lazer_found: false };
  rerender(<OpenInLazer beatmapId={5} />);
  expect(screen.queryByRole("button")).toBeNull();
});
