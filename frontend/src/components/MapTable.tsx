import { useState } from "react";

import type { Schemas } from "../api/client";
import { clock, fmt, mapName } from "../lib/format";
import { DataTable, type Column } from "./DataTable";
import { EmptyState } from "./states";

type MapRow = Schemas["MapRow"];

const COLUMNS: Column<MapRow>[] = [
  { key: "map", header: "Map", cell: mapName, strong: true, wrap: true },
  { key: "stars", header: "Difficulty", cell: (m) => fmt(m.stars, 2, " ★"), value: (m) => m.stars, align: "right",
    title: "Star rating (no mod)." },
  { key: "bpm", header: "BPM", cell: (m) => fmt(m.bpm, 0), value: (m) => m.bpm, align: "right" },
  { key: "ar", header: "AR", cell: (m) => fmt(m.ar, 1), value: (m) => m.ar, align: "right" },
  { key: "length", header: "Length", cell: (m) => clock(m.length_s), value: (m) => m.length_s, align: "right" },
  { key: "why", header: "Why this map", cell: (m) => m.why, wrap: true, title: "The patterns it has for the skill." },
  { key: "demand", header: "Skill demand", cell: (m) => fmt(m.skill_demand, 1), value: (m) => m.skill_demand, align: "right",
    title: "Experimental 0–100 demand projection for the target skill." },
  { key: "score", header: "F(m)", cell: (m) => fmt(m.formula_score, 4), value: (m) => m.formula_score, align: "right",
    title: "Goal-conditioned ranking score; higher is better within this goal." },
  { key: "breakdown", header: "Breakdown", value: () => null, cell: (m) => m.breakdown ? (
    <details><summary>Calculation</summary><pre style={{ maxWidth: 360, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(m.breakdown, null, 2)}</pre></details>
  ) : "–" },
  {
    key: "link",
    header: "Link",
    cell: (m) =>
      m.url ? (
        <a href={m.url} target="_blank" rel="noreferrer noopener" onClick={(e) => e.stopPropagation()}>
          open ↗
        </a>
      ) : (
        "–"
      ),
    value: () => null,
  },
];

/** For narrow cards: preserve the compact map columns and add formula details. */
const COMPACT = COLUMNS.filter((c) => ["map", "stars", "bpm", "length", "demand", "score", "breakdown", "link"].includes(c.key));

/** Maps with the same columns everywhere (``compact``: fewer, for half-width cards); ``onHide`` adds a button to
 * never suggest a map again. */
export function MapTable({ maps, maxHeight, onHide, compact = false }: {
  maps: MapRow[];
  maxHeight?: number;
  onHide?: (m: MapRow) => void;
  compact?: boolean;
}) {
  const [page, setPage] = useState(1);
  const pages = Math.max(1, Math.ceil(maps.length / 5));
  const shownPage = Math.min(page, pages);
  const base = compact ? COMPACT : COLUMNS;
  const columns: Column<MapRow>[] = onHide
    ? [
        ...base,
        {
          key: "hide",
          header: "",
          value: () => null,
          cell: (m) => (
            <button type="button" className="btn btn--ghost btn--sm" title="Never suggest this map again" onClick={() => onHide(m)}>
              Hide
            </button>
          ),
        },
      ]
    : base;
  return (
    <div className={compact ? "map-table map-table--compact" : "map-table"}>
    <DataTable
      label="Maps"
      rows={maps.slice((shownPage - 1) * 5, shownPage * 5)}
      columns={columns}
      rowKey={(m) => m.md5}
      maxHeight={maxHeight}
      empty={<EmptyState title="No maps found for this." />}
    />
    {maps.length > 5 && <div className="controls" style={{ marginTop: 12, alignItems: "center" }}>
      <span className="small muted">Maps {(shownPage - 1) * 5 + 1}–{Math.min(shownPage * 5, maps.length)} of {maps.length}</span>
      <button type="button" className="btn btn--sm" disabled={shownPage === 1} onClick={() => setPage(shownPage - 1)}>Previous</button>
      <label className="small">Page <select className="select" value={shownPage} onChange={(e) => setPage(Number(e.target.value))}>
        {Array.from({ length: pages }, (_, i) => <option key={i + 1} value={i + 1}>{i + 1} of {pages}</option>)}
      </select></label>
      <button type="button" className="btn btn--sm" disabled={shownPage === pages} onClick={() => setPage(shownPage + 1)}>Next</button>
    </div>}
    </div>
  );
}
