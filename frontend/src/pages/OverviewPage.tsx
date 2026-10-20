import { useCallback, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";

import type { Schemas } from "../api/client";
import { useMeta, useOverview, usePatchSettings, useSettings } from "../api/queries";
import { Chart } from "../charts/Chart";
import { compareBars, missCauses, skillBars } from "../charts/overview";
import type { ChartTheme } from "../charts/palette";
import { IconCheck } from "../components/icons";
import { StarPicker } from "../components/StarPicker";
import { QueryView } from "../components/states";
import { Alert, Badge, Card, Page, Row, Stat, Switch, Tiles, type TileCount } from "../components/ui";
import { fmt, int, pct, span, stars } from "../lib/format";
import { chanceLabel, fromComfort, pickTarget, starLabel, targetOptions } from "../lib/starCompare";

type Overview = Schemas["Overview"];

export default function OverviewPage() {
  const q = useOverview();
  return (
    <Page
      title="Overview"
      sub="Your main numbers at a glance. Every number is weighted by difficulty: plays close to your level count fully, plays far below or above it hardly count (see Your level)."
    >
      <QueryView query={q} tiles={6}>
        {(ov) => <OverviewBody ov={ov} />}
      </QueryView>
    </Page>
  );
}

function OverviewBody({ ov }: { ov: Overview }) {
  const meta = useMeta();
  const k = ov.kpis;
  const help = meta.data?.skills;
  // consistency is measured around the comfort level only, so the comparison with other star ratings leaves it out
  const compared = useMemo(() => ov.skills.filter((s) => s.key !== "consistency"), [ov.skills]);
  const skillsChart = useCallback((t: ChartTheme) => skillBars(ov.skills, help ?? [], t), [ov.skills, help]);
  const descriptions = useMemo(
    () => Object.fromEntries((meta.data?.miss_causes ?? []).map((m) => [m.key, m.description])),
    [meta.data],
  );
  const missChart = useCallback((t: ChartTheme) => missCauses(ov.miss_causes, descriptions, t), [ov.miss_causes, descriptions]);
  const skillsHeight = Math.max(320, ov.skills.length * 44);

  return (
    <>
      <LevelCard ov={ov} />
      <Tiles n={6}>
        <Stat label="Replays" value={int(k.replays)} hint={`${k.maps} different maps; they count as ${fmt(k.weighted_replays, 1)} after the weighting.`} />
        <Stat label="Play time" value={fmt(k.play_minutes, 0, " min")} />
        <Stat label="Comfort level" value={stars(k.comfort_stars, 1)}
          hint="75th percentile of recent completed map/mod configurations with at most 2 head misses per 100 notes; at least 3 configurations required." />
        <Stat label="Unstable rate" value={fmt(k.ur, 0)} hint="10 × the spread of your hit timing in ms. Lower = steadier timing." />
        <Stat label="Misses / 100 notes" value={fmt(k.misses_per_100, 1)} />
        <Stat label="Accuracy" value={pct(k.accuracy)} />
      </Tiles>
      <Card
        title="Skills at your comfort level"
        sub={`Experimental replay ratings, 0–100; 50 = expected performance at your ${stars(k.comfort_stars, 1)} comfort level under assumed curves. Most skills use the best play per map/mod; Timing accuracy uses weighted hit single notes from all selected replays. Consistency: how steadily you hold combo and accuracy on different maps within ±1★ of your comfort level. Grey = not measured yet: point at a bar to see what to play.`}
      >
        <Chart build={skillsChart} height={skillsHeight} label="Skill scores against your level" />
      </Card>
      <CompareCard compare={ov.compare} skills={compared} help={help} height={Math.max(320, compared.length * 44)} />
      <Row>
        <Card
          title="Why you miss"
          sub="Share of your misses by cause (weighted by difficulty). Aim = jumps and single notes; speed-aim = tapped in time but the cursor couldn't keep up in a stream, burst or very fast jump; the others are tapping / reading misses."
          foot={
            ov.aim_split
              ? `Against what the difficulty predicts: on fast patterns you miss ${ov.aim_split.fast_ratio.toFixed(1)}× the expected, on normal-speed jumps and notes ${ov.aim_split.normal_ratio.toFixed(1)}× (1.0× = as expected for your level).`
              : undefined
          }
        >
          {ov.miss_causes.length ? (
            <Chart build={missChart} height={Math.max(240, ov.miss_causes.length * 40)} label="Misses by cause" />
          ) : (
            <Alert tone="good">No misses in these replays.</Alert>
          )}
        </Card>
        <StrengthsCard ov={ov} />
      </Row>
      <TopTips tips={ov.top_tips} />
      <p className="small muted">
        {ov.sim_agreement === null
          ? "Data check: these replays don't store their results, so the re-simulation couldn't be cross-checked."
          : `Data check: re-simulated judgements match the replays exactly on ${pct(ov.sim_exact_share, 0)} of replays (${pct(ov.sim_agreement)} of all judgements).`}
      </p>
    </>
  );
}

/** A level to one decimal, as it is set by hand. */
const tenth = (v: number) => Math.round(v * 10) / 10;

function LevelCard({ ov }: { ov: Overview }) {
  const lv = ov.level;
  const settings = useSettings();
  const patch = usePatchSettings();
  const applied = settings.data?.level_override ?? null; // null = the detected level
  const detected = tenth(lv.detected ?? lv.stars ?? 4);
  // the switch and the typed level are only what the player is editing; nothing changes until Apply
  const [byHandInput, setByHand] = useState<boolean | null>(null);
  const [draftInput, setDraft] = useState<string | null>(null);
  const [done, setDone] = useState<number | "detected" | null>(null); // what the last change applied
  const byHand = byHandInput ?? applied !== null;
  const draft = draftInput ?? (applied ?? detected).toFixed(1);
  const n = Number(draft);
  const value = draft.trim() !== "" && Number.isFinite(n) && n >= 1 && n <= 12 ? tenth(n) : null;
  const changed = value !== null && value !== applied;

  const apply = (level: number | null) => {
    setDone(null);
    patch.mutate({ level_override: level }, { onSuccess: () => setDone(level ?? "detected") });
  };

  if (lv.stars === null)
    return (
      <Card>
        <p>
          <strong>Your level: unknown</strong> — no star ratings in these replays, so every play counts fully.
        </p>
      </Card>
    );

  const target = patch.variables?.level_override;
  let status: ReactNode = null;
  if (patch.isPending)
    status = (
      <>
        <span className="spinner" aria-hidden="true" />
        Recalculating your numbers with {target === null || target === undefined ? "the detected level" : stars(target, 1)}…
      </>
    );
  else if (patch.isError) status = patch.error.message;
  else if (byHand && value === null) status = "Enter a level from 1 to 12★.";
  else if (byHand && changed) status = "Not applied yet: press Apply.";
  else if (done !== null)
    status = (
      <>
        <IconCheck />
        {done === "detected"
          ? `Back to the detected level: every number on this page uses ${stars(lv.stars, 1)} again.`
          : `Applied: every number on this page now uses ${stars(done, 1)}.`}
      </>
    );
  const tone = patch.isPending ? "" : patch.isError || (byHand && value === null) ? " apply-status--bad" : done !== null && !changed ? " apply-status--good" : "";

  return (
    <Card>
      <div className="split" style={{ alignItems: "stretch" }}>
        <div className="stack" style={{ gap: 8 }}>
          <p style={{ fontSize: 17 }}>
            <strong>Your level: {stars(lv.stars)}</strong>
          </p>
          <p className="muted">
            {lv.override ? "Set by you." : `Detected from your ${lv.recent_n} most recent replays (last 30 days).`} Replays from{" "}
            {(lv.stars - lv.band).toFixed(1)} to {(lv.stars + lv.band).toFixed(1)}★ count fully; the further a play's star rating
            (with mods, e.g. DT) is from your level, the less it counts. So a warm-up on an easy map or a 9★ map for fun doesn't
            distort your numbers: your {lv.replays} replays count as {fmt(lv.weighted_replays, 1)}.
          </p>
          <div className="grow" />
          <div className="controls">
            <Switch
              checked={byHand}
              disabled={patch.isPending}
              label="Set my level by hand"
              hint="If the detected level is off (e.g. you only played easy maps lately). Type a level and press Apply: every number is recalculated with it."
              onChange={(on) => {
                setByHand(on);
                setDraft(null);
                setDone(null);
                if (!on && applied !== null) apply(null);
              }}
            />
            {byHand ? (
              <form
                className="apply-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (changed && !patch.isPending) apply(value);
                }}
              >
                <input
                  className="input"
                  aria-label="My level (★)"
                  aria-invalid={value === null}
                  type="number"
                  min={1}
                  max={12}
                  step={0.1}
                  value={draft}
                  onChange={(e) => {
                    setDraft(e.target.value);
                    setDone(null);
                  }}
                />
                <button type="submit" className="btn btn--primary" disabled={!changed || patch.isPending}>
                  Apply
                </button>
              </form>
            ) : (
              lv.detected !== null && <span className="muted small">Detected: {stars(lv.detected)}</span>
            )}
          </div>
          <p className={`apply-status${tone}`} role="status">
            {status}
          </p>
        </div>
        <Tiles n={4}>
          {lv.weights.slice(0, 4).map((w) => (
            <Stat
              key={w.stars_off}
              label={`${w.stars_off}★ off`}
              value={w.weight >= 0.005 ? pct(w.weight, 0) : "~0%"}
              note="counts"
            />
          ))}
        </Tiles>
      </div>
    </Card>
  );
}

/** The comfort-level scores moved to a star rating picked within 2★ of comfort (one star above first): lower on
 * harder maps, by how much more their typical maps demand of each skill, with the chance to pass one cleanly. */
function CompareCard({
  compare,
  skills,
  help,
  height,
}: {
  compare: Schemas["StarCompare"];
  skills: Schemas["SkillScore"][];
  help?: Schemas["SkillMeta"][];
  height: number;
}) {
  const [picked, setPicked] = useState<number | null>(null);
  const options = useMemo(() => targetOptions(compare), [compare]);
  const target = pickTarget(compare, picked);
  const comfort = compare.comfort ?? 0;
  const build = useCallback(
    (t: ChartTheme) => (target ? compareBars(skills, target, comfort, t, help ?? []) : {}),
    [skills, target, comfort, help],
  );
  const weakest = target?.skills.find((k) => k.key === target.weakest);
  const weakestLabel = skills.find((s) => s.key === target?.weakest)?.label;
  return (
    <Card
      title="Compare with other star ratings"
      sub={`Your comfort-level scores (above) on easier and harder maps. Harder maps demand more of every skill, so the scores drop, each by how much more typical maps of that star rating demand of it (measured on ranked maps). You can compare up to ${starLabel(compare.max_gap)} either side of your comfort level.`}
    >
      {target === null || compare.comfort === null ? (
        <Alert>Your comfort level isn't known yet: analyse at least 3 recent maps you finished cleanly.</Alert>
      ) : (
        <div className="stack" style={{ gap: 14 }}>
          <StarPicker label="Compare with" options={options} value={target.stars} onChange={setPicked} />
          <p>
            {target.comfort ? "At your comfort level" : `On typical ${starLabel(target.stars)} maps (${fromComfort(target.stars, comfort)})`}: about{" "}
            <b>{chanceLabel(target.pass_chance)}</b> chance to pass one cleanly (completed, at most 2 misses per 100 notes).
            {weakestLabel && weakest?.score !== null && weakest?.score !== undefined ? (
              <>
                {" "}
                Your weakest skill there: {weakestLabel.toLowerCase()} ({weakest.score.toFixed(0)}).
              </>
            ) : null}
          </p>
          <Chart build={build} height={height} label={`Skill scores at ${starLabel(target.stars)}`} />
        </div>
      )}
    </Card>
  );
}

function StrengthsCard({ ov }: { ov: Overview }) {
  const rs = ov.reading_split;
  return (
    <Card title="Strengths & weaknesses" sub="Your three best skills (score ≥ 55) and up to three to work on (≤ 45).">
      <div className="split">
        <div className="stack" style={{ gap: 8 }}>
          <Badge tone="good">Strong</Badge>
          {ov.strengths.length ? (
            <ul className="list list--bullets">{ov.strengths.map((s) => <li key={s}>{s}</li>)}</ul>
          ) : (
            <p className="muted">not clear yet</p>
          )}
        </div>
        <div className="stack" style={{ gap: 8 }}>
          <Badge tone="bad">Work on</Badge>
          {ov.weaknesses.length ? (
            <ul className="list list--bullets">{ov.weaknesses.map((s) => <li key={s}>{s}</li>)}</ul>
          ) : (
            <p className="muted">not clear yet</p>
          )}
        </div>
      </div>
      <div className="section">
        <h3 className="section__title">Reading by approach rate</h3>
        <Tiles n={2}>
          <Stat label="Low AR (<8)" value={fmt(rs.low_ar_score, 0)} note={`${rs.low_ar_maps} maps`} />
          <Stat label="High AR (10+)" value={fmt(rs.high_ar_score, 0)} note={`${rs.high_ar_maps} maps`} />
        </Tiles>
      </div>
      {ov.stamina.length > 0 && (
        <div className="section">
          <h3 className="section__title">Stamina: the tempo you kept up</h3>
          <p className="small muted">
            Not a miss count: how long you keep a high tempo while still pressing 90%+ of the notes — overstreaming never counts
            against you. {ov.stamina.map((s) => `${span(s.seconds)}: ${s.bpm.toFixed(0)} BPM (typical ${fmt(s.typical, 0)})`).join(" · ")}.
          </p>
        </div>
      )}
      {(ov.sliders_scored || ov.few_data.length > 0) && (
        <p className="small muted">
          {ov.sliders_scored &&
            "Slider control counts how hard the sliders are that you follow to the end: speed, length, shape, speed changes and how soon the next note follows. "}
          {ov.few_data.length > 0 &&
            `Unmeasured (${ov.few_data.join(", ")}): comfort, relevant map coverage, or tested challenge is insufficient.`}
        </p>
      )}
    </Card>
  );
}

function TopTips({ tips }: { tips: Schemas["TipOut"][] }) {
  if (!tips.length) return <Alert tone="good">No clear problems found in these replays. Keep playing and re-analyse later.</Alert>;
  return (
    <Card
      title="Top tips"
      sub={
        <>
          The most important tips; all of them, with what to do, are on <Link to="/tips">Tips & Setup</Link>.
        </>
      }
    >
      <Tiles n={tips.length as TileCount}>
        {tips.map((t) => (
          <div key={t.title} className="mini">
            <span className="mini__title">{t.title}</span>
            <span className="small muted">{t.category}</span>
            <p className="muted">{t.evidence}</p>
          </div>
        ))}
      </Tiles>
    </Card>
  );
}
