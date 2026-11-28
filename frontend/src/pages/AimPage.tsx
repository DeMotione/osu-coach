import { useCallback, useEffect, useMemo, useState } from "react";

import type { Schemas } from "../api/client";
import { useAim, useAnalysedReplays, useClicks } from "../api/queries";
import { Chart } from "../charts/Chart";
import { judgedBars } from "../charts/judged";
import type { ChartTheme } from "../charts/palette";
import { ClicksView } from "../components/Clicks";
import { DateRangePicker } from "../components/DateRangePicker";
import { PlayfieldGrid, QuadrantGrid } from "../components/Heat";
import { RangeSlider } from "../components/RangeSlider";
import { QueryView } from "../components/states";
import { Card, Page, Row, Segmented, Stat, Tiles } from "../components/ui";
import { ChartNote } from "../components/ChartNote";
import { PractiseLink, Verdict } from "../components/Verdict";
import { type AimKind, aimSpot } from "../lib/practise";
import { ANGLE_SHORT, averageAlong, jumpAngle, jumpDirection, jumpDistance, overshoot, screenPart } from "../lib/aimWords";
import { clickFilter, clicksCaption, starBounds } from "../lib/clicks";
import { dayOf, type DayRange } from "../lib/dateRange";
import { int, pct, signed } from "../lib/format";
import { judge, type Judged, listed, MIN_NOTES, share, times, weakest } from "../lib/verdict";

export default function AimPage() {
  const q = useAim();
  return (
    <Page title="Aim">
      <QueryView query={q}>{(aim) => <AimBody aim={aim} />}</QueryView>
    </Page>
  );
}

type Groups = { directions: Judged[]; distances: Judged[]; angles: Judged[]; quadrants: Judged[] };

function AimBody({ aim }: { aim: Schemas["AimPage"] }) {
  const k = aim.kpis;
  const groups: Groups = useMemo(
    () => ({
      directions: judge(aim.directions.map((d) => ({ label: d.direction, rate: d.miss_rate, n: d.objects }))),
      distances: judge(aim.distances.map((d) => ({ label: d.bin, rate: d.miss_rate, n: d.objects }))),
      angles: judge(aim.angles.map((a) => ({ label: a.bin, rate: a.miss_rate, n: a.objects }))),
      quadrants: judge(aim.quadrants.map((q) => ({ label: q.quadrant, rate: q.miss_rate, n: q.objects }))),
    }),
    [aim],
  );
  return (
    <>
      <Tiles n={3}>
        <Stat label="Jump miss rate" value={pct(k.jump_miss_rate)} />
        <Stat label="Near misses" value={pct(k.near_miss_share, 0)} hint="Aim misses that landed within a 1.4 radius of the circle, where the base circle size is 1." />
        <Stat label="Jump distance error" value={signed(k.jump_along_pct, 1, "%")} hint="Median over/undershoot along the jump direction, as % of the jump length." />
      </Tiles>
      <WeakSpotsCard groups={groups} />
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
        <DirectionsCard groups={groups.directions} />
      </Row>
      <Row>
        <DistanceCard groups={groups.distances} rows={aim.distances} />
        <AnglesCard groups={groups.angles} />
      </Row>
    </>
  );
}

const BAR_HINT =
  "Red = you miss clearly more of these than usual, green = clearly fewer, grey = as usual, faint with a ? = too few jumps to tell.";

/** Every kind of jump that is clearly worse than your usual, the most misses it costs you first. */
function WeakSpotsCard({ groups }: { groups: Groups }) {
  const spots = useMemo(() => {
    const named = (gs: Judged[], name: (l: string) => string, kind: AimKind) =>
      weakest(gs).map((g) => ({ ...g, name: name(g.label), kind, practise: aimSpot(kind, g.label) }));
    return [
      ...named(groups.directions, jumpDirection, "direction"),
      ...named(groups.distances, jumpDistance, "distance"),
      ...named(groups.angles, jumpAngle, "angle"),
      ...named(groups.quadrants, screenPart, "quadrant"),
    ].sort((a, b) => (b.rate! - (b.usual ?? 0)) * b.n - (a.rate! - (a.usual ?? 0)) * a.n).slice(0, 4);
  }, [groups]);
  const top = spots[0];
  return (
    <Card
      title="Aim weak spots"
      hint="Every kind of jump (direction, distance, angle, part of the screen) you miss clearly more of than usual, the one costing you the most misses first. Clearly = enough jumps that it isn't chance. Practise makes a playlist of maps full of that kind of jump (a direction no map statistic tells)."
    >
      {top ? (
        <>
          <Verdict tone="bad" value={share(top.rate)} practise={top.practise}>
            Your weakest jumps: <strong>{top.name}</strong> — {share(top.rate)} missed, {times(top.ratio)} your average {share(top.usual)}.
          </Verdict>
          {spots.length > 1 && (
            <ul className="weak-list" aria-label="Other weak spots">
              {spots.slice(1).map((g) => (
                <li key={`${g.kind}:${g.label}`}>
                  <span className="weak-list__what">{g.name.charAt(0).toUpperCase() + g.name.slice(1)}</span>
                  <span className="weak-list__rate">{share(g.rate)}</span>
                  <span className="weak-list__more">{times(g.ratio)} your average · {int(g.n)} notes</span>
                  {g.practise && <PractiseLink practise={g.practise}>Practise</PractiseLink>}
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <Verdict tone="good">
          No kind of jump stands out: you miss about as much of every direction, distance, angle and part of the screen.
        </Verdict>
      )}
    </Card>
  );
}

function DirectionsCard({ groups }: { groups: Judged[] }) {
  const build = useCallback(
    (t: ChartTheme) => judgedBars({ groups, unit: "jumps", sideways: true, describe: jumpDirection }, t),
    [groups],
  );
  const bad = weakest(groups);
  return (
    <Card title="Miss rate by jump direction" hint={`The direction the cursor moves in to reach the note (jumps of 1+ circle), worst on top. ${BAR_HINT}`}>
      {bad.length ? (
        <Verdict tone="bad" value={share(bad[0].rate)}>
          Jumps moving <strong>{listed(bad.map((g) => g.label))}</strong>: you miss {times(bad[0].ratio)} your average.
        </Verdict>
      ) : (
        <Verdict tone="good">No direction stands out: you miss about the same whichever way you move.</Verdict>
      )}
      <Chart build={build} height={300} label="Miss rate by jump direction" />
      <ChartNote groups={groups} />
    </Card>
  );
}

function DistanceCard({ groups, rows }: { groups: Judged[]; rows: Schemas["DistanceRow"][] }) {
  const build = useCallback(
    (t: ChartTheme) => judgedBars({ groups, unit: "jumps", axisName: "distance from the previous note (circle widths)", describe: jumpDistance }, t),
    [groups],
  );
  const bad = weakest(groups);
  const shoot = overshoot(averageAlong(rows, MIN_NOTES));
  return (
    <Card title="By jump distance" hint={`How far the note is from the previous one, in circle widths. ${BAR_HINT}`}>
      {bad.length ? (
        <Verdict tone="bad" value={share(bad[0].rate)}>
          <strong>{capital(jumpDistance(bad[0].label))}</strong>: {times(bad[0].ratio)} your average miss rate. {shoot}
        </Verdict>
      ) : (
        <Verdict tone="good">No jump length stands out. {shoot}</Verdict>
      )}
      <Chart build={build} height={300} label="Miss rate by jump distance" />
      <ChartNote groups={groups} />
    </Card>
  );
}

function AnglesCard({ groups }: { groups: Judged[] }) {
  const short = useMemo(() => groups.map((g) => ({ ...g, label: ANGLE_SHORT[g.label] ?? g.label })), [groups]);
  const build = useCallback(
    (t: ChartTheme) =>
      judgedBars({ groups: short, unit: "jumps", axisName: "angle between one jump and the next", describe: (l) => jumpAngle(Object.keys(ANGLE_SHORT).find((k) => ANGLE_SHORT[k] === l) ?? l) }, t),
    [short],
  );
  const bad = weakest(groups);
  return (
    <Card
      title="By angle between jumps"
      hint={`Sharp turn = back-and-forth jumps, keeps going = jumps that continue in one direction. ${BAR_HINT}`}
    >
      {bad.length ? (
        <Verdict tone="bad" value={share(bad[0].rate)}>
          <strong>{capital(jumpAngle(bad[0].label))}</strong>: {times(bad[0].ratio)} your average miss rate.
        </Verdict>
      ) : groups.some((g) => g.standing !== "few") ? (
        <Verdict tone="good">No kind of turn stands out: sharp and wide jumps cost you about the same.</Verdict>
      ) : (
        <Verdict tone="muted">Not enough jumps yet to compare the angles.</Verdict>
      )}
      <Chart build={build} height={300} label="Miss rate by angle between jumps" />
      <ChartNote groups={groups} />
    </Card>
  );
}

const capital = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

const CLICKS_HINT = "The click that hit each note and the closest click of each aim miss, in circle radii from the note's centre.";

function ClicksCard() {
  const [view, setView] = useState<"screen" | "movement">("screen");
  const replays = useAnalysedReplays();
  const plays = useMemo(() => replays.data ?? [], [replays.data]);
  const bounds = useMemo(() => starBounds(plays), [plays]);
  const played = useMemo(() => new Set(plays.flatMap((r) => (r.played_at ? [dayOf(r.played_at)] : []))), [plays]);
  const [stars, setStars] = useState<[number, number] | null>(null);
  const [dates, setDates] = useState<DayRange | null>(null);
  // the chart follows the slider once it stops moving
  const [chosen, setChosen] = useState(stars);
  useEffect(() => {
    const t = setTimeout(() => setChosen(stars), 300);
    return () => clearTimeout(t);
  }, [stars]);
  const filter = useMemo(() => clickFilter(chosen, bounds, dates), [chosen, bounds, dates]);
  const q = useClicks(view, filter);
  const [low, high] = stars ?? bounds ?? [0, 0];
  const caption = q.data?.enough ? clicksCaption(q.data) : "";
  return (
    <Card
      className="clicks-card"
      title="Where your clicks land"
      hint={caption ? `${CLICKS_HINT}\n\n${caption}` : CLICKS_HINT}
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
      {/* two equal columns, each a label and its value over a control, one column on narrow cards */}
      <div className="clicks-filters">
        {bounds && bounds[1] > bounds[0] && (
          <RangeSlider label="Star rating" min={bounds[0]} max={bounds[1]} step={0.1} value={[low, high]}
            onChange={setStars} format={(v) => `${v.toFixed(1)}★`} />
        )}
        <div className="labelled">
          <div className="labelled__head">
            <span className="field__label">Played</span>
            {q.data && plays.length > 0 && (
              <span className="labelled__value">
                {int(q.data.plays)} of {int(plays.length)} plays
              </span>
            )}
          </div>
          <DateRangePicker value={dates} onChange={setDates} played={played} label="Played" />
        </div>
      </div>
      {q.data ? (
        <ClicksView clicks={q.data} empty={Object.keys(filter).length ? "Not enough clicks in these plays" : undefined} />
      ) : (
        <div className="skeleton grow" style={{ minHeight: 360 }} />
      )}
    </Card>
  );
}
