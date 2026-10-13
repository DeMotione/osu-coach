import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DataTable, type Column } from "./DataTable";

type Row = { name: string; score: number | null };
const rows: Row[] = [
  { name: "b", score: 2 },
  { name: "a", score: null },
  { name: "c", score: 1 },
];
const columns: Column<Row>[] = [
  { key: "name", header: "Name", cell: (r) => r.name },
  { key: "score", header: "Score", cell: (r) => (r.score === null ? "–" : String(r.score)), value: (r) => r.score, align: "right" },
];

const names = () =>
  screen
    .getAllByRole("row")
    .slice(1)
    .map((r) => within(r).getAllByRole("cell")[0].textContent);

describe("DataTable", () => {
  it("keeps the given order until a header is clicked, then sorts with missing values last", () => {
    render(<DataTable label="t" rows={rows} columns={columns} rowKey={(r) => r.name} />);
    expect(names()).toEqual(["b", "a", "c"]);
    fireEvent.click(screen.getByRole("button", { name: "Score" }));
    expect(names()).toEqual(["c", "b", "a"]);
    fireEvent.click(screen.getByRole("button", { name: /Score/ }));
    expect(names()).toEqual(["b", "c", "a"]);
    fireEvent.click(screen.getByRole("button", { name: /Score/ }));
    expect(names()).toEqual(["b", "a", "c"]);
  });

  it("selects one row and unselects it on a second click", () => {
    const onSelect = vi.fn();
    const { rerender } = render(<DataTable label="t" rows={rows} columns={columns} rowKey={(r) => r.name} onSelect={onSelect} />);
    fireEvent.click(screen.getByText("c"));
    expect(onSelect).toHaveBeenLastCalledWith(rows[2], "c");
    rerender(<DataTable label="t" rows={rows} columns={columns} rowKey={(r) => r.name} onSelect={onSelect} selected="c" />);
    expect(screen.getByText("c").closest("tr")).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByText("c"));
    expect(onSelect).toHaveBeenLastCalledWith(null, null);
  });

  it("shows the empty state without rows", () => {
    render(<DataTable label="t" rows={[]} columns={columns} rowKey={(r) => r.name} empty={<p>nothing</p>} />);
    expect(screen.getByText("nothing")).toBeInTheDocument();
  });
});
