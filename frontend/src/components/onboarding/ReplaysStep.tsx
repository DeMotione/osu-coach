/* eslint-disable react-refresh/only-export-components -- the step and the hook that runs its jobs belong together */
import { useEffect, useRef, useState } from "react";

import { api, unwrap, type Job, type Schemas } from "../../api/client";
import { useJob } from "../../api/jobs";
import { uploadFiles, useAnalysisStatus, useInstalls, useMeta, usePatchSettings, useSettings } from "../../api/queries";
import { formatLeft, useSecondsLeft } from "../../lib/eta";
import { int } from "../../lib/format";
import { IconArrowLeft, IconArrowRight, IconCheck, IconFolder, IconSearch, IconUpload } from "../icons";
import { Alert, Dropzone, Field, FileChips, Progress, Segmented } from "../ui";
import { ChoiceCards, HitCircles, Step } from "./parts";

/** The scan and the analysis the guide started (job ids), to tell them from other jobs and to follow them. */
export interface ReplayRun {
  scan: string;
  analysis?: string;
}

type Phase = "idle" | "scanning" | "analysing" | "done" | "empty" | "failed";
type ScanRequest = Schemas["ScanRequest"];

/**
 * The guide's replay run: a scan, then — by itself — the analysis of what it found. Kept by the whole guide, not the
 * step, so the analysis starts even when the player has moved on to the next step meanwhile.
 */
export function useReplayRun(run: ReplayRun | null, setRun: (run: ReplayRun | null) => void) {
  const settings = useSettings();
  const scan = useJob("scan");
  const analysis = useJob("analysis");
  const chained = useRef<string | null>(null);

  const scanJob = run && scan.job?.id === run.scan ? scan.job : undefined;
  const analysisJob = run?.analysis && analysis.job?.id === run.analysis ? analysis.job : undefined;
  const found = scanJob?.kind === "scan" && scanJob.status === "succeeded" ? (scanJob.result?.replays ?? 0) : null;
  const failedJob = [analysisJob, scanJob].find((j) => j?.status === "failed");
  const error = scan.error?.message ?? analysis.error?.message ?? failedJob?.error ?? null;

  let phase: Phase = "idle";
  if (error) phase = "failed";
  else if (analysisJob) phase = analysisJob.status === "running" ? "analysing" : "done";
  else if (scanJob) phase = scanJob.status === "running" ? "scanning" : found === 0 ? "empty" : "analysing";

  // the scan found replays: analyse them, with the choices of the Replays page
  const s = settings.data;
  useEffect(() => {
    if (!run || run.analysis || !found || !s || chained.current === run.scan) return;
    chained.current = run.scan;
    const body = {
      player: s.player ?? null,
      latest: s.latest,
      date_range: s.date_range,
      date_from: s.date_from ?? null,
      date_to: s.date_to ?? null,
      online: true,
    };
    void analysis
      .run(() => unwrap(api.POST("/api/analysis", { body })))
      .then((job) => job && setRun({ scan: run.scan, analysis: job.id }));
  }, [run, found, s, analysis, setRun]);

  const reset = () => {
    chained.current = null;
    scan.dismiss();
    analysis.dismiss();
    setRun(null);
  };

  const start = async (body: ScanRequest) => {
    reset();
    const job = await scan.run(() => unwrap(api.POST("/api/library/scan", { body })));
    if (job) setRun({ scan: job.id });
  };

  // a scan or an analysis that isn't the guide's (e.g. the last session being restored): wait for it
  const other = [scan, analysis].find((j) => j.running && j.job?.id !== run?.scan && j.job?.id !== run?.analysis)?.job;

  return { phase, scanJob, analysisJob, found, error, other, start, reset, started: !!analysisJob };
}

export type ReplayRunState = ReturnType<typeof useReplayRun>;

// ------------------------------------------------------------------ the step
/** Step 3: find the replays (osu! installs, or files and folders given by hand), then scan and analyse them. */
export function ReplaysStep({ client, r, onBack, onNext }: { client: Schemas["SetupModel"]["client"]; r: ReplayRunState; onBack: () => void; onNext: () => void }) {
  const status = useAnalysisStatus();
  const had = !!status.data && status.data.analysed > 0;
  const working = r.phase === "scanning" || r.phase === "analysing";
  return (
    <Step
      title="Find your replays"
      sub="osu! coach replays every note of your plays against the beatmap to see how you aim and tap. Everything runs on this computer."
      foot={
        <>
          <button type="button" className="btn btn--ghost" onClick={onBack}>
            <IconArrowLeft /> Back
          </button>
          <span className="grow" />
          {r.phase === "done" || (r.phase === "analysing" && r.started) || (had && !working) ? (
            <button type="button" className="btn btn--primary" onClick={onNext}>
              {r.phase === "analysing" ? "Continue while it runs" : "Continue"} <IconArrowRight />
            </button>
          ) : working ? (
            <button type="button" className="btn btn--primary" disabled title="Wait until your replays are found">
              Continue <IconArrowRight />
            </button>
          ) : (
            <button type="button" className="btn btn--ghost" onClick={onNext}>
              Skip for now
            </button>
          )}
        </>
      }
    >
      {working ? (
        <Working r={r} />
      ) : r.phase === "done" ? (
        <Finished r={r} player={status.data?.player_label ?? ""} />
      ) : (
        <>
          {r.phase === "failed" && <Alert tone="bad">{r.error}</Alert>}
          {r.phase === "empty" && (
            <Alert tone="warn">
              No osu!standard replays were found there (relax, autopilot and autoplay replays are skipped). Try other
              folders or add the replay files yourself.
            </Alert>
          )}
          {had && r.phase === "idle" && (
            <Alert tone="good">
              {int(status.data!.analysed)} replays{status.data!.player_label ? ` of ${status.data!.player_label}` : ""} are
              analysed already. Continue, or find and analyse your replays again.
            </Alert>
          )}
          <Sources client={client} r={r} />
        </>
      )}
    </Step>
  );
}

// ------------------------------------------------------------------ where the replays come from
function Sources({ client, r }: { client: Schemas["SetupModel"]["client"]; r: ReplayRunState }) {
  const settings = useSettings();
  const installs = useInstalls();
  const meta = useMeta();
  const patch = usePatchSettings();
  const all = installs.data ?? [];
  const [mode, setMode] = useState<"auto" | "manual" | null>(null);
  const [picked, setPicked] = useState<Set<string> | null>(null);
  const [uploads, setUploads] = useState<Schemas["UploadedFile"][]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [folder, setFolder] = useState("");
  const [starting, setStarting] = useState(false);

  const how = mode ?? (installs.isPending || all.length > 0 ? "auto" : "manual");
  // the installs of the osu! chosen in step 1 (all of them when there is none of that kind)
  const mine = all.some((i) => i.kind === client) ? all.filter((i) => i.kind === client) : all;
  const chosen = picked ?? new Set(mine.map((i) => i.root));
  const s = settings.data;
  const extra = (s?.folders ?? "").split("\n").map((f) => f.trim()).filter(Boolean);

  const addFiles = async (files: File[]) => {
    setUploadError(null);
    try {
      const added = await uploadFiles(files);
      setUploads((u) => [...u.filter((x) => !added.some((a) => a.id === x.id)), ...added]);
    } catch (e) {
      setUploadError((e as Error).message);
    }
  };

  if (!s) return <div className="skeleton" style={{ height: 240 }} />;

  const body: ScanRequest | null =
    how === "auto"
      ? chosen.size || extra.length
        ? { mode: "library", installs: [...chosen], folders: extra, files: [] }
        : null
      : folder.trim()
        ? { mode: "library", installs: [], folders: [folder.trim()], files: uploads.map((u) => u.id) }
        : uploads.length
          ? { mode: "files", folders: [], files: uploads.map((u) => u.id) }
          : null;
  const library = how === "auto" || !!folder.trim();

  const go = async () => {
    if (!body) return;
    setStarting(true);
    await r.start(body);
    setStarting(false);
  };

  return (
    <>
      <ChoiceCards
        label="Find replays"
        value={how}
        onChange={setMode}
        options={[
          { value: "auto", title: "Find them for me", text: "Read the replays of the osu! found on this computer.", icon: <IconSearch /> },
          { value: "manual", title: "I'll add them myself", text: "Drop replay files (.osr), or enter a folder with replays in it.", icon: <IconUpload /> },
        ]}
      />
      {how === "auto" ? (
        <Field label="osu! to read">
          {installs.isPending ? (
            <p className="muted small">Looking for osu! on this computer…</p>
          ) : all.length > 0 ? (
            <div className="stack" style={{ gap: 8 }}>
              {all.map((inst) => (
                <label key={inst.root} className="check">
                  <input
                    type="checkbox"
                    checked={chosen.has(inst.root)}
                    onChange={(e) => {
                      const next = new Set(chosen);
                      if (e.target.checked) next.add(inst.root);
                      else next.delete(inst.root);
                      setPicked(next);
                    }}
                  />
                  <span className="check__text">{inst.label}</span>
                </label>
              ))}
            </div>
          ) : (
            <Alert tone="warn">
              No osu! was found on this computer. Go back to step 1 to enter the folder it is in, or add your replays
              yourself.
            </Alert>
          )}
          {extra.length > 0 && <span className="field__help">And your extra folders: {extra.join(", ")}</span>}
        </Field>
      ) : (
        <>
          <Dropzone
            accept=".osr,.osu"
            onFiles={addFiles}
            title="Drop replay files here, or click to choose them"
            help="Add their .osu beatmaps too if they aren't on this computer; missing ones are downloaded."
          />
          <FileChips files={uploads} />
          {uploadError && <Alert tone="bad">{uploadError}</Alert>}
          <Field label="…or a folder with replays" hint="Searched with its subfolders for .osr replays and .osu beatmaps.">
            <input className="input" value={folder} onChange={(e) => setFolder(e.target.value)} placeholder="A folder with .osr files" spellCheck={false} autoComplete="off" />
          </Field>
        </>
      )}
      {library && (
        <Field label="Replays to read" hint="How many of your replays are analysed, newest first. Fewer = faster, and closer to how you play now; you can analyse more later on the Replays page.">
          <Segmented
            label="Replays to read"
            block
            value={s.latest}
            onChange={(latest) => patch.mutate({ latest })}
            options={(meta.data?.latest_choices ?? [100, 500, 1000, 0]).map((n) => ({ value: n as Schemas["Latest"], label: n ? `Latest ${n}` : "All" }))}
          />
        </Field>
      )}
      {r.other && (
        <Alert tone="info">
          Another task is running ({r.other.message || "working"}). You can start once it has finished.
        </Alert>
      )}
      <button type="button" className="btn btn--primary btn--lg" disabled={!body || !!r.other || starting} onClick={() => void go()}>
        {how === "auto" ? <IconSearch /> : <IconFolder />} Find and analyse my replays
      </button>
    </>
  );
}

// ------------------------------------------------------------------ while it runs, and after
function Working({ r }: { r: ReplayRunState }) {
  const analysing = r.phase === "analysing";
  const job: Job | undefined = analysing ? r.analysisJob : r.scanJob;
  const progress = analysing ? job?.progress : null;
  const left = useSecondsLeft(analysing && job?.status === "running" ? job.id : null, progress);
  const known = progress !== null && progress !== undefined && Number.isFinite(progress);
  return (
    <div className="working">
      <HitCircles />
      <div className="working__text" role="status">
        <p className="working__title">Wait for replays to be analysed</p>
        <p className="working__eta">
          {left !== null
            ? formatLeft(left).replace(/^./, (c) => c.toUpperCase())
            : analysing
              ? "Working out how long it takes…"
              : "Looking for your replays first…"}
        </p>
      </div>
      <div className="working__progress">
        <Progress value={progress} text={job?.message || (analysing ? "Starting the analysis…" : "Scanning…")} right={known ? `${Math.round(progress * 100)}%` : undefined} />
      </div>
      <ol className="stages">
        <li className={analysing ? "done" : "current"}>
          {analysing ? <IconCheck /> : <span className="stages__dot" />}
          {r.found === null ? "Find your replays" : `Found ${int(r.found)} replays`}
        </li>
        <li className={analysing ? "current" : ""}>
          <span className="stages__dot" />
          Analyse them
        </li>
      </ol>
      <p className="small muted">
        {analysing
          ? "The first analysis takes longest: later ones reuse it. You can go on with the guide meanwhile."
          : "This takes a moment the first time — osu! coach reads every replay's header."}
      </p>
    </div>
  );
}

function Finished({ r, player }: { r: ReplayRunState; player: string }) {
  const res = r.analysisJob?.kind === "analysis" ? r.analysisJob.result : null;
  const players = r.scanJob?.kind === "scan" ? (r.scanJob.result?.players ?? 0) : 0;
  if (!res) return null;
  return (
    <div className="working working--done">
      <span className="done-mark">
        <IconCheck />
      </span>
      <div className="working__text" role="status">
        <p className="working__title">
          Analysed {int(res.analysed)} replays{player ? ` of ${player}` : ""}
        </p>
        <p className="muted">
          {players > 1 && player && player !== "All players"
            ? `Your replays folder has plays of ${players} players; ${player} has the most, so these are taken as yours. Not you? Pick your name on the Replays page. `
            : "You can analyse other replays any time on the Replays page. "}
          {res.skipped ? `${int(res.skipped)} could not be analysed — the Replays page lists them.` : ""}
        </p>
      </div>
      {res.warnings.map((w) => (
        <Alert key={w} tone="warn">
          {w}
        </Alert>
      ))}
    </div>
  );
}
