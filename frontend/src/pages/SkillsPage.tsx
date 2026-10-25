import { useCallback, useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";

import type { Schemas } from "../api/client";
import { useAddPlan, useGoals, usePlaylist, useRemoveGoal } from "../api/queries";
import { Chart } from "../charts/Chart";
import type { ChartTheme } from "../charts/palette";
import { goalsChart } from "../charts/progress";
import { AddGoal } from "../components/AddGoalDialog";
import { ExportPanel } from "../components/ExportPanel";
import { IconRefresh, IconTrash } from "../components/icons";
import { MapTable } from "../components/MapTable";
import { RecommendationControls, type RecommendationOptions } from "../components/RecommendationControls";
import { EmptyState, ErrorCard, LoadingPage } from "../components/states";
import { Alert, Badge, Card, Page, Progress, Stat, Tabs, Tiles } from "../components/ui";
import { fmt } from "../lib/format";
import { STAGE_SIZE, stageMaps } from "../lib/playlist";
import { speedFitNotice } from "../lib/recommendationFit";

type Tab = "goals" | "playlist";

export default function SkillsPage() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("tab") === "playlist" ? "playlist" : "goals";
  return (
    <Page title="Goals & Training">
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
  paused: ["muted", "paused · previous accuracy scale"],
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
      <Card
        title="Your goals"
        hint="Each goal: a skill score to reach by a date. On track = you are at least as far as the time that has passed."
        foot={g.history.length ? undefined : <AddGoal goals={g} />}
      >
        {g.open.length ? (
          <div className="stack">{g.open.map((x) => <GoalRow key={x.id} goal={x} />)}</div>
        ) : (
          <EmptyState title="No open goals yet">Add one below or make a plan from your weakest skills.</EmptyState>
        )}
      </Card>
      {g.history.length > 0 && <HistoryCard history={g.history} foot={<AddGoal goals={g} />} />}
      <PlanCard goals={g} />
      {g.done.length > 0 && (
        <Card title="Reached goals">
          <ul className="list list--bullets">
            {g.done.map((x) => (
              <li key={x.id}>
                <strong>{x.label}</strong> {fmt(x.start, 0)} → {x.target.toFixed(0)}, reached {x.done} (set {x.created})
                {x.score_source === "legacy" && " · previous rating scale"}
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
  const [tone, stateWord] = STATE[goal.state];
  // set before 0.10: those scores can't be compared with today's, so the goal isn't followed any more (#70)
  const oldScale = goal.score_source === "legacy";
  const word = goal.state === "paused" && oldScale ? "paused · previous rating scale" : stateWord;
  return (
    <div className="goal">
      <div className="stack" style={{ gap: 4 }}>
        <span className="goal__title">
          {goal.label}: {fmt(goal.start, 0)} → {goal.target.toFixed(0)} by {goal.deadline}
          {goal.state !== "paused" && ` · now ${fmt(goal.current, 0)}`} {" "}
          <Badge tone={tone}>{word}</Badge>
        </span>
        <span className="goal__meta">
          <span>{goal.state === "paused" ? `Original deadline ${goal.deadline}` : goal.days_left >= 0 ? `${goal.days_left} days left` : `${-goal.days_left} days overdue`}</span>
          {goal.left !== null && goal.left > 0 && <span>{goal.left.toFixed(0)} points to go</span>}
          {goal.state === "paused" &&
            (oldScale ? (
              <span>Set on the previous rating scale, which no longer matches your scores. Add a new goal to follow this skill.</span>
            ) : (
              <span>Create a new goal to track the recalibrated score.</span>
            ))}
          {oldScale && goal.state !== "paused" && <span>Previous rating scale</span>}
        </span>
      </div>
      <button type="button" className="btn btn--ghost btn--sm btn--danger" onClick={() => remove.mutate(goal.id)} disabled={remove.isPending}>
        <IconTrash /> Remove
      </button>
      {goal.progress !== null && <Progress value={goal.progress} text={`${Math.round(goal.progress * 100)}% of the way`} />}
    </div>
  );
}

function HistoryCard({ history, foot }: { history: Schemas["GoalHistory"][]; foot: ReactNode }) {
  const build = useCallback((t: ChartTheme) => goalsChart(history, t), [history]);
  return (
    <Card
      title="Goal skills day by day"
      hint="Goals on the current rating scale. Solid lines: your score over the plays of the last 7 days, on each day you played; dotted: the path from where you started to the target by the deadline. Above the dotted line = ahead of plan."
      foot={foot}
    >
      <Chart build={build} height={320} label="Goal skills day by day" />
    </Card>
  );
}

function PlanCard({ goals }: { goals: Schemas["GoalsOut"] }) {
  const plan = useAddPlan();
  return (
    <Card title="A 4-week plan" hint="Up to 3 measured skills below your comfort level, each with a target 10 points higher.">
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
        <EmptyState title={goals.skills.length ? "No measured weak skills without a goal" : "No measured skill ratings yet"} />
      )}
      {goals.weak_without_goal.length > 0 && (
        <p className="small muted">
          Still below your level and without a goal: {goals.weak_without_goal.map((s) => `${s.label} (${s.score.toFixed(0)})`).join(", ")}.
        </p>
      )}
      {plan.isError && <Alert tone="bad">{plan.error.message}</Alert>}
      <div className="grow" />
      <button type="button" className="btn" disabled={!goals.suggested.length || plan.isPending} onClick={() => plan.mutate()}>
        Make this plan
      </button>
    </Card>
  );
}

// ------------------------------------------------------------------ playlist
function PlaylistTab() {
  const [options, setOptions] = useState<RecommendationOptions>({});
  const q = usePlaylist(options);
  const pl = q.data;
  // which group of five each stage shows; a new playlist starts again with the best ones
  const [rounds, setRounds] = useState<{ of?: typeof pl; by: Record<string, number> }>({ by: {} });
  if (rounds.of !== pl) setRounds({ of: pl, by: {} });
  const shown = useMemo(
    () => new Map((pl?.stages ?? []).map((st) => [st.stage, stageMaps(st.maps, rounds.by[st.stage] ?? 0)])),
    [pl, rounds],
  );
  // the export takes the maps on screen: five per stage
  const all = useMemo(
    () => [...new Map([...shown.values()].flatMap((s) => s.maps).map((m) => [m.md5, m])).values()],
    [shown],
  );
  const next = (stage: string) => setRounds((r) => ({ ...r, by: { ...r.by, [stage]: (r.by[stage] ?? 0) + 1 } }));

  if (q.isPending) return <LoadingPage tiles={2} />;
  if (q.error && !pl) return <ErrorCard error={q.error} onRetry={() => void q.refetch()} />;
  if (!pl) return null;
  return (
    <>
      <RecommendationControls current={pl.skill} measured={pl.measured_abilities ?? {}} comfort={pl.comfort} onApply={setOptions} />
      <Card>
        {!pl.has_profile && <Alert tone="info">No replays analysed yet — enter comfort stars and player ratings to get a personal playlist.</Alert>}
        <p className="muted">
          Your comfort level ≈ <strong>{pl.comfort.toFixed(1)}★</strong> ({pl.comfort_source})
          {(pl.skill === "speed" || pl.skill === "stamina") && pl.stream_bpm ? (
            <>
              {" "}
              · stream target ≈ <strong>{pl.stream_bpm.toFixed(0)} BPM</strong>
            </>
          ) : null}{" "}
          · collection name: <code>{pl.collection_name}</code>
        </p>
        <p className="small muted">Skill-adjusted target: {pl.skill_adjusted_stars?.toFixed(2) ?? "unknown"}★. Map demands and coefficients are experimental.</p>
      </Card>
      {pl.stages.length ? (
        pl.stages.map((st) => {
          const { maps, first } = shown.get(st.stage) ?? { maps: [], first: 0 };
          const fitNotice = pl.skill === "speed" ? speedFitNotice(maps, st.target_demand) : null;
          return (
            <Card
              key={st.stage}
              title={st.stage}
              hint={`${st.eligible} eligible · target ${st.target_stars?.toFixed(2) ?? "unknown"}★ · target demand ${st.target_demand?.toFixed(1) ?? "unknown"}`}
              actions={
                st.maps.length > STAGE_SIZE && (
                  <>
                    {/* which five of the stage's maps are shown: what Other maps moves on */}
                    <span className="small muted">
                      showing {first + 1}–{first + maps.length} of {st.maps.length}
                    </span>
                    <button type="button" className="btn btn--sm" title="Show the next five maps of this stage" onClick={() => next(st.stage)}>
                      <IconRefresh /> Other maps
                    </button>
                  </>
                )
              }
            >
              {fitNotice && <Alert tone="warn">{fitNotice}</Alert>}
              <MapTable key={`${st.stage}:${st.eligible}:${maps[0]?.md5 ?? ""}:${pl.skill_adjusted_stars}`} maps={maps} />
              {!st.eligible && <p className="small muted">{Object.entries(st.excluded ?? {}).map(([reason, count]) => `${reason}: ${count}`).join(" · ")}</p>}
            </Card>
          );
        })
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
