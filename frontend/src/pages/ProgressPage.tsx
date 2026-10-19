import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router";

import { isApiError, type Schemas } from "../api/client";
import { useMeta, useProgress, useProgressPlayers, useProgressPlays, useSettings } from "../api/queries";
import { Chart } from "../charts/Chart";
import type { ChartTheme } from "../charts/palette";
import { playedChart, skillsChart, starsChart } from "../charts/progress";
import { DataTable } from "../components/DataTable";
import { IconTrend } from "../components/icons";
import { EmptyState, ErrorCard, LoadingPage } from "../components/states";
import { Card, Delta, Field, Page, Row, Segmented, Stat, Tiles } from "../components/ui";
import { fmt, int, isoDay, localTime, pct, shortLabel, stars as starsText } from "../lib/format";

type Period = Schemas["ProgressOut"]["period"];
type PRow = Schemas["PeriodRow"];

const WORD: Record<Period, string> = { month: "month", week: "week", day: "day" };

export default function ProgressPage() {
  const settings = useSettings();
  const players = useProgressPlayers();
  const [player, setPlayer] = useState<string | undefined>(undefined);
  const [period, setPeriod] = useState<Period>("month");
  const [since, setSince] = useState<string | undefined>(undefined);
  const [until, setUntil] = useState<string | undefined>(undefined);
  const names = players.data ?? [];
  const pref = settings.data?.player;
  const chosen = player ?? (pref && names.some((n) => n.name === pref) ? pref : names[0]?.name);
  const q = useProgress({ player: chosen, period, since, until }, names.length > 0);

  let body;
  if (players.isPending || (names.length > 0 && q.isPending)) body = <LoadingPage tiles={6} />;
  else if (!names.length || isApiError(q.error, "no_history"))
    body = (
      <Card>
        <EmptyState
          icon={<IconTrend />}
          title="Nothing saved yet"
          action={
            <Link className="btn btn--primary" to="/replays">
              Go to Replays
            </Link>
          }
        >
          Analyse your replays on the Replays page — choose All there once to fill in your older months.
        </EmptyState>
      </Card>
    );
  else if (q.error) body = <ErrorCard error={q.error} onRetry={() => void q.refetch()} />;
  else if (q.data)
    body = (
      <>
        <Card>
          <div className="controls">
            <Field label="Player">
              <select className="select" value={chosen ?? ""} onChange={(e) => setPlayer(e.target.value)}>
                {names.map((n) => (
                  <option key={n.name} value={n.name}>
                    {n.name || "(no name)"} ({n.plays} plays saved)
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Group by">
              <Segmented
                label="Group by"
                block
                value={period}
                onChange={setPeriod}
                options={[
                  { value: "month", label: "Month" },
                  { value: "week", label: "Week" },
                  { value: "day", label: "Day" },
                ]}
              />
            </Field>
            <Field label="From">
              <input className="input" type="date" value={since ?? q.data.first_day ?? ""} onChange={(e) => setSince(e.target.value || undefined)} />
            </Field>
            <Field label="To (included)">
              <input className="input" type="date" value={until ?? isoDay()} onChange={(e) => setUntil(e.target.value || undefined)} />
            </Field>
          </div>
        </Card>
        {q.data.rows.length ? (
          <ProgressBody rows={q.data.rows} period={period} player={q.data.player} reference={q.data.skill_reference_stars} />
        ) : (
          <Card>
            <EmptyState icon={<IconTrend />} title="No plays saved in that range" />
          </Card>
        )}
      </>
    );

  return (
    <Page
      title="Progress"
      sub="Every analysis is saved here (progress.sqlite in the osu! coach data folder), so the history stays even if you delete replays later. These numbers are not weighted by difficulty, so periods stay comparable."
    >
      {body}
    </Page>
  );
}

function delta(last: PRow, prev: PRow | undefined, key: keyof PRow, digits: number, scale = 1) {
  const a = last[key];
  const b = prev?.[key];
  if (typeof a !== "number" || typeof b !== "number") return null;
  const d = (a - b) * scale;
  return <Delta value={d} text={`${d >= 0 ? "+" : "−"}${Math.abs(d).toFixed(digits)}`} />;
}

function ProgressBody({ rows, period, player, reference }: { rows: PRow[]; period: Period; player: string; reference: number | null }) {
  const meta = useMeta();
  const word = WORD[period];
  const last = rows[rows.length - 1];
  const prev = rows.length > 1 ? rows[rows.length - 2] : undefined;
  const skills = useMemo(() => (meta.data?.skills ?? []).map((s) => ({ key: s.key, label: shortLabel(s.label) })), [meta.data]);
  const stars = useCallback((t: ChartTheme) => starsChart(rows, t), [rows]);
  const played = useCallback((t: ChartTheme) => playedChart(rows, t), [rows]);
  const skillChart = useCallback((t: ChartTheme) => skillsChart(rows, skills, t), [rows, skills]);
  const hasSkills = rows.some((r) => Object.values(r.skills).some((v) => v !== null));
  return (
    <>
      <Tiles n={6}>
        <Stat label="Comfort ★" value={fmt(last.comfort_stars, 2)} note={delta(last, prev, "comfort_stars", 2)}
          hint="75% of your clean, finished plays (≤ 2 misses per 100 notes) are at or below this." />
        <Stat label="Hardest clean pass ★" value={fmt(last.max_stars_passed, 2)} note={delta(last, prev, "max_stars_passed", 2)}
          hint="Hardest map finished with at most 5 misses per 100 notes." />
        <Stat label="Plays" value={int(last.plays)} note={delta(last, prev, "plays", 0)} />
        <Stat label="New maps" value={int(last.new_maps)} note={delta(last, prev, "new_maps", 0)} hint={`Maps played for the first time that ${word}.`} />
        <Stat label="Accuracy" value={pct(last.accuracy, 2)} note={delta(last, prev, "accuracy", 2, 100)} />
        <Stat label="Play time" value={fmt(last.minutes, 0, " min")} note={delta(last, prev, "minutes", 0)} />
      </Tiles>
      <p className="small muted" style={{ marginTop: -6 }}>
        {last.key}
        {prev ? ` compared with ${prev.key}.` : "."}
        {last.few_plays ? ` Few plays that ${word} — the numbers are rough.` : ""}
      </p>
      <Row>
        <Card
          title={`Star rating by ${word}`}
          sub="Comfort = the star rating 75% of your clean plays stay under; hardest clean pass / full combo = the hardest map finished with ≤ 5 misses per 100 notes / without a miss. Hollow points: fewer than 5 plays."
        >
          <Chart build={stars} height={320} label="Star rating by period" />
        </Card>
        <Card title="What you played" sub={`Bars: plays and maps played for the first time each ${word} (left axis); line: minutes played (right axis).`}>
          <Chart build={played} height={320} label="Plays, new maps and minutes by period" />
        </Card>
      </Row>
      <Card
        title={`Skills by ${word}`}
        sub={`The same skill ratings as the Overview's chart, every ${word} rated at your comfort level${reference !== null ? ` (${starsText(reference, 1)})` : ""}: 50 = what that level expects, higher = you played the skill better that ${word}. Click a skill in the legend to hide or show it. Hollow points: fewer than 5 plays.`}
      >
        {hasSkills ? (
          <Chart build={skillChart} height={360} label="Skill scores by period" />
        ) : (
          <EmptyState title="No skill scores yet">
            {`Skill ratings need 5+ plays in a ${word}, with 3+ different maps for a skill. Scores saved by an earlier version aren't shown: analyse your replays again (Replays page) to rate every ${word}.`}
          </EmptyState>
        )}
      </Card>
      <PlaysCard rows={rows} period={period} player={player} />
    </>
  );
}

function PlaysCard({ rows, period, player }: { rows: PRow[]; period: Period; player: string }) {
  const keys = useMemo(() => rows.map((r) => r.key).reverse(), [rows]);
  const [picked, setPicked] = useState<string | null>(null);
  const key = picked && keys.includes(picked) ? picked : keys[0] ?? null;
  const plays = useProgressPlays({ player, period, key });
  return (
    <Card
      title={`Plays of one ${WORD[period]}`}
      sub={`Every play saved for the ${WORD[period]} you pick: result, accuracy and misses.`}
      actions={
        <select className="select" value={key ?? ""} onChange={(e) => setPicked(e.target.value)} aria-label="Period">
          {keys.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      }
    >
      <DataTable
        label="Plays"
        rows={plays.data ?? []}
        rowKey={(r, i) => `${r.played_at}-${i}`}
        maxHeight={420}
        empty={<EmptyState title={plays.isPending ? "Loading…" : "No plays"} />}
        columns={[
          { key: "played", header: "Played", cell: (r) => localTime(r.played_at), value: (r) => r.played_at },
          { key: "map", header: "Map", cell: (r) => r.map, strong: true, wrap: true },
          { key: "mods", header: "Mods", cell: (r) => r.mods },
          { key: "stars", header: "Difficulty", cell: (r) => fmt(r.stars, 2, " ★"), value: (r) => r.stars, align: "right" },
          { key: "acc", header: "Accuracy", cell: (r) => pct(r.accuracy, 2), value: (r) => r.accuracy, align: "right" },
          { key: "miss", header: "Misses", cell: (r) => int(r.misses), value: (r) => r.misses, align: "right" },
          {
            key: "combo",
            header: "Combo",
            cell: (r) => (r.map_combo ? `${int(r.combo)}/${int(r.map_combo)}` : int(r.combo)),
            value: (r) => r.combo,
            align: "right",
          },
          {
            key: "result",
            header: "Result",
            cell: (r) => (
              <span className={`badge badge--${r.result === "failed" ? "bad" : r.result === "full combo" ? "good" : "info"}`}>{r.result}</span>
            ),
            value: (r) => r.result,
          },
        ]}
      />
    </Card>
  );
}
