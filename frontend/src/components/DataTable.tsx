import { useMemo, useState, type ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: ReactNode;
  /** The cell; ``value`` (for sorting) defaults to what ``cell`` returns when it is a string or number. */
  cell: (row: T) => ReactNode;
  value?: (row: T) => string | number | null | undefined;
  align?: "left" | "right";
  wrap?: boolean;
  strong?: boolean;
  title?: string;
}

interface Props<T> {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T, index: number) => string;
  selected?: string | null;
  onSelect?: (row: T | null, key: string | null) => void;
  maxHeight?: number;
  fill?: boolean;
  empty?: ReactNode;
  label: string;
}

/** A sortable table with a sticky header that scrolls inside its card; optionally one row can be selected. */
export function DataTable<T>({ rows, columns, rowKey, selected, onSelect, maxHeight, fill, empty, label }: Props<T>) {
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);
  const sorted = useMemo(() => {
    if (!sort) return rows.map((r, i) => [r, i] as const);
    const col = columns.find((c) => c.key === sort.key);
    const get = col?.value ?? ((r: T) => {
      const v = col?.cell(r);
      return typeof v === "string" || typeof v === "number" ? v : null;
    });
    return rows
      .map((r, i) => [r, i] as const)
      .sort(([a], [b]) => {
        const va = get(a);
        const vb = get(b);
        if (va === vb) return 0;
        if (va === null || va === undefined) return 1;            // missing values last, either direction
        if (vb === null || vb === undefined) return -1;
        return (va < vb ? -1 : 1) * sort.dir;
      });
  }, [rows, columns, sort]);

  if (!rows.length && empty) return <>{empty}</>;
  const style = maxHeight ? { ["--table-max" as string]: `${maxHeight}px` } : undefined;
  return (
    <div className={fill ? "table-wrap table-wrap--fill" : "table-wrap"} style={style}>
      <table className="table" aria-label={label}>
        <thead>
          <tr>
            {columns.map((c) => {
              const active = sort?.key === c.key;
              return (
                <th
                  key={c.key}
                  className={c.align === "right" ? "num" : undefined}
                  title={c.title}
                  aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : undefined}
                >
                  <button
                    type="button"
                    onClick={() => setSort(active ? (sort.dir === 1 ? { key: c.key, dir: -1 } : null) : { key: c.key, dir: 1 })}
                  >
                    {c.header}
                    {active ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map(([r, i]) => {
            const k = rowKey(r, i);
            const isSel = selected === k;
            return (
              <tr
                key={k}
                className={[onSelect ? "selectable" : "", isSel ? "selected" : ""].join(" ").trim() || undefined}
                onClick={onSelect ? () => onSelect(isSel ? null : r, isSel ? null : k) : undefined}
                aria-selected={onSelect ? isSel : undefined}
              >
                {columns.map((c) => (
                  <td
                    key={c.key}
                    className={[c.align === "right" ? "num" : "", c.wrap ? "wrap" : "", c.strong ? "strong" : ""]
                      .join(" ")
                      .trim() || undefined}
                  >
                    {c.cell(r)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
