import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { api, unwrap, type Schemas } from "../api/client";
import { useJob } from "../api/jobs";
import { uploadFiles, useCheckReplays, usePlayGoalOptions } from "../api/queries";
import { Combobox } from "../components/Combobox";
import { DataTable, type Column } from "../components/DataTable";
import { ExportPanel } from "../components/ExportPanel";
import { ModPicker } from "../components/ModPicker";
import { StageNav } from "../components/StageNav";
import { EmptyState, ErrorCard, JobStatus, LoadingPage } from "../components/states";
import { Alert, Badge, Card, Dropzone, Field, Page, Segmented, Switch, Tabs } from "../components/ui";
import { clock, fmt, pct, stars } from "../lib/format";
import { bestReplays, exportGoalMaps, GOAL_MODS, goalRequest } from "../lib/playGoals";
import { STAGE_SIZE, stageMaps, useRounds } from "../lib/playlist";

type Request = Schemas["PlayGoalRequest"];
type Result = Schemas["PlayGoalResult"];
type Accuracy = Schemas["AccuracyEstimate"];
type Recommendation = Schemas["GoalRecommendation"];
type Goal = Request["goal"];

const PLAYS_TITLE: Record<Goal, string> = { fc: "Maps to practice", farm: "Maps to farm", mod: "Maps to train your mods" };

/** Why these maps: shown as the "?" next to the results title. */
const PICK_CRITERIA: Record<Goal, string> = {
  fc: "Maps with the target's mods that are at or a little below your level. Ranked by how much they train the skills you are weakest at on the target (or overall, with no attempts). Maps with much faster BPM or higher AR than you play are left out.",
  farm: "Maps with your chosen mods that are within reach of your level, best PP first. PP is for a full combo at the target accuracy.",
  mod: "Maps with the chosen mods that are easier than your normal level, so you can build control with that mod. Maps much faster or with higher AR than you play are left out.",
};

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
  const [editMods, setEditMods] = useState(false);
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
  const started = useRef(false);
  useEffect(() => {
    // Arriving from a map or replay link: the target is already chosen, so assess it right away.
    if (started.current || goal !== "fc" || !(path || beatmap)) return;
    started.current = true;
    void run(() => unwrap(api.POST("/api/play-goals", { body: request })));
  }, [goal, path, beatmap, request, run]);
  const invalid = goal === "fc" && !request.replay_path && !request.beatmap?.trim();
  return (
    <>
      <Card
        title={goal === "fc" ? "What is stopping your FC?" : goal === "farm" ? "Find a score worth going for" : "Get comfortable with your mod"}
        hint={goal === "fc" ? "Pick a difficulty and mods." :
          goal === "farm" ? "Local PP scenarios, not account PP." : "Pick a mod or combo."}
      >
        <p>{options.player ? `Player: ${options.player}. ` : "No player selected. "}
          {options.evidence_plays} analysed replays.{" "}
          <Link to="/replays">Manage replays</Link>
        </p>
        {goal === "fc" && <TargetPicker request={request} update={update} />}
        <div className="controls">
          {goal === "fc" && (request.replay_path && !editMods ? (
            <p>Mods: <strong>+{request.mods}</strong> (from your replay){" "}
              <button type="button" className="btn btn--sm" onClick={() => setEditMods(true)}>Change</button></p>
          ) : (
            <ModPicker label="Mods you want to FC with" allowNone value={request.mods}
              onChange={(mods) => update({ mods })} />
          ))}
          {goal === "mod" && (
            <ModPicker label="Training mods" value={request.training_mod}
              onChange={(mods) => update({ training_mod: mods as Request["training_mod"] })} />
          )}
        </div>
        {goal === "farm" && (
          <fieldset>
            <legend>Mod combinations to farm</legend>
            <FarmMods value={request.farm_mods ?? []} onChange={(farm_mods) => update({ farm_mods })} />
            <Field label="Minimum PP">
              <input className="input" type="number" min={0} max={5000} step={10} placeholder="Any" value={request.min_pp ?? ""}
                onChange={(e) => update({ min_pp: e.target.value === "" ? null : Math.max(0, Number(e.target.value)) })} />
            </Field>
          </fieldset>
        )}
        <div className="controls">
          <Switch label="Allow missing target beatmap downloads" checked={request.online ?? true} onChange={(online) => update({ online })} />
          <button type="button" className="btn btn--primary" disabled={job.running || invalid || !request.farm_mods?.length} onClick={submit}>
            {goal === "fc" ? "Assess my FC goal" : goal === "farm" ? "Find maps" : "Find training maps"}
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
        <Card><EmptyState title="Pick a goal, get maps to play">No more guessing what to grind. Start with one of the three goals above.</EmptyState></Card>
      )}
    </>
  );
}

function Choice<T extends string>({ label, value, options, onChange }: {
  label: string; value: T; options: { value: T; label: string }[]; onChange: (value: T) => void;
}) {
  return (
    <div className="field">
      <span className="field__label">{label}</span>
      <Segmented label={label} value={value} options={options} onChange={onChange} />
    </div>
  );
}

function FarmMods({ value, onChange }: { value: NonNullable<Request["farm_mods"]>; onChange: (value: NonNullable<Request["farm_mods"]>) => void }) {
  const [draft, setDraft] = useState<NonNullable<Request["mods"]>>("HD");
  return (
    <div className="stack">
      <div className="modpicker">
        {value.map((m) => (
          <button key={m} type="button" className="modpicker__chip" aria-pressed="true" title="Remove"
            onClick={() => onChange(value.filter((v) => v !== m))}>{m === "NM" ? "NM" : `+${m}`} ×</button>
        ))}
        {!value.length && <span className="muted">Add at least one combination.</span>}
      </div>
      <div className="modpicker">
        <ModPicker label="Build a combination" allowNone value={draft} onChange={setDraft} />
        <button type="button" className="btn btn--sm" disabled={value.includes(draft) || value.length >= GOAL_MODS.length}
          onClick={() => onChange([...value, draft])}>Add</button>
      </div>
    </div>
  );
}

function TargetPicker({ request, update }: { request: Request; update: (patch: Partial<Request>) => void }) {
  const replays = useCheckReplays(request.replay_path ?? null, false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [source, setSource] = useState<"replay" | "beatmap">(request.beatmap ? "beatmap" : "replay");
  const choices = bestReplays(replays.data?.replays ?? [], request.replay_path);
  return (
    <>
      <Choice label="Target source" value={source}
        options={[{ value: "replay", label: "A replay of this map" }, { value: "beatmap", label: "A beatmap link" }]}
        onChange={(next) => {
          setSource(next);
          update({ replay_path: null, beatmap: null });
        }} />
      {source === "beatmap" ? (
        <Field label="Beatmap link" help="On osu.ppy.sh open the specific difficulty (not the whole set) and copy the address.">
          <input className="input" placeholder="https://osu.ppy.sh/beatmapsets/123#osu/456" value={request.beatmap ?? ""}
            onChange={(e) => update({ beatmap: e.target.value, replay_path: null })} />
        </Field>
      ) : (
        <>
          <Combobox label="Replay for the FC target" placeholder="Type a map name" value={request.replay_path ?? ""}
            options={choices.map((r) => ({ value: r.path, label: `${r.map} +${r.mods} - ${r.player}${r.accuracy == null ? "" : ` - ${pct(r.accuracy, 2)}`}`, disabled: !r.analysable }))}
            onChange={(replayPath) => {
              const picked = replays.data?.replays.find((r) => r.path === replayPath);
              const mods = GOAL_MODS.find((m) => m === picked?.mods.replaceAll("NC", "DT"));
              update({ replay_path: replayPath, beatmap: null, ...(mods ? { mods } : {}) });
            }} />
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
      <p className="small muted">{value.plays} similar plays across {value.maps} maps.</p>
    </div>
  ) : null;
}

function playColumns(farm: boolean, estimates: boolean): Column<Recommendation>[] {
  return [
    { key: "map", header: "Map", strong: true, wrap: true,
      value: (r) => `${r.map.artist} - ${r.map.title} [${r.map.version}]`,
      cell: (r) => <a href={`https://osu.ppy.sh/beatmaps/${r.map.beatmap_id}`} target="_blank" rel="noreferrer noopener">
        {r.map.artist} - {r.map.title} [{r.map.version}]</a> },
    { key: "mods", header: "Mods", cell: (r) => <Badge tone="info">+{r.map.mods}</Badge>, value: (r) => r.map.mods },
    { key: "type", header: "Type", cell: (r) => r.map.dynamics ?? "", wrap: true, title: "The map's overall character." },
    { key: "stage", header: "Stage", cell: (r) => r.stage, title: "Starter: no data yet. Core: your level. Stretch: a bit above it." },
    { key: "stars", header: "Stars", cell: (r) => stars(r.map.stars), value: (r) => r.map.stars, align: "right" },
    { key: "bpm", header: "BPM", cell: (r) => fmt(r.map.bpm, 0), value: (r) => r.map.bpm, align: "right" },
    { key: "ar", header: "AR", cell: (r) => fmt(r.map.ar, 1), value: (r) => r.map.ar, align: "right" },
    { key: "length", header: "Length", cell: (r) => clock(r.map.length_s), value: (r) => r.map.length_s, align: "right" },
    { key: "target", header: "Target", cell: (r) => pct(r.practice_accuracy, 0), value: (r) => r.practice_accuracy, align: "right",
      title: "Accuracy to aim for, with no combo breaks." },
    ...(estimates ? [{ key: "estimate", header: "Estimate", align: "right" as const,
      cell: (r: Recommendation) => r.accuracy ? `${pct(r.accuracy.low, 0)}-${pct(r.accuracy.high, 0)}` : "",
      value: (r: Recommendation) => r.accuracy?.median, title: "Accuracy range of your similar plays." }] : []),
    ...(farm ? [{ key: "pp", header: "PP at target", align: "right" as const,
      cell: (r: Recommendation) => r.pp === null ? "" : `${fmt(r.pp, 0)}${r.pp_label?.startsWith("Achievable") ? "" : "*"}`,
      value: (r: Recommendation) => r.pp, title: "PP for a full combo at the target accuracy. * = if you FC it." },
    { key: "pp_ss", header: "PP at SS", align: "right" as const,
      cell: (r: Recommendation) => r.pp_ss == null ? "" : fmt(r.pp_ss, 0),
      value: (r: Recommendation) => r.pp_ss, title: "PP for a 100% play." }] : []),
    { key: "best", header: "Your best", align: "right",
      cell: (r) => r.local_best_accuracy === null ? "" : `${pct(r.local_best_accuracy, 1)}${r.achieved ? " ✓" : ""}`,
      value: (r) => r.local_best_accuracy },
  ];
}

function GoalResults({ result }: { result: Result }) {
  const { rounds, move } = useRounds(result);
  const all = result.recommendations;
  const { maps: recommendations, first } = stageMaps(all, rounds("plays").at);
  const maps = exportGoalMaps(recommendations);
  const columns = playColumns(result.request.goal === "farm", all.some((r) => r.accuracy));
  return (
    <>
      {result.request.goal === "fc" && <Card title={result.verdict} className={`verdict verdict--${result.tone}`}>
        {result.target && <p><strong>{result.target.artist} - {result.target.title} [{result.target.version}]</strong>{" "}
          +{result.target.mods} / {stars(result.target.stars)}{" "}
          {result.target.dynamics && <Badge tone="info">{result.target.dynamics}</Badge>}</p>}
        <ul className="list list--bullets">{result.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
        {result.request.goal === "fc" && <AccuracyRange value={result.accuracy} />}
        {result.replay_path && <Link className="btn btn--sm" to={`/check?path=${encodeURIComponent(result.replay_path)}`}>Open detailed map analysis</Link>}
      </Card>}
      {result.blockers.length > 0 && (
        <Card title="What to work on for this map">
          <ul className="list">
            {result.blockers.map((b) => <li key={b.skill}>
              <strong>{b.title}</strong> <Badge tone={b.observed ? "info" : "muted"}>{b.observed ? "Observed" : "Inferred"}</Badge>
              <p>{b.detail}</p>
              {b.timestamps.length > 0 && <p>Practise around: {b.timestamps.join(", ")}</p>}
            </li>)}
          </ul>
        </Card>
      )}
      <Card title={PLAYS_TITLE[result.request.goal]} hint={PICK_CRITERIA[result.request.goal]}
        actions={all.length > STAGE_SIZE && (
          <StageNav rounds={rounds("plays")} first={first} count={recommendations.length} total={all.length} onMove={(to) => move("plays", to)} />
        )}>
        {recommendations.length ? (
          <DataTable label={PLAYS_TITLE[result.request.goal]} rows={recommendations} columns={columns} maxHeight={560}
            rowKey={(r) => `${r.map.md5}:${r.map.mods}`} />
        ) : <EmptyState title="No suitable covered maps">Try another supported mod or analyse more replays. The app will not fill this list with unrelated maps.</EmptyState>}
      </Card>
      {maps.length > 0 && (
        <ExportPanel maps={maps} name={`osu-coach: ${result.request.goal} ${[...new Set(recommendations.map((r) => `+${r.map.mods}`))].join(" ")}`}
          preferred={result.request.client ?? "stable"} title="Get these maps into osu!"
          sub="Collections import maps, not mods. Set the listed mods manually; the text map list retains your play objectives." />
      )}
      {result.warnings.length > 0 && <Card title="Limitations"><details><summary>{result.warnings.length} notes</summary><ul className="list list--bullets">
        {result.warnings.map((warning) => <li key={warning}>{warning}</li>)}
      </ul></details></Card>}
    </>
  );
}
