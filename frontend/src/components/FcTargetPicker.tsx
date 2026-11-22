/** FC a map's target (#127): one of your replays, found by its map's name; a replay file or a beatmap link in a dialog. */
import { useId, useRef, useState } from "react";

import type { Schemas } from "../api/client";
import { replayAt, useUpload } from "../api/queries";
import { useModal } from "../lib/dialog";
import { localTime, pct } from "../lib/format";
import { goalMods, modsText } from "../lib/playGoals";
import { IconX } from "./icons";
import { useReplays } from "../lib/replaySearch";
import { ReplayPicker } from "./ReplayPicker";
import { Alert, Dropzone, Field } from "./ui";

type Request = Schemas["PlayGoalRequest"];
type Replay = Schemas["CheckReplay"];

/** The replay as the target, with its mods and speed when they are a configuration goals know. */
const replayTarget = (r: Replay): Partial<Request> => {
  const found = goalMods(r.mods, r.rate);
  return { replay_path: r.path, beatmap: null, ...(found ? { mods: found.mods, rate: found.rate } : {}) };
};

export function FcTargetPicker({ request, update }: { request: Request; update: (patch: Partial<Request>) => void }) {
  const [other, setOther] = useState(false);
  // the chosen replay is always in the answer (a dropped file too), so the target line can name its map
  const replays = useReplays(request.replay_path ?? null);
  const chosen = replays.all.find((r) => r.path === request.replay_path);
  return (
    <div className="stack">
      <ReplayPicker replays={replays} label="Find the map you want to FC" selected={request.replay_path ?? null} analysableOnly
        onPick={(r) => update(r ? replayTarget(r) : { replay_path: null })} otherwise="use a replay file or a beatmap link"
        aside={<button type="button" className="btn" onClick={() => setOther(true)}>Replay file or beatmap link…</button>} />
      <p className="fc-target">
        {request.replay_path ? (
          <span>Target: <strong>{chosen?.map ?? request.replay_path.split(/[\\/]/).pop()}</strong>
            {chosen && <> {modsText(chosen.mods, chosen.rate)}{chosen.accuracy != null && `, ${pct(chosen.accuracy, 2)}`}, {localTime(chosen.played_at)}</>}</span>
        ) : request.beatmap ? (
          <span>Target: <strong>{request.beatmap}</strong> (beatmap link)</span>
        ) : (
          <span className="muted">No target yet: pick one of your replays, or use a replay file or a beatmap link.</span>
        )}
        {(request.replay_path || request.beatmap) && (
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => update({ replay_path: null, beatmap: null })}>Clear</button>
        )}
      </p>
      {other && (
        <OtherTargetDialog beatmap={request.beatmap ?? ""} onClose={() => setOther(false)}
          onReplay={(r) => update(replayTarget(r))} onBeatmap={(beatmap) => update({ beatmap, replay_path: null })} />
      )}
    </div>
  );
}

/** A replay file (dropped or chosen) or a beatmap link: for a map you have no replay of here. */
function OtherTargetDialog({ beatmap, onReplay, onBeatmap, onClose }: {
  beatmap: string;
  onReplay: (replay: Replay) => void;
  onBeatmap: (link: string) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  const [link, setLink] = useState(beatmap);
  const { upload, error: uploadError } = useUpload();
  const [error, setError] = useState<string | null>(null);
  const [reading, setReading] = useState(false);
  useModal(ref);

  const takeFile = async (files: File[]) => {
    setError(null);
    setReading(true);
    try {
      const [uploaded] = (await upload(files)) ?? [];
      if (!uploaded) return;
      const replay = await replayAt(uploaded.path);
      if (!replay) setError("That file isn't a replay osu! coach can read.");
      else if (!replay.analysable) setError(`This replay can't be used: ${replay.reason ?? "it can't be analysed"}.`);
      else {
        onReplay(replay);
        onClose();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setReading(false);
    }
  };
  const chooseLink = () => {
    onBeatmap(link.trim());
    onClose();
  };

  return (
    <dialog ref={ref} className="goal-dialog" aria-labelledby={`${id}-title`} onClose={onClose}>
      <div className="goal-dialog__head">
        <h2 id={`${id}-title`} className="card__title">Replay file or beatmap link</h2>
        <button type="button" className="btn btn--ghost btn--sm" aria-label="Close" onClick={onClose}>
          <IconX />
        </button>
      </div>
      <div className="goal-dialog__body">
        <section className="stack">
          <h3 className="section__title">A replay file</h3>
          <Dropzone accept=".osr" multiple={false} title={reading ? "Reading the replay…" : "Drop your replay, or click to choose it"}
            help="Export an .osr from your results screen." onFiles={(files) => void takeFile(files)} />
        </section>
        <section className="stack">
          <h3 className="section__title">A beatmap link</h3>
          <form className="controls" onSubmit={(e) => {
            e.preventDefault();
            if (link.trim()) chooseLink();
          }}>
            <Field label="Beatmap link">
              <input className="input" placeholder="https://osu.ppy.sh/beatmapsets/123#osu/456" value={link}
                onChange={(e) => setLink(e.target.value)} />
            </Field>
            <button type="submit" className="btn btn--primary" disabled={!link.trim()}>Use this beatmap</button>
          </form>
          <p className="small muted">On osu.ppy.sh open the specific difficulty (not the whole set) and copy the address.</p>
        </section>
        {(error ?? uploadError) && <Alert tone="bad">{error ?? uploadError}</Alert>}
      </div>
      <div className="goal-dialog__foot">
        <button type="button" className="btn btn--ghost" onClick={onClose}>Cancel</button>
      </div>
    </dialog>
  );
}
