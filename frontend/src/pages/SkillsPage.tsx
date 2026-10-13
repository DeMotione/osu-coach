import { useCallback, useMemo, useState } from "react";
import { useSearchParams } from "react-router";

import type { Schemas } from "../api/client";
import { useAddGoal, useAddPlan, useGoals, usePatchSettings, usePlaylist, useRemoveGoal, useSettings } from "../api/queries";
import { Chart } from "../charts/Chart";
import type { ChartTheme } from "../charts/palette";
import { goalsChart } from "../charts/progress";
import { ExportPanel } from "../components/ExportPanel";
import { IconPlus, IconTrash } from "../components/icons";
import { MapTable } from "../components/MapTable";
import { EmptyState, ErrorCard, LoadingPage } from "../components/states";
import { Alert, Badge, Card, Field, Page, Progress, Row, Stat, Tabs, Tiles } from "../components/ui";
import { fmt, isoDay } from "../lib/format";
import { useDebouncedEffect } from "../lib/hooks";

type Tab = "goals" | "playlist";

export default function SkillsPage() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("tab") === "playlist" ? "playlist" : "goals";
  return (
    <Page title="Skill Development" sub="Set goals for your skills and follow them, and get a staged playlist (warm-up / core / push) for any skill.">
      <Tabs
        tabs={[
          { value: "goals", label: "Training plan & goals" },
          { value: "playlist", label: "Playlist for a skill" },
        ]}
        value={tab}
        onChange={(t) => setParams(t === "goals" ? {} : { tab: t })}
      />
      {tab === "goals" ? <GoalsTab /> : <PlaylistTab />}
    </Page>
  );
}

// ------------------------------------------------------------------ goals
const STATE: Record<Schemas["GoalOut"]["state"], ["good" | "info" | "warn" | "bad" | "muted", string]> = {
  done: ["good", "reached"],
  "on track": ["good", "on track"],
  behind: ["warn", "behind"],
  overdue: ["bad", "overdue"],
  "no data": ["muted", "no data"],
};

function GoalsTab() {
  const q = useGoals();
  if (q.isPending) return <LoadingPage tiles={3} />;
  if (q.error) return <ErrorCard error={q.error} onRetry={() => void q.refetch()} />;
  const g = q.data;
  return (
    <>
      <Tiles n={3}>
        <Stat label="Open goals" value={g.open.length} />
        <Stat label="Reached" value={g.done.length} />
        <Stat label="Behind or overdue" value={g.behind} />
      </Tiles>
      <Card title="Your goals" sub="Each goal: a skill score to reach by a date. On track = you are at least as far as the time that has passed.">
        {g.open.length ? (
          <div className="stack">{g.open.map((x) => <GoalRow key={x.id} goal={x} />)}</div>
        ) : (
          <EmptyState title="No open goals yet">Add one below or make a plan from your weakest skills.</EmptyState>
        )}
      </Card>
      {g.history.length > 0 && <HistoryCard history={g.history} />}
      <Row>
        <AddGoalCard goals={g} />
        <PlanCard goals={g} />
      </Row>
      {g.done.length > 0 && (
        <Card title="Reached goals">
          <ul className="list list--bullets">
            {g.done.map((x) => (
              <li key={x.id}>
                <strong>{x.label}</strong> {fmt(x.start, 0)} → {x.target.toFixed(0)}, reached {x.done} (set {x.created})
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}

function GoalRow({ goal }: { goal: Schemas["GoalOut"] }) {
  const remove = useRemoveGoal();
  const [tone, word] = STATE[goal.state];
  return (
    <div className="goal">
      <div className="stack" style={{ gap: 4 }}>
        <span className="goal__title">
          {goal.label}: {fmt(goal.start, 0)} → {goal.target.toFixed(0)} by {goal.deadline} · now {fmt(goal.current, 0)}{" "}
          <Badge tone={tone}>{word}</Badge>
        </span>
        <span className="goal__meta">
          <span>{goal.days_left >= 0 ? `${goal.days_left} days left` : `${-goal.days_left} days overdue`}</span>
          {goal.left !== null && goal.left > 0 && <span>{goal.left.toFixed(0)} points to go</span>}
        </span>
      </div>
      <button type="button" className="btn btn--ghost btn--sm btn--danger" onClick={() => remove.mutate(goal.id)} disabled={remove.isPending}>
        <IconTrash /> Remove
      </button>
      <Progress value={goal.progress} text={`${Math.round(goal.progress * 100)}% of the way`} />
    </div>
  );
}

function HistoryCard({ history }: { history: Schemas["GoalHistory"][] }) {
  const build = useCallback((t: ChartTheme) => goalsChart(history, t), [history]);
  return (
    <Card
      title="Goal skills day by day"
      sub="Solid lines: your score each day you analysed replays; dotted: the path from where you started to the target by the deadline. Above the dotted line = ahead of plan."
    >
      <Chart build={build} height={320} label="Goal skills day by day" />
    </Card>
  );
}

function AddGoalCard({ goals }: { goals: Schemas["GoalsOut"] }) {
  const add = useAddGoal();
  const [skill, setSkill] = useState<string | null>(null);
  const [target, setTarget] = useState<string>("");
  const [deadline, setDeadline] = useState(isoDay(28));
  const chosen = goals.skills.find((s) => s.key === skill) ?? goals.skills[0];
  const tgt = target === "" && chosen ? String(Math.min(100, Math.round(chosen.score + 10))) : target;
  if (!goals.has_profile || !chosen)
    return (
      <Card title="Add a goal">
        <EmptyState title="Analyse your replays first">Goals follow your skill scores.</EmptyState>
      </Card>
    );
  return (
    <Card title="Add a goal" sub="A skill, the score to reach and by when.">
      <Field label="Skill">
        <select className="select" value={chosen.key} onChange={(e) => (setSkill(e.target.value), setTarget(""))}>
          {goals.skills.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label} · now {s.score.toFixed(0)}
            </option>
          ))}
        </select>
      </Field>
      <div className="split">
        <Field label="Target score">
          <input className="input" type="number" min={1} max={100} value={tgt} onChange={(e) => setTarget(e.target.value)} />
        </Field>
        <Field label="By">
          <input className="input" type="date" min={isoDay()} value={deadline} onChange={(e) => setDeadline(e.target.value)} />
        </Field>
      </div>
      {add.isError && <Alert tone="bad">{add.error.message}</Alert>}
      <div className="grow" />
      <button
        type="button"
        className="btn btn--primary btn--block"
        disabled={add.isPending || !tgt || !deadline}
        onClick={() => add.mutate({ skill: chosen.key, target: Number(tgt), deadline }, { onSuccess: () => setTarget("") })}
      >
        <IconPlus /> Add
      </button>
    </Card>
  );
}

function PlanCard({ goals }: { goals: Schemas["GoalsOut"] }) {
  const plan = useAddPlan();
  return (
    <Card title="A 4-week plan" sub="Your 3 weakest skills, each with a target 10 points higher.">
      {goals.suggested.length ? (
        <ul className="list">
          {goals.suggested.map((s) => (
            <li key={s.skill} className="mini">
              <span className="mini__title">
                {s.label}: {s.current.toFixed(0)} → {s.target.toFixed(0)}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState title="No scored skills yet" />
      )}
      {goals.weak_without_goal.length > 0 && (
        <p className="small muted">
          Still below your level and without a goal: {goals.weak_without_goal.map((s) => `${s.label} (${s.score.toFixed(0)})`).join(", ")}.
        </p>
      )}
      {plan.isError && <Alert tone="bad">{plan.error.message}</Alert>}
      <div className="grow" />
      <button type="button" className="btn btn--block" disabled={!goals.suggested.length || plan.isPending} onClick={() => plan.mutate()}>
        Make this plan
      </button>
    </Card>
  );
}

// ------------------------------------------------------------------ playlist
function PlaylistTab() {
  const settings = useSettings();
  const patch = usePatchSettings();
  const [skill, setSkill] = useState<string | undefined>(undefined);
  const [maps, setMaps] = useState(15);
  const [comfortText, setComfortText] = useState<string | null>(null);
  const saved = settings.data?.manual_comfort ?? 2.5;
  const comfort = comfortText !== null && Number.isFinite(Number(comfortText)) ? Number(comfortText) : saved;
  const q = usePlaylist({ skill, maps, comfort: Math.min(8, Math.max(1, comfort)) });
  useDebouncedEffect(comfortText, 600, (v) => {
    const n = Number(v);
    if (v !== null && n >= 1 && n <= 8) patch.mutate({ manual_comfort: n });
  });
  const pl = q.data;
  const all = useMemo(() => pl?.stages.flatMap((s) => s.maps) ?? [], [pl]);

  if (q.isPending) return <LoadingPage tiles={2} />;
  if (q.error && !pl) return <ErrorCard error={q.error} onRetry={() => void q.refetch()} />;
  if (!pl) return null;
  return (
    <>
      <Card>
        {!pl.has_profile && <Alert tone="info">No replays analysed yet — set your level by hand, or analyse replays for a personal playlist.</Alert>}
        <div className="controls">
          <Field label="Skill">
            <select className="select" value={pl.skill} onChange={(e) => setSkill(e.target.value)}>
              {pl.skills.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                  {s.score !== null ? ` · your score ${s.score.toFixed(0)}` : ""}
                </option>
              ))}
            </select>
          </Field>
          <Field label={`Maps: ${maps}`}>
            <input type="range" min={6} max={30} step={3} value={maps} onChange={(e) => setMaps(Number(e.target.value))} />
          </Field>
          {!pl.has_profile && (
            <Field label="Star rating you can pass comfortably">
              <input
                className="input"
                type="number"
                min={1}
                max={8}
                step={0.1}
                value={comfortText ?? String(saved)}
                onChange={(e) => setComfortText(e.target.value)}
              />
            </Field>
          )}
        </div>
        <p className="muted">
          Your level ≈ <strong>{pl.comfort.toFixed(1)}★</strong>
          {(pl.skill === "speed" || pl.skill === "stamina") && pl.stream_bpm ? (
            <>
              {" "}
              · stream target ≈ <strong>{pl.stream_bpm.toFixed(0)} BPM</strong>
            </>
          ) : null}{" "}
          · collection name: <code>{pl.collection_name}</code>
        </p>
      </Card>
      {pl.stages.length ? (
        pl.stages.map((st) => (
          <Card key={st.stage} title={st.stage} sub={st.goal}>
            <MapTable maps={st.maps} />
          </Card>
        ))
      ) : (
        <Alert tone="warn">No maps found for this skill at your level.</Alert>
      )}
      {all.length > 0 && (
        <ExportPanel
          maps={all}
          name={pl.collection_name}
          preferred={pl.preferred_client}
          title="Get the playlist into osu!"
          sub="lazer: one folder to import maps and collection; stable: add the collection and download the maps."
        />
      )}
    </>
  );
}
