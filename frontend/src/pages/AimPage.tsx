import { useCallback, useState } from "react";
import { Link } from "react-router";

import type { Schemas } from "../api/client";
import { useAim, useClicks } from "../api/queries";
import { directionsChart, distanceChart } from "../charts/aim";
import { Chart } from "../charts/Chart";
import type { ChartTheme } from "../charts/palette";
import { ClicksView } from "../components/Clicks";
import { DataTable } from "../components/DataTable";
import { PlayfieldGrid, QuadrantGrid } from "../components/Heat";
import { EmptyState, QueryView } from "../components/states";
import { Alert, Card, Page, Row, Segmented, Stat, Tiles } from "../components/ui";
import { fmt, int, pct, signed } from "../lib/format";

export default function AimPage() {
  const q = useAim();
  return (
    <Page title="Aim">
      <QueryView query={q}>{(aim) => <AimBody aim={aim} />}</QueryView>
    </Page>
  );
}

function AimBody({ aim }: { aim: Schemas["AimPage"] }) {
  const k = aim.kpis;
  const wq = aim.worst_quadrant;
  const dirs = useCallback((t: ChartTheme) => directionsChart(aim.directions, t), [aim.directions]);
  const dist = useCallback((t: ChartTheme) => distanceChart(aim.distances, t), [aim.distances]);
  return (
    <>
      <Tiles n={3}>
        <Stat label="Jump miss rate" value={pct(k.jump_miss_rate)} />
        <Stat label="Near misses" value={pct(k.near_miss_share, 0)} hint="Aim misses that landed within 1.4 radii — just outside the circle." />
        <Stat label="Jump distance error" value={signed(k.jump_along_pct, 1, "%")} hint="Median over/undershoot along the jump direction, as % of the jump length." />
      </Tiles>
      {wq &&
        (wq.significant ? (
          <Alert tone="warn">
            Weakest quadrant: <strong>{wq.quadrant}</strong> — {pct(wq.miss_rate)} misses vs {pct(wq.rest_miss_rate)} elsewhere (
            {fmt(wq.relative_risk, 1)}×). See <Link to="/tips">Tips</Link> for how to fix it.
          </Alert>
        ) : (
          <Alert tone="info">
            Weakest quadrant: <strong>{wq.quadrant}</strong> — {pct(wq.miss_rate)} misses vs {pct(wq.rest_miss_rate)} elsewhere (
            {fmt(wq.relative_risk, 1)}×). The difference is still within noise.
          </Alert>
        ))}
      <Row>
        <Card title="Miss rate by screen quadrant" hint="The playfield cut into four. Each cell: share of the notes there you missed, and misses / notes. Pinker = more misses.">
          <QuadrantGrid cells={aim.quadrants} />
        </Card>
        <Card title="Where on the playfield you miss" hint="A finer grid of the playfield as you see it: the pinker a cell, the more of its notes you missed. Empty cells: too few notes there.">
          <PlayfieldGrid grid={aim.grid} />
        </Card>
      </Row>
      <Row>
        <ClicksCard />
        <Card
          title="Miss rate by jump direction"
          hint="Each wedge is a direction the cursor moves in to reach the note (jumps of 1+ circle). The longer the wedge, the more of those jumps you missed."
        >
          <Chart build={dirs} height={420} label="Miss rate by jump direction" />
        </Card>
      </Row>
      <Row>
        <Card
          title="By jump distance"
          hint="Bars: miss rate by how far the note is from the previous one (circle diameters). Line: how far past (+) or short of (−) the note you click, in circle radii."
        >
          <Chart build={dist} height={340} label="Miss rate and over/undershoot by jump distance" />
        </Card>
        <AnglesCard angles={aim.angles} />
      </Row>
    </>
  );
}

function ClicksCard() {
  const [view, setView] = useState<"screen" | "movement">("screen");
  const q = useClicks(view);
  return (
    <Card
      title="Where your clicks land"
      hint="The click that hit each note and the closest click of each aim miss, in circle radii from the note's centre."
      actions={
        <Segmented
          label="View"
          value={view}
          onChange={setView}
          options={[
            { value: "screen", label: "On screen" },
            { value: "movement", label: "Along the jump" },
          ]}
        />
      }
    >
      {q.data ? <ClicksView clicks={q.data} /> : <div className="skeleton grow" style={{ minHeight: 360 }} />}
    </Card>
  );
}

function AnglesCard({ angles }: { angles: Schemas["AngleRow"][] }) {
  return (
    <Card
      title="By angle between jumps"
      hint="Sharp = back-and-forth jumps, wide = jumps that keep going in one direction. Notes are weighted by difficulty."
    >
      {angles.length ? (
        <DataTable
          label="Miss rate by angle between jumps"
          rows={angles}
          rowKey={(r) => r.bin}
          columns={[
            { key: "bin", header: "Angle between jumps", cell: (r) => r.bin },
            { key: "n", header: "Notes", cell: (r) => int(r.objects), value: (r) => r.objects, align: "right" },
            { key: "rate", header: "Miss rate", cell: (r) => pct(r.miss_rate), value: (r) => r.miss_rate, align: "right" },
          ]}
        />
      ) : (
        <EmptyState title="Not enough jumps yet" />
      )}
    </Card>
  );
}
