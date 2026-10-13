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

/** For narrow cards: the map, its difficulty, BPM and length, and the link. */
const COMPACT = COLUMNS.filter((c) => ["map", "stars", "bpm", "length", "link"].includes(c.key));

/** Maps with the same columns everywhere (``compact``: fewer, for half-width cards); ``onHide`` adds a button to
 * never suggest a map again. */
export function MapTable({ maps, maxHeight, onHide, compact = false }: {
  maps: MapRow[];
  maxHeight?: number;
  onHide?: (m: MapRow) => void;
  compact?: boolean;
}) {
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
    <DataTable
      label="Maps"
      rows={maps}
      columns={columns}
      rowKey={(m) => m.md5}
      maxHeight={maxHeight}
      empty={<EmptyState title="No maps found for this." />}
    />
  );
}
