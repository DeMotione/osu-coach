import { canGoBack, canGoForward, type Rounds } from "../lib/playlist";
import { IconArrowLeft, IconArrowRight, IconRefresh } from "./icons";

/** Which five of a stage's ``total`` maps are on screen, with Back / Forward through the groups shown before and
 * Other maps for a new one. Both arrows stay in place: Back is off at the first group, and Forward at the newest one
 * brings a new group, like Other maps. */
export function StageNav({ rounds, first, count, total, onMove }: {
  rounds: Rounds;
  first: number;
  count: number;
  total: number;
  onMove: (to: "back" | "forward" | "other") => void;
}) {
  const forward = canGoForward(rounds);
  return (
    <div className="stage-nav">
      <span className="small muted">
        showing {first + 1}–{first + count} of {total}
      </span>
      <button type="button" className="btn btn--sm btn--icon" aria-label="Back" title="The maps shown before these"
        disabled={!canGoBack(rounds)} onClick={() => onMove("back")}>
        <IconArrowLeft />
      </button>
      <button type="button" className="btn btn--sm btn--icon" aria-label="Forward"
        title={forward ? "The maps shown after these" : "The next five maps of this stage"} onClick={() => onMove(forward ? "forward" : "other")}>
        <IconArrowRight />
      </button>
      <button type="button" className="btn btn--sm" title="Show the next five maps of this stage" onClick={() => onMove("other")}>
        <IconRefresh /> Other maps
      </button>
    </div>
  );
}
