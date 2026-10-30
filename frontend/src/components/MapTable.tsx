import { useEffect, useRef, useState } from "react";

import type { Schemas } from "../api/client";
import { useMeta } from "../api/queries";
import { breakdownLines } from "../lib/breakdown";
import { clock, fmt, mapName, NONE } from "../lib/format";
import { DataTable, type Column } from "./DataTable";
import { EmptyState } from "./states";

type MapRow = Schemas["MapRow"];

/** The F(m) terms of a map as a short list behind a "Calculation" toggle. */
function Breakdown({ map }: { map: MapRow }) {
  const meta = useMeta();
  const label = (key: string) => meta.data?.skills.find((s) => s.key === key)?.label ?? key;
  const lines = breakdownLines(map.breakdown, map.stars, map.skill_demand, label);
  if (!lines.length) return NONE;
  return (
    <details className="map-breakdown">
      <summary>Calculation</summary>
      <dl>
        {lines.map((line) => (
          <div key={line.label}>
            <dt>{line.label}</dt>
            <dd>{line.value}</dd>
            <dd className="map-breakdown__detail">{line.detail}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

const COLUMNS: Column<MapRow>[] = [
  { key: "map", header: "Map", cell: mapName, strong: true, wrap: true },
  { key: "stars", header: "Difficulty", cell: (m) => fmt(m.stars, 2, " ★"), value: (m) => m.stars, align: "right",
    title: "Star rating (no mod)." },
  { key: "bpm", header: "BPM", cell: (m) => fmt(m.bpm, 0), value: (m) => m.bpm, align: "right" },
  { key: "ar", header: "AR", cell: (m) => fmt(m.ar, 1), value: (m) => m.ar, align: "right" },
  { key: "length", header: "Length", cell: (m) => clock(m.length_s), value: (m) => m.length_s, align: "right" },
  { key: "why", header: "Why this map", cell: (m) => m.why, wrap: true, title: "The patterns it has for the skill." },
  { key: "demand", header: "Skill demand", cell: (m) => fmt(m.skill_demand, 1), value: (m) => m.skill_demand, align: "right",
    title: "How much the map asks of the target skill, 0–100." },
  { key: "score", header: "F(m)", cell: (m) => fmt(m.formula_score, 4), value: (m) => m.formula_score, align: "right",
    title: "Goal-conditioned ranking score; higher is better within this goal." },
  { key: "breakdown", header: "Breakdown", value: () => null, cell: (m) => <Breakdown map={m} />,
    title: "How F(m) adds up: each term is 0 at best and lower the further the map is from what this goal asks." },
  {
    key: "link",
    header: "Link",
    cell: (m) => (m.url ? <a href={m.url} target="_blank" rel="noreferrer noopener">open ↗</a> : "–"),
    value: () => null,
  },
];

/** For narrow cards: preserve the compact map columns and add formula details. */
const COMPACT = COLUMNS.filter((c) => ["map", "stars", "bpm", "length", "demand", "score", "breakdown", "link"].includes(c.key));

type PageItem = number | "left-gap" | "right-gap";

function pageItems(page: number, pages: number): PageItem[] {
  if (pages <= 7) return Array.from({ length: pages }, (_, index) => index + 1);
  if (page <= 3) return [1, 2, 3, "right-gap", pages];
  if (page >= pages - 2) return [1, "left-gap", pages - 2, pages - 1, pages];
  return [1, "left-gap", page - 1, page, page + 1, "right-gap", pages];
}

function MapPagination({ page, pages, total, onPageChange }: {
  page: number;
  pages: number;
  total: number;
  onPageChange: (page: number) => void;
}) {
  const [openGap, setOpenGap] = useState<"left-gap" | "right-gap" | null>(null);
  const [jump, setJump] = useState("");
  const [invalid, setInvalid] = useState(false);
  const jumpInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (openGap) jumpInput.current?.focus();
  }, [openGap]);

  const choosePage = (next: number) => {
    onPageChange(next);
    setOpenGap(null);
    setJump("");
    setInvalid(false);
  };

  return (
    <nav className="map-pagination" aria-label="Map pages">
      <span className="map-pagination__count">Showing {(page - 1) * 5 + 1}–{Math.min(page * 5, total)} of {total} maps</span>
      <div className="map-pagination__links">
        <button type="button" className="map-pagination__step" disabled={page === 1} onClick={() => choosePage(page - 1)}>‹ Previous</button>
        {pageItems(page, pages).map((item) => typeof item === "number" ? (
          <button key={item} type="button" className={`map-pagination__page${item === page ? " is-current" : ""}`}
            aria-label={`Page ${item}`} aria-current={item === page ? "page" : undefined} onClick={() => choosePage(item)}>{item}</button>
        ) : openGap === item ? (
          <input key={item} ref={jumpInput} className="map-pagination__jump" type="text" inputMode="numeric"
            aria-label={`Page number, 1 to ${pages}; press Enter to go`} aria-invalid={invalid} value={jump}
            onChange={(event) => { setJump(event.target.value.replace(/\D/g, "")); setInvalid(false); }}
            onKeyDown={(event) => {
              if (event.key === "Escape") { setOpenGap(null); setJump(""); setInvalid(false); }
              if (event.key === "Enter") {
                const next = Number(jump);
                if (jump && Number.isInteger(next) && next >= 1 && next <= pages) choosePage(next);
                else setInvalid(true);
              }
            }}
          />
        ) : (
          <button key={item} type="button" className="map-pagination__gap" aria-label="Enter a page number"
            title="Enter a page number" onClick={() => { setOpenGap(item); setJump(""); setInvalid(false); }}>…</button>
        ))}
        <button type="button" className="map-pagination__step" disabled={page === pages} onClick={() => choosePage(page + 1)}>Next ›</button>
      </div>
    </nav>
  );
}

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
    {maps.length > 5 && <MapPagination page={shownPage} pages={pages} total={maps.length} onPageChange={setPage} />}
    </div>
  );
}
