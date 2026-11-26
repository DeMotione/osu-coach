import { useRef } from "react";

import type { Job } from "../api/client";
import { useModal } from "../lib/dialog";
import { AnalysingArt } from "./AnalysingArt";
import { Progress } from "./ui";

/**
 * Covers the page while a playlist is made (#144), as the analysis does: "Practise this" on an analysis page, Show
 * maps, or the first visit. A playlist without mods takes a few seconds; one with mods follows its search, which can
 * be cancelled. It closes by itself when the playlist is there (or making it failed: the page says why).
 */
export function PlaylistLock({ open, focused = false, job, onCancel }: {
  open: boolean;
  /** it keeps to a weak spot ("Practise this") */
  focused?: boolean;
  /** the search of a playlist with mods */
  job?: Job | null;
  onCancel?: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useModal(ref, open);
  const searching = job?.kind === "playlist" && job.status === "running" ? job : null;
  return (
    <dialog
      ref={ref}
      className="analysis-lock playlist-lock"
      aria-labelledby="playlist-lock-title"
      aria-describedby="playlist-lock-text"
      onCancel={(e) => e.preventDefault() /* Esc: the playlist is still being made */}
    >
      {open && (
        <div className="analysis-lock__body">
          <AnalysingArt />
          <h2 id="playlist-lock-title">Making your playlist</h2>
          <p id="playlist-lock-text" className="analysis-lock__text">
            Hang on a moment: osu! coach is going through the map pool for the maps that fit your level
            {focused ? " and are full of your weak spot" : ""}.{" "}
            {searching ? "With mods every map is worked out with them, which takes a while." : "It takes a few seconds."} This screen
            closes by itself when the playlist is ready.
          </p>
          <Progress
            value={searching?.progress}
            text={searching?.message || "Picking maps…"}
            right={searching?.progress !== null && searching?.progress !== undefined ? `${Math.round(searching.progress * 100)}%` : undefined}
          />
          {searching && onCancel && (
            <button type="button" className="btn" onClick={onCancel}>
              Cancel the search
            </button>
          )}
        </div>
      )}
    </dialog>
  );
}
