import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Job } from "../api/client";
import { PlaylistLock } from "./PlaylistLock";

const search = { id: "j1", kind: "playlist", status: "running", progress: 0.4, message: "Searching map configurations", result: null } as unknown as Job;

describe("PlaylistLock", () => {
  it("covers the page while a playlist is made", () => {
    render(<PlaylistLock open focused />);
    expect(screen.getByRole("dialog", { name: "Making your playlist" })).toBeInTheDocument();
    expect(screen.getByText(/full of your weak spot/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull(); // a few seconds: nothing to cancel
  });

  it("follows a search with mods, which can be cancelled", () => {
    const cancel = vi.fn();
    render(<PlaylistLock open job={search} onCancel={cancel} />);
    expect(screen.getByText("40%")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel the search" }));
    expect(cancel).toHaveBeenCalled();
  });

  it("is gone once the playlist is there", () => {
    render(<PlaylistLock open={false} />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
