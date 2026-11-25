import { share, type Judged } from "../lib/verdict";

/** Under a chart of judged groups: what its colours and its dashed line are. */
export function ChartNote({ groups, unit = "notes" }: { groups: Judged[]; unit?: string }) {
  const average = groups.find((g) => g.usual !== null)?.usual ?? null;
  const few = groups.some((g) => g.standing === "few" && g.rate !== null);
  return (
    <p className="chart-note">
      <span className="chart-note__key chart-note__key--line" /> your average miss rate{average !== null ? ` (${share(average)})` : ""}
      <span className="chart-note__key chart-note__key--bad" /> clearly worse
      <span className="chart-note__key chart-note__key--good" /> clearly better
      {few && <> · ? = too few {unit} to tell</>}
    </p>
  );
}
