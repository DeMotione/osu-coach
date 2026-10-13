import type { Schemas } from "../api/client";
import { chartTheme, heat, heatText } from "../charts/palette";
import { useTheme } from "../lib/theme";

/** The playfield cut into four: miss rate and misses / notes per quadrant; the pinker, the more misses. */
export function QuadrantGrid({ cells }: { cells: Schemas["QuadrantCell"][] }) {
  const { dark } = useTheme();
  const t = chartTheme(dark);
  const max = Math.max(...cells.map((c) => c.miss_rate ?? 0), 1e-9);
  return (
    <div className="quadrants" role="table" aria-label="Miss rate by screen quadrant">
      {cells.map((c) => (
        <div
          key={c.quadrant}
          className="quadrant"
          role="cell"
          style={{ background: heat((c.miss_rate ?? 0) / max, t), color: heatText((c.miss_rate ?? 0) / max, t) }}
        >
          <span className="quadrant__rate">{c.miss_rate === null ? "–" : `${(c.miss_rate * 100).toFixed(1)}%`}</span>
          <span className="quadrant__name">{c.quadrant.replace("-", " ")}</span>
          <span className="quadrant__n">
            {Math.round(c.misses)} / {Math.round(c.objects)} notes
          </span>
        </div>
      ))}
    </div>
  );
}

/** A finer grid of the playfield as the player sees it: miss rate per cell (empty = too few notes). */
export function PlayfieldGrid({ grid }: { grid: Schemas["PlayfieldGrid"] }) {
  const { dark } = useTheme();
  const t = chartTheme(dark);
  const values = grid.rate.flat().filter((v): v is number => v !== null);
  const max = Math.max(...values, 1e-9);
  return (
    <div className="playfield" role="table" aria-label="Miss rate on the playfield">
      {grid.rate.map((row, r) =>
        row.map((v, c) => (
          <div
            key={`${r}-${c}`}
            className="playfield__cell"
            role="cell"
            title={v === null ? "too few notes here" : `miss rate ${v.toFixed(1)}%`}
            style={{ background: v === null ? "transparent" : heat(v / max, t), color: v === null ? undefined : heatText(v / max, t) }}
          >
            {v !== null && <span>{v.toFixed(0)}%</span>}
          </div>
        )),
      )}
      <span className="playfield__axis playfield__axis--v" aria-hidden="true" />
      <span className="playfield__axis playfield__axis--h" aria-hidden="true" />
    </div>
  );
}
