import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { api, unwrap, type Schemas } from "../api/client";
import { useJob } from "../api/jobs";
import { uploadFiles, useCheckReplays, usePlayGoalOptions } from "../api/queries";
import { ExportPanel } from "../components/ExportPanel";
import { EmptyState, ErrorCard, JobStatus, LoadingPage } from "../components/states";
import { Alert, Badge, Card, Dropzone, Field, Page, Switch, Tabs } from "../components/ui";
import { clock, fmt, pct, stars } from "../lib/format";
import { exportGoalMaps, GOAL_MODS, goalRequest } from "../lib/playGoals";

type Request = Schemas["PlayGoalRequest"];
type Result = Schemas["PlayGoalResult"];
type Accuracy = Schemas["AccuracyEstimate"];
type Goal = Request["goal"];

export default function PlayGoalsPage() {
  const [params, setParams] = useSearchParams();
  const options = usePlayGoalOptions();
  const value = params.get("tab");
  const goal: Goal = value === "farm" || value === "mod" ? value : "fc";
  return (
    <Page title="Play Goals">
      <Tabs
        tabs={[{ value: "fc", label: "FC a map" }, { value: "farm", label: "Farm PP" }, { value: "mod", label: "Improve a mod" }]}
        value={goal}
        onChange={(tab) => setParams({ tab })}
      />
      {options.isPending ? <LoadingPage tiles={2} /> : options.error ? (
        <ErrorCard error={options.error} onRetry={() => void options.refetch()} />
      ) : (
        <GoalForm key={params.toString()} goal={goal} options={options.data} path={params.get("path")} beatmap={params.get("beatmap")} client={params.get("client")} mods={params.get("mods")} />
      )}
    </Page>
  );
}

function GoalForm({ goal, options, path, beatmap, client, mods }: {
  goal: Goal; options: Schemas["PlayGoalOptions"]; path: string | null; beatmap: string | null; client: string | null; mods: string | null;
}) {
  const [request, setRequest] = useState<Request>(() => {
    const targetMods = GOAL_MODS.find((m) => m === mods?.replaceAll("NC", "DT"));
    return {
      ...goalRequest(goal, options.last_request),
      ...(path ? { replay_path: path, beatmap: null } : {}),
      ...(beatmap && !path ? { beatmap, replay_path: null } : {}),
      ...(client === "lazer" || client === "stable" ? { client } : {}),
      ...(targetMods ? { mods: targetMods } : {}),
    };
  });
  const job = useJob("play_goal");
  const result = job.job?.kind === "play_goal" && job.job.status === "succeeded" && job.job.result?.request.goal === goal
    ? job.job.result : null;
  const update = (patch: Partial<Request>) => setRequest((previous) => ({ ...previous, ...patch }));
  const { run } = job;

  useEffect(() => {
    if (result && result.evidence_revision !== options.evidence_revision) {
      void run(() => unwrap(api.POST("/api/play-goals", { body: result.request })));
    }
  }, [result, options.evidence_revision, run]);

  const submit = () => void run(() => unwrap(api.POST("/api/play-goals", { body: request })));
  const invalid = goal === "fc" && !request.replay_path && !request.beatmap?.trim();
  return (
    <>
      <Card
        title={goal === "fc" ? "What is stopping your FC?" : goal === "farm" ? "Find a score worth going for" : "Get comfortable with your mod"}
        hint={goal === "fc" ? "Choose a specific difficulty and target configuration. Your attempts identify the blockers." :
          goal === "farm" ? "Local map PP scenarios, not promised account PP gains." : "Choose HD or standard 1.5x DT. Get easier maps and concrete objectives."}
      >
        <p>{options.player ? `Player: ${options.player}. ` : "No single player selected. "}
          {options.evidence_plays} analysed replays; {options.coverage_maps} difficulties in the offline goal pool.{" "}
          <Link to="/replays">Manage replay evidence</Link>
        </p>
        {goal === "fc" && <TargetPicker request={request} update={update} />}
        <div className="controls">
          <Field label="osu! client">
            <select className="select" value={request.client} onChange={(e) => update({ client: e.target.value === "lazer" ? "lazer" : "stable" })}>
              <option value="stable">osu!stable</option><option value="lazer">osu!lazer</option>
            </select>
          </Field>
          {goal === "fc" && (
            <Field label="Target mods">
              <select className="select" value={request.mods} onChange={(e) => {
                const mods = GOAL_MODS.find((m) => m === e.target.value);
                if (mods) update({ mods });
              }}>{GOAL_MODS.map((m) => <option key={m} value={m}>{m}</option>)}</select>
            </Field>
          )}
          {goal === "mod" && (
            <Field label="Training mod">
              <select className="select" value={request.training_mod} onChange={(e) => update({ training_mod: e.target.value === "DT" ? "DT" : "HD" })}>
                <option value="HD">HD - Hidden</option><option value="DT">DT - Double Time (1.5x)</option>
              </select>
            </Field>
          )}
        </div>
        {goal === "farm" && (
          <fieldset>
            <legend>Allowed farming mods</legend>
            <div className="controls">
              {GOAL_MODS.map((m) => (
                <Switch key={m} label={m} checked={request.farm_mods?.includes(m) ?? false} onChange={(checked) => {
                  const mods = request.farm_mods ?? [];
                  update({ farm_mods: checked ? [...mods, m] : mods.filter((v) => v !== m) });
                }} />
              ))}
            </div>
          </fieldset>
        )}
        <div className="controls">
          <Switch label="Allow missing target beatmap downloads" checked={request.online ?? true} onChange={(online) => update({ online })} />
          <button type="button" className="btn btn--primary" disabled={job.running || invalid || !request.farm_mods?.length} onClick={submit}>
            {goal === "fc" ? "Assess my FC goal" : goal === "farm" ? "Find PP plays" : "Find training maps"}
          </button>
        </div>
        <JobStatus job={job.job} error={job.error} onCancel={() => void job.cancel()} />
      </Card>
      {result ? (
        <>
          {JSON.stringify(result.request) !== JSON.stringify(request) && <Alert tone="info">These results use the last submitted choices. Submit again to apply your changes.</Alert>}
          <GoalResults key={job.job?.id} result={result} />
        </>
      ) : !job.running && !job.job && (
        <Card><EmptyState title="Pick a goal, get your next plays">No more guessing what to grind. Start with one of the three goals above.</EmptyState></Card>
      )}
    </>
  );
}

function TargetPicker({ request, update }: { request: Request; update: (patch: Partial<Request>) => void }) {
  const replays = useCheckReplays(request.replay_path ?? null, false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [source, setSource] = useState<"replay" | "beatmap">(request.beatmap ? "beatmap" : "replay");
  return (
    <>
      <Field label="Target source">
        <select className="select" value={source} onChange={(e) => {
          setSource(e.target.value === "beatmap" ? "beatmap" : "replay");
          update({ replay_path: null, beatmap: null });
        }}>
          <option value="replay">A replay of this map</option><option value="beatmap">Beatmap difficulty URL or ID</option>
        </select>
      </Field>
      {source === "beatmap" ? (
        <Field label="Beatmap difficulty">
          <input className="input" placeholder="https://osu.ppy.sh/beatmapsets/123#osu/456 or 456" value={request.beatmap ?? ""}
            onChange={(e) => update({ beatmap: e.target.value, replay_path: null })} />
        </Field>
      ) : (
        <>
          <Field label="Replay for the FC target">
            <select className="select" value={request.replay_path ?? ""} onChange={(e) => {
              const picked = replays.data?.replays.find((r) => r.path === e.target.value);
              const mods = GOAL_MODS.find((m) => m === picked?.mods.replaceAll("NC", "DT"));
              update({ replay_path: e.target.value || null, beatmap: null, ...(mods ? { mods } : {}) });
            }}>
              <option value="">Choose a replay</option>
              {replays.data?.replays.map((r) => <option key={r.path} value={r.path} disabled={!r.analysable}>{r.map} +{r.mods} - {r.player}</option>)}
            </select>
          </Field>
          {replays.error && <Alert tone="bad">{replays.error.message}</Alert>}
          <Dropzone accept=".osr" multiple={false} title="Or drop your replay" help="Export an .osr from your results screen."
            onFiles={async (files) => {
              setUploadError(null);
              try {
                const uploaded = await uploadFiles(files);
                if (uploaded[0]) update({ replay_path: uploaded[0].path, beatmap: null });
              } catch (error) {
                setUploadError(error instanceof Error ? error.message : String(error));
              }
            }} />
          {uploadError && <Alert tone="bad">{uploadError}</Alert>}
        </>
      )}
    </>
  );
}

function AccuracyRange({ value }: { value: Accuracy | null | undefined }) {
  return value ? (
    <div>
      <strong>Estimated accuracy: {pct(value.low, 1)} - {pct(value.high, 1)}</strong>
      <p className="small muted">{value.plays} comparable plays across {value.maps} maps. {value.explanation}</p>
    </div>
  ) : <p className="muted">Estimated accuracy: insufficient comparable evidence.</p>;
}

function GoalResults({ result }: { result: Result }) {
  const [page, setPage] = useState(0);
  const recommendations = result.recommendations.slice(page * 5, (page + 1) * 5);
  const maps = exportGoalMaps(recommendations);
  return (
    <>
      <Card title={result.verdict}>
        <p><Badge tone={result.confidence === "unassessed" ? "muted" : "info"}>{result.confidence} evidence</Badge>
          {result.player ? ` ${result.player}` : " No measured player profile"}
        </p>
        {result.target && <p><strong>{result.target.artist} - {result.target.title} [{result.target.version}]</strong>{" "}
          +{result.target.mods} / osu!{result.target.client} / {stars(result.target.stars)}</p>}
        <ul className="list list--bullets">{result.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
        {result.request.goal === "fc" && <AccuracyRange value={result.accuracy} />}
        {result.replay_path && <Link className="btn btn--sm" to={`/check?path=${encodeURIComponent(result.replay_path)}`}>Open detailed map analysis</Link>}
      </Card>
      {result.blockers.length > 0 && (
        <Card title="What to work on for this map">
          <ul className="list">
            {result.blockers.map((b) => <li key={b.skill}>
              <strong>{b.title}</strong> <Badge tone={b.observed ? "info" : "muted"}>{b.observed ? "Observed in attempts" : "Inferred demand"}</Badge>
              <p>{b.detail}</p>
              {b.timestamps.length > 0 && <p>Practise around: {b.timestamps.join(", ")}</p>}
            </li>)}
          </ul>
        </Card>
      )}
      <Card title="Your next plays" hint="Useful repeats are allowed. A pass is not an FC, and different mods are a different challenge.">
        {recommendations.length ? <div className="stack">
          {recommendations.map((r) => <article key={`${r.map.md5}:${r.map.mods}`}>
            <h3><a href={`https://osu.ppy.sh/beatmaps/${r.map.beatmap_id}`} target="_blank" rel="noreferrer noopener">
              {r.map.artist} - {r.map.title} [{r.map.version}]
            </a></h3>
            <p><Badge tone="info">+{r.map.mods}</Badge> {r.stage} / {stars(r.map.stars)} / {fmt(r.map.bpm, 0)} BPM /
              AR {fmt(r.map.ar, 1)} / OD {fmt(r.map.od, 1)} / {clock(r.map.length_s)} / osu!{r.map.client}</p>
            <p>{r.why}</p>
            <p><strong>Play target: {pct(r.practice_accuracy, 0)}</strong> - {r.objective}</p>
            <AccuracyRange value={r.accuracy} />
            {result.request.goal === "farm" && r.pp !== null && <p>{r.pp_label}: <strong>{fmt(r.pp, 1)} PP</strong> at {pct(r.pp_accuracy, 0)}, full combo, no misses.
              All slider ticks/tails hit; conservative generated hit-result distribution.</p>}
            {r.local_best_accuracy !== null && <p>Local best completed accuracy: {pct(r.local_best_accuracy, 2)}{r.achieved ? " - this practice objective was already achieved." : ""}</p>}
            <p className="small muted">{r.step_up}</p>
          </article>)}
          <div className="controls">
            <button type="button" className="btn btn--sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Previous five</button>
            <span>{page * 5 + 1}-{Math.min((page + 1) * 5, result.recommendations.length)} of {result.recommendations.length}</span>
            <button type="button" className="btn btn--sm" disabled={(page + 1) * 5 >= result.recommendations.length} onClick={() => setPage((p) => p + 1)}>Next five</button>
          </div>
        </div> : <EmptyState title="No suitable covered maps">Try another supported mod or analyse more replays. The app will not fill this list with unrelated maps.</EmptyState>}
      </Card>
      {maps.length > 0 && (
        <ExportPanel maps={maps} name={`osu-coach: ${result.request.goal} ${[...new Set(recommendations.map((r) => `+${r.map.mods}`))].join(" ")}`}
          preferred={result.request.client ?? "stable"} title="Get these maps into osu!"
          sub="Collections import maps, not mods. Set the listed mods manually; the text map list retains your play objectives." />
      )}
      {result.warnings.length > 0 && <Card title="Evidence and limitations"><ul className="list list--bullets">
        {result.warnings.map((warning) => <li key={warning}>{warning}</li>)}
      </ul></Card>}
    </>
  );
}
