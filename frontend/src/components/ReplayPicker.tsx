/** Your replays, found by their map's name: a search box and a table to pick one from (Detailed Map Analysis, FC a
 * map). The list follows each key at once; every replay (not only the newest) is searched once typing stops. */
import type { ReactNode } from "react";

import { isBusy, type Schemas } from "../api/client";
import { localTime, pct } from "../lib/format";
import { matchesMap, modsText } from "../lib/playGoals";
import type { Replays } from "../lib/replaySearch";
import { DataTable, type Column } from "./DataTable";
import { EmptyState } from "./states";
import { Alert, Badge, Field } from "./ui";

type Replay = Schemas["CheckReplay"];

/** "2026-11-18" over "01:23": a date and its time on two lines, so the column stays narrow. */
function Played({ iso }: { iso: string | null | undefined }) {
  const [day, time] = localTime(iso).split(" ");
  return (
    <span className="replay-picker__played">
      {day}
      {time && <span className="small muted">{time}</span>}
    </span>
  );
}

// every column in view in half a page: the player under the map's name, the time under the date (fixed widths, see
// .replay-picker in components.css)
const COLUMNS: Column<Replay>[] = [
  { key: "map", header: "Map", strong: true, wrap: true, value: (r) => r.map,
    cell: (r) => (
      <span className="replay-picker__map">
        {r.analysable ? r.map : <>{r.map} <span className="small muted">({r.reason})</span></>}
        {r.player && <span className="small muted">{r.player}</span>}
      </span>
    ) },
  { key: "mods", header: "Mods", cell: (r) => <Badge tone="info">{modsText(r.mods, r.rate)}</Badge>, value: (r) => r.mods },
  { key: "acc", header: "Accuracy", cell: (r) => pct(r.accuracy, 2), value: (r) => r.accuracy, align: "right" },
  { key: "played", header: "Played", cell: (r) => <Played iso={r.played_at} />, value: (r) => r.played_at, align: "right" },
];

export function ReplayPicker({ replays, label, selected, onPick, aside, analysableOnly = false, otherwise }: {
  replays: Replays;
  label: string;
  selected: string | null;
  onPick: (replay: Replay | null) => void;
  /** next to the search box */
  aside?: ReactNode;
  /** leave out the replays that can't be analysed */
  analysableOnly?: boolean;
  /** what else to do when nothing is found, e.g. "drop a replay file above" */
  otherwise: string;
}) {
  const { search, setSearch, list, all } = replays;
  const rows = all.filter((r) => (r.analysable || !analysableOnly) && matchesMap(r.map, search));
  return (
    <div className="stack">
      <div className="controls">
        <Field label={label}>
          <input className="input" type="search" placeholder="Map name, artist or difficulty" value={search}
            onChange={(e) => setSearch(e.target.value)} />
        </Field>
        {aside}
      </div>
      {list.error && (isBusy(list.error)
        ? <p className="small muted" role="status">{list.error.message} The list updates by itself then.</p>
        : <Alert tone="bad">{list.error.message}</Alert>)}
      <div className="replay-picker">
        <DataTable label="Your replays" rows={rows} columns={COLUMNS} rowKey={(r) => r.path} maxHeight={320} colgroup
          selected={selected} onSelect={(r) => onPick(r)}
          empty={search.trim() ? (
            <EmptyState title="No replay of a map like that">Try fewer or other words, or {otherwise}.</EmptyState>
          ) : list.isPending || list.error ? null : (
            <EmptyState title="No replays yet">Scan your replays on the Replays page, or {otherwise}.</EmptyState>
          )} />
      </div>
    </div>
  );
}
