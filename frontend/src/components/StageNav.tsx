import { canGoBack, canGoForward, type Rounds } from "../lib/playlist";
import { IconArrowLeft, IconArrowRight, IconRefresh } from "./icons";

/** Which five of a stage's ``total`` maps are on screen, with Back / Forward through the groups shown before and
 * Other maps for a new one; Forward only shows behind the newest group, Back only when there is one before. */
export function StageNav({ rounds, first, count, total, onMove }: {
  rounds: Rounds;
  first: number;
  count: number;
  total: number;
  onMove: (to: "back" | "forward" | "other") => void;
}) {
  return (
    <div className="stage-nav">
      <span className="small muted">
        showing {first + 1}–{first + count} of {total}
      </span>
      {canGoBack(rounds) && (
        <button type="button" className="btn btn--sm btn--icon" aria-label="Back" title="The maps shown before these" onClick={() => onMove("back")}>
          <IconArrowLeft />
        </button>
      )}
      {canGoForward(rounds) && (
        <button type="button" className="btn btn--sm btn--icon" aria-label="Forward" title="The maps shown after these" onClick={() => onMove("forward")}>
          <IconArrowRight />
        </button>
      )}
      <button type="button" className="btn btn--sm" title="Show the next five maps of this stage" onClick={() => onMove("other")}>
        <IconRefresh /> Other maps
      </button>
    </div>
  );
}
