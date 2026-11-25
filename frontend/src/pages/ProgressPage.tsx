import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router";

import { isApiError, type Schemas } from "../api/client";
import { useMeta, useProgress, useProgressPlayers, useProgressPlays, useSettings } from "../api/queries";
import { Chart } from "../charts/Chart";
import type { ChartTheme } from "../charts/palette";
import { starsChart } from "../charts/progress";
import { DataTable } from "../components/DataTable";
import { DateRangePicker } from "../components/DateRangePicker";
import { IconTrend } from "../components/icons";
import { EmptyState, ErrorCard, LoadingPage } from "../components/states";
import { PlayCalendar } from "../components/PlayCalendar";
import { SkillTrends } from "../components/SkillTrends";
import { Card, Delta, Field, Page, Row, Segmented, Stat, Tiles } from "../components/ui";
import { Verdict } from "../components/Verdict";
import { playStats } from "../lib/playCalendar";
import { ends, periodLabel, periodStart, timeline } from "../lib/progressTime";
import { meaningful, skillTrends, type Trend } from "../lib/skillTrends";
import { fmt, int, isoDay, localTime, pct, shortLabel, stars as starsText } from "../lib/format";

type Period = Schemas["ProgressOut"]["period"];
type PRow = Schemas["PeriodRow"];
type Replays = Schemas["ProgressOut"]["replays"];

const WORD: Record<Period, string> = { month: "month", week: "week", day: "day" };

export default function ProgressPage() {
  const settings = useSettings();
  const players = useProgressPlayers();
  const [player, setPlayer] = useState<string | undefined>(undefined);
  // weeks: the last year a timeline of ~50 points, not ~12
  const [period, setPeriod] = useState<Period>("week");
  // the last year, as the analysis takes (Dates: any range, or all of the history saved)
  const [since, setSince] = useState<string | undefined>(() => isoDay(-365));
  const [until, setUntil] = useState<string | undefined>(undefined);
  const [replays, setReplays] = useState<Replays>("analysed");
  const names = players.data ?? [];
  const pref = settings.data?.player;
  const chosen = player ?? (pref && names.some((n) => n.name === pref) ? pref : names[0]?.name);
  const q = useProgress({ player: chosen, period, since, until, replays }, names.length > 0);

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
            {q.data.analysed_plays !== null && q.data.analysed_plays !== undefined ? (
              <Field label="Replays">
                <Segmented
                  label="Replays"
                  block
                  value={q.data.replays}
                  onChange={setReplays}
                  options={[
                    { value: "analysed", label: `Analysed (${int(q.data.analysed_plays)})` },
                    { value: "all", label: "All saved" },
                  ]}
                />
              </Field>
            ) : null}
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
            <Field label="Dates">
              <DateRangePicker
                label="Dates"
                value={since || until ? { from: since ?? q.data.first_day ?? isoDay(), to: until ?? isoDay() } : null}
                onChange={(r) => { setSince(r?.from); setUntil(r?.to ?? undefined); }}
                span={[q.data.first_day ?? isoDay(), isoDay()]}
              />
            </Field>
          </div>
        </Card>
        {q.data.rows.length ? (
          <ProgressBody
            rows={q.data.rows}
            period={period}
            player={q.data.player}
            reference={q.data.skill_reference_stars}
            replays={q.data.replays}
            unit={q.data.unit}
          />
        ) : (
          <Card>
            <EmptyState icon={<IconTrend />} title="No plays saved in that range" />
          </Card>
        )}
      </>
    );

  return (
    <Page title="Progress">
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

function ProgressBody({
  rows,
  period,
  player,
  reference,
  replays,
  unit,
}: {
  rows: PRow[];
  period: Period;
  player: string;
  reference: number | null;
  replays: Replays;
  /** what the chosen engine rates skills in: scores, or star levels (Star Levels) */
  unit: Schemas["ProgressOut"]["unit"];
}) {
  const meta = useMeta();
  const word = WORD[period];
  const last = rows[rows.length - 1];
  const prev = rows.length > 1 ? rows[rows.length - 2] : undefined;
  const skills = useMemo(() => (meta.data?.skills ?? []).map((s) => ({ key: s.key, label: shortLabel(s.label) })), [meta.data]);
  const stars = useCallback((t: ChartTheme) => starsChart(rows, period, t), [rows, period]);
  const inStars = unit === "stars";
  const trends = useMemo(() => skillTrends(rows, period, skills, inStars), [rows, period, skills, inStars]);
  return (
    <>
      <Tiles n={6}>
        <Stat label="Comfort ★" value={fmt(last.comfort_stars, 2)} note={delta(last, prev, "comfort_stars", 2)}
          hint="75% of your clean, finished plays (≤ 2 misses per 100 notes) are at or below this." />
        <Stat label="Hardest clean pass ★" value={fmt(last.max_stars_passed, 2)} note={delta(last, prev, "max_stars_passed", 2)}
          valueHint={last.max_stars_passed_map ?? undefined}
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
          hint="Comfort = the star rating 75% of your clean plays stay under; hardest clean pass = the hardest map finished with ≤ 5 misses per 100 notes. The axis is real time: a gap = no plays then. Hollow points: fewer than 5 plays."
        >
          <ComfortVerdict rows={rows} period={period} />
          <Chart build={stars} height={280} label="Star rating by period" />
        </Card>
        <CalendarCard player={player} replays={replays} />
      </Row>
      <Card
        title={`Skills by ${word}`}
        hint={inStars
          ? `Star Levels: each skill's star level every ${word}, fitted to the plays of that ${word} alone (the star rating it holds up on, as the Overview's). All skills on the same scale and timeline; the line breaks where you didn't play.`
          : `The same skill ratings as the Overview's, every ${word} rated at ${replays === "analysed" ? "the Overview's" : "your"} comfort level${reference !== null ? ` (${starsText(reference, 1)})` : ""}: 50 = what maps of that level demand, higher = you played the skill better that ${word}. All skills on the same scale and timeline; the line breaks where you didn't play.`}
      >
        {trends.length ? (
          <>
            <TrendVerdict trends={trends} inStars={inStars} first={firstTrendLabel(rows, trends)} word={word} />
            <SkillTrends trends={trends} inStars={inStars} />
          </>
        ) : (
          <EmptyState title={inStars ? "No star levels yet" : "No skill scores yet"}>
            {inStars
              ? `Star levels need 5+ plays in a ${word}. They are worked out when your replays are analysed: analyse them again (Replays page) to fit every ${word}.`
              : `Skill ratings need 5+ plays in a ${word}, with 3+ different maps for a skill. Scores saved by an earlier version aren't shown: analyse your replays again (Replays page) to rate every ${word}.`}
          </EmptyState>
        )}
      </Card>
      <PlaysCard rows={rows} period={period} player={player} replays={replays} />
    </>
  );
}

/** Your comfort level now and how it moved over the periods shown, from the first with enough plays (a period with
 * a play or two says little). */
function ComfortVerdict({ rows, period }: { rows: PRow[]; period: Period }) {
  const latest = [...rows].reverse().find((r) => r.comfort_stars !== null);
  if (!latest) return <Verdict tone="muted">No comfort level yet: it needs a few clean, finished plays.</Verdict>;
  const solid = rows.filter((r) => !r.few_plays && r.comfort_stars !== null);
  const e = ends(timeline(solid, period, (r) => r.comfort_stars));
  const now = solid.length ? solid[solid.length - 1] : latest;
  // the latest period, when it rests on a play or two, is said apart: the number shown is the latest solid one
  const rough = latest !== now ? ` This ${WORD[period]}: ${latest.comfort_stars!.toFixed(2)}★ from ${latest.plays} ${latest.plays === 1 ? "play" : "plays"}, rough.` : "";
  if (!e)
    return (
      <Verdict tone="info" value={`${now.comfort_stars!.toFixed(2)}★`}>
        Your comfort level. Play more {WORD[period]}s to see where it goes.{rough}
      </Verdict>
    );
  const d = e.last - e.first;
  const tone = d >= 0.1 ? "good" : d <= -0.1 ? "bad" : "info";
  return (
    <Verdict tone={tone} value={`${now.comfort_stars!.toFixed(2)}★`}>
      Your comfort level {Math.abs(d) < 0.1 ? "held steady" : d > 0 ? `rose ${d.toFixed(2)}★` : `fell ${Math.abs(d).toFixed(2)}★`} since{" "}
      {periodLabel(solid[0].key)}.{rough}
    </Verdict>
  );
}

function CalendarCard({ player, replays }: { player: string; replays: Replays }) {
  const since = isoDay(-364);
  const q = useProgress({ player, period: "day", since, until: undefined, replays }, true);
  const plays = useMemo(() => new Map((q.data?.rows ?? []).map((r) => [r.key, r.plays])), [q.data]);
  const st = useMemo(() => playStats(plays), [plays]);
  return (
    <Card title="When you played" hint="The last year, a square per day: the darker, the more plays that day. Point at a day for its plays.">
      {q.data ? (
        <>
          <Verdict tone={st.lastYear ? "info" : "muted"} value={`${st.lastYear} days`}>
            {st.lastYear
              ? <>You played on {st.lastYear} days of the last year, {st.lastMonth} of them in the last 30 days.{st.longestBreak >= 14 ? ` Your longest break: ${st.longestBreak} days.` : ""}</>
              : "No plays in the last year."}
          </Verdict>
          <PlayCalendar plays={plays} />
        </>
      ) : (
        <div className="skeleton" style={{ height: 160 }} />
      )}
    </Card>
  );
}

/** The first period any skill has a value in, as people say it. */
function firstTrendLabel(rows: PRow[], trends: Trend[]): string {
  const first = Math.min(...trends.map((t) => t.points[0]?.[0] ?? Infinity));
  const key = rows.find((r) => periodStart(r.key)?.getTime() === first)?.key;
  return key ? periodLabel(key) : "the first period";
}

/** The skills that moved the most since the first period shown. */
function TrendVerdict({ trends, inStars, first, word }: { trends: Trend[]; inStars: boolean; first: string | undefined; word: string }) {
  if (trends.every((t) => t.change === null))
    return <Verdict tone="muted">Only one {word} with skill levels so far: they need 5+ plays in a {word}. Play more, or group by a shorter period.</Verdict>;
  const moved = trends.filter((t) => meaningful(t.change, inStars)).sort((a, b) => b.change! - a.change!);
  const up = moved.filter((t) => t.change! > 0);
  const down = moved.filter((t) => t.change! < 0).reverse();
  const amount = (c: number) => `${c > 0 ? "+" : "−"}${inStars ? `${Math.abs(c).toFixed(1)}★` : Math.abs(c).toFixed(0)}`;
  if (!moved.length)
    return <Verdict tone="info">No skill moved much{first ? ` since ${first}` : ""}: your skills held where they were.</Verdict>;
  return (
    <Verdict tone={down.length && !up.length ? "bad" : up.length && !down.length ? "good" : "info"}>
      Since {first}:{" "}
      {up.length > 0 && <>{up[0].label} rose most ({amount(up[0].change!)})</>}
      {up.length > 0 && down.length > 0 && "; "}
      {down.length > 0 && <>{down[0].label} fell most ({amount(down[0].change!)})</>}.
    </Verdict>
  );
}

function PlaysCard({ rows, period, player, replays }: { rows: PRow[]; period: Period; player: string; replays: Replays }) {
  const keys = useMemo(() => rows.map((r) => r.key).reverse(), [rows]);
  const [picked, setPicked] = useState<string | null>(null);
  const key = picked && keys.includes(picked) ? picked : keys[0] ?? null;
  const plays = useProgressPlays({ player, period, key, replays });
  return (
    <Card
      title={`Plays of one ${WORD[period]}`}
      hint={`Every play saved for the ${WORD[period]} you pick: result, accuracy and misses.`}
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
