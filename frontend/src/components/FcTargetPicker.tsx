/** FC a map's target (#127): one of your replays, found by its map's name; a replay file or a beatmap link in a dialog. */
import { useEffect, useId, useRef, useState } from "react";

import type { Schemas } from "../api/client";
import { replayAt, uploadFiles, useCheckReplays } from "../api/queries";
import { localTime, pct } from "../lib/format";
import { goalMods, matchesMap } from "../lib/playGoals";
import { DataTable, type Column } from "./DataTable";
import { IconX } from "./icons";
import { EmptyState } from "./states";
import { Alert, Badge, Dropzone, Field } from "./ui";

type Request = Schemas["PlayGoalRequest"];
type Replay = Schemas["CheckReplay"];

const SEARCH_WAIT_MS = 250;

const COLUMNS: Column<Replay>[] = [
  { key: "map", header: "Map", strong: true, wrap: true, cell: (r) => r.map },
  { key: "mods", header: "Mods", cell: (r) => <Badge tone="info">+{r.mods}</Badge>, value: (r) => r.mods },
  { key: "acc", header: "Accuracy", cell: (r) => pct(r.accuracy, 2), value: (r) => r.accuracy, align: "right" },
  { key: "played", header: "Played", cell: (r) => localTime(r.played_at), value: (r) => r.played_at, align: "right" },
  { key: "player", header: "Player", cell: (r) => r.player },
];

/** The replay as the target, with its mods when they are a combination goals know. */
const replayTarget = (r: Replay): Partial<Request> => {
  const mods = goalMods(r.mods);
  return { replay_path: r.path, beatmap: null, ...(mods ? { mods } : {}) };
};

export function FcTargetPicker({ request, update }: { request: Request; update: (patch: Partial<Request>) => void }) {
  const [search, setSearch] = useState("");
  const [searched, setSearched] = useState("");
  const [other, setOther] = useState(false);
  useEffect(() => {
    const wait = setTimeout(() => setSearched(search.trim()), SEARCH_WAIT_MS);
    return () => clearTimeout(wait);
  }, [search]);
  // the chosen replay is always in the answer (a dropped file too), so the target line can name its map
  const replays = useCheckReplays(request.replay_path ?? null, false, searched);
  const all = replays.data?.replays ?? [];
  // filtered here too: the list follows each key at once, the search of all replays follows when typing stops
  const rows = all.filter((r) => r.analysable && matchesMap(r.map, search));
  const chosen = all.find((r) => r.path === request.replay_path);
  return (
    <div className="stack">
      <div className="controls">
        <Field label="Find the map you want to FC">
          <input className="input" type="search" placeholder="Map name, artist or difficulty" value={search}
            onChange={(e) => setSearch(e.target.value)} />
        </Field>
        <button type="button" className="btn" onClick={() => setOther(true)}>Replay file or beatmap link…</button>
      </div>
      {replays.error && <Alert tone="bad">{replays.error.message}</Alert>}
      <div className="fc-replays">
        <DataTable label="Your replays" rows={rows} columns={COLUMNS} rowKey={(r) => r.path} maxHeight={320}
          selected={request.replay_path ?? null}
          onSelect={(r) => update(r ? replayTarget(r) : { replay_path: null })}
          empty={search.trim() ? (
            <EmptyState title="No replay of a map like that">Try fewer or other words, or use a replay file or a beatmap link.</EmptyState>
          ) : replays.isPending ? null : (
            <EmptyState title="No replays yet">Scan your replays on the Replays page, or use a replay file or a beatmap link.</EmptyState>
          )} />
      </div>
      <p className="fc-target">
        {request.replay_path ? (
          <span>Target: <strong>{chosen?.map ?? request.replay_path.split(/[\\/]/).pop()}</strong>
            {chosen && <> +{chosen.mods}{chosen.accuracy != null && `, ${pct(chosen.accuracy, 2)}`}, {localTime(chosen.played_at)}</>}</span>
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
  const [error, setError] = useState<string | null>(null);
  const [reading, setReading] = useState(false);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (typeof d.showModal === "function") d.showModal();
    else d.setAttribute("open", "");
    return () => d.close?.();
  }, []);

  const takeFile = async (files: File[]) => {
    setError(null);
    setReading(true);
    try {
      const [uploaded] = await uploadFiles(files);
      const replay = uploaded ? await replayAt(uploaded.path) : null;
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
        {error && <Alert tone="bad">{error}</Alert>}
      </div>
      <div className="goal-dialog__foot">
        <button type="button" className="btn btn--ghost" onClick={onClose}>Cancel</button>
      </div>
    </dialog>
  );
}
