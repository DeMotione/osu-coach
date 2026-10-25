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
      <Tiles n={4}>
        <Stat
          label="Aim misses"
          value={pct(k.aim_miss_share, 0)}
          hint={`Share of your misses where you tapped in time but outside the circle, on jumps and single notes. Another ${pct(k.speed_aim_miss_share, 0)} are speed-aim misses (in streams, bursts and very fast jumps).`}
        />
        <Stat label="Jump miss rate" value={pct(k.jump_miss_rate)} />
        <Stat label="Near misses" value={pct(k.near_miss_share, 0)} hint="Aim misses that landed within 1.4 radii — just outside the circle." />
        <Stat label="Jump distance error" value={signed(k.jump_along_pct, 1, "%")} hint="Median over/undershoot along the jump direction, as % of the jump length." />
      </Tiles>
      {wq &&
        (wq.significant ? (
          <Alert tone="warn">
            Weakest quadrant: <strong>{wq.quadrant}</strong> — {pct(wq.miss_rate)} misses vs {pct(wq.rest_miss_rate)} elsewhere (
            {fmt(wq.relative_risk, 1)}×). See <Link to="/tips">Tips & Setup</Link> for how to fix it.
          </Alert>
        ) : (
          <Alert tone="info">
            Weakest quadrant: <strong>{wq.quadrant}</strong> — {pct(wq.miss_rate)} misses vs {pct(wq.rest_miss_rate)} elsewhere (
            {fmt(wq.relative_risk, 1)}×). The difference is still within noise.
          </Alert>
        ))}
      <Row>
        <Card title="Miss rate by screen quadrant" sub="The playfield cut into four. Each cell: share of the notes there you missed, and misses / notes. Pinker = more misses.">
          <QuadrantGrid cells={aim.quadrants} />
        </Card>
        <Card title="Where on the playfield you miss" sub="A finer grid of the playfield as you see it: the pinker a cell, the more of its notes you missed. Empty cells: too few notes there.">
          <PlayfieldGrid grid={aim.grid} />
        </Card>
      </Row>
      <Row>
        <ClicksCard />
        <Card
          title="Miss rate by jump direction"
          sub="Each wedge is a direction the cursor moves in to reach the note (jumps of 1+ circle). The longer the wedge, the more of those jumps you missed."
        >
          <Chart build={dirs} height={420} label="Miss rate by jump direction" />
        </Card>
      </Row>
      <Row>
        <Card
          title="By jump distance"
          sub="Bars: miss rate by how far the note is from the previous one (circle diameters). Line: how far past (+) or short of (−) the note you click, in circle radii."
        >
          <Chart build={dist} height={340} label="Miss rate and over/undershoot by jump distance" />
        </Card>
        <CalibrationCard aim={aim} />
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
      sub="The click that hit each note and the closest click of each aim miss, in circle radii from the note's centre."
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

function CalibrationCard({ aim }: { aim: Schemas["AimPage"] }) {
  const reg = aim.regression;
  return (
    <Card
      title="Aim calibration"
      sub="Your actual cursor movement compared with the movement each jump needed. 0% = exact; + = you move too far. This drives the tablet area / sensitivity tip on Tips & Setup."
    >
      {reg ? (
        <>
          <Tiles n={4}>
            <Stat label="Horizontal" value={signed((reg.scale_x - 1) * 100, 1, "%")} hint="How far you move compared with the real jump. + = overaim (too far)." />
            <Stat label="Vertical" value={signed((reg.scale_y - 1) * 100, 1, "%")} />
            <Stat label="Rotation" value={signed(reg.rotation_deg, 1, "°")} hint="+ = your movements come out clockwise." />
            <Stat
              label="Constant offset"
              value={`${Math.hypot(reg.offset_x, reg.offset_y).toFixed(1)} px`}
              hint={`x ${signed(reg.offset_x, 1)}, y ${signed(reg.offset_y, 1)} osu!px`}
            />
          </Tiles>
          <p className="small muted">
            Fitted on {int(reg.n)} jumps: your actual movement vs the movement that was needed. This is what the tablet-area /
            sensitivity tips are based on.
          </p>
        </>
      ) : (
        <EmptyState title="Not enough jumps yet">The calibration needs 40+ jumps.</EmptyState>
      )}
      {aim.angles.length > 0 && (
        <div className="section">
          <h3 className="section__title">By angle between jumps</h3>
          <p className="small muted">Sharp = back-and-forth jumps, wide = jumps that keep going in one direction. Notes are weighted by difficulty.</p>
          <DataTable
            label="Miss rate by angle between jumps"
            rows={aim.angles}
            rowKey={(r) => r.bin}
            columns={[
              { key: "bin", header: "Angle between jumps", cell: (r) => r.bin },
              { key: "n", header: "Notes", cell: (r) => int(r.objects), value: (r) => r.objects, align: "right" },
              { key: "rate", header: "Miss rate", cell: (r) => pct(r.miss_rate), value: (r) => r.miss_rate, align: "right" },
            ]}
          />
        </div>
      )}
    </Card>
  );
}
