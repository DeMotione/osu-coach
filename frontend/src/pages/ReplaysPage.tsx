import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";

import { api, unwrap, type Schemas } from "../api/client";
import { useJob } from "../api/jobs";
import {
  uploadFiles,
  useAnalysedReplays,
  useForgetFiles,
  useAnalysisStatus,
  useInstalls,
  useLibrary,
  useMeta,
  usePatchSettings,
  useSelection,
  useSettings,
} from "../api/queries";
import { DataTable, type Column } from "../components/DataTable";
import { IconMagnify, IconPlay, IconSearch } from "../components/icons";
import { EmptyState, JobStatus } from "../components/states";
import { Alert, Card, Dropzone, Field, FileChips, Meter, Page, Row, Segmented, Switch, type Option } from "../components/ui";
import { fmt, int, localTime, pct } from "../lib/format";

type Settings = Schemas["AppSettings"];
type Latest = Schemas["Latest"];

const LATEST_LABEL = (n: number) => (n ? `Latest ${n}` : "All");

export default function ReplaysPage() {
  const settings = useSettings();
  return (
    <Page
      title="Your replays"
      sub="osu! coach reads your replay files (.osr), replays every note against the beatmap and measures how you aim and tap. Everything runs on this computer."
    >
      {settings.data ? (
        <>
          <Row>
            <FindCard settings={settings.data} />
            <AnalyseCard settings={settings.data} />
          </Row>
          <AnalysedCard />
        </>
      ) : (
        <div className="row">
          <div className="skeleton" style={{ height: 460 }} />
          <div className="skeleton" style={{ height: 460 }} />
        </div>
      )}
    </Page>
  );
}

// ------------------------------------------------------------------ 1 · find replays
function FindCard({ settings }: { settings: Settings }) {
  const installs = useInstalls();
  const library = useLibrary();
  const patch = usePatchSettings();
  const scan = useJob("scan");
  const analysis = useJob("analysis");
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [folders, setFolders] = useState(settings.folders);
  const [uploads, setUploads] = useState<Schemas["UploadedFile"][]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const forget = useForgetFiles();
  const filesMode = settings.source_mode === "files";
  const busy = scan.running || analysis.running;
  // files added by hand are kept across scans (#38): the ones the library has, then the ones dropped since
  const kept = library.data?.files ?? [];
  const added = [...kept, ...uploads.filter((u) => !kept.some((k) => k.id === u.id))];

  const addFiles = async (files: File[]) => {
    setUploadError(null);
    try {
      const added = await uploadFiles(files);
      setUploads((u) => [...u.filter((x) => !added.some((a) => a.id === x.id)), ...added]);
    } catch (e) {
      setUploadError((e as Error).message);
    }
  };

  // every replay is read; how many of them to analyse is chosen in the Analyse card (#36)
  const startScan = () =>
    scan.run(() =>
      unwrap(
        api.POST("/api/library/scan", {
          body: {
            mode: settings.source_mode,
            installs: (installs.data ?? []).map((i) => i.root).filter((r) => !excluded.has(r)),
            folders: folders.split("\n").map((f) => f.trim()).filter(Boolean),
            files: uploads.map((u) => u.id),
          },
        }),
      ),
    );

  return (
    <Card title="1 · Find replays" sub="Where the replays come from: your osu! installs and folders, or only the files you drop here.">
      <Field label="Analyse">
        <Segmented
          label="Analyse"
          block
          value={settings.source_mode}
          onChange={(source_mode) => patch.mutate({ source_mode })}
          options={[
            { value: "library", label: "My replays (osu! installs and folders)" },
            { value: "files", label: "Only these files" },
          ]}
        />
      </Field>
      {filesMode ? (
        <Dropzone
          accept=".osr,.osu"
          onFiles={addFiles}
          title="Drop the replay files to analyse — only files you add, not your osu! installs"
          help="Added files are kept: drop more any time and Scan adds them to the others (a replay added twice counts once). Add their .osu maps too if they aren't on this computer; missing maps are downloaded."
        />
      ) : (
        <>
          <Field label="osu! installs found">
            {installs.data && installs.data.length > 0 ? (
              <div className="stack" style={{ gap: 8 }}>
                {installs.data.map((inst) => (
                  <label key={inst.root} className="check">
                    <input
                      type="checkbox"
                      checked={!excluded.has(inst.root)}
                      onChange={(e) => {
                        const next = new Set(excluded);
                        if (e.target.checked) next.delete(inst.root);
                        else next.add(inst.root);
                        setExcluded(next);
                      }}
                    />
                    <span className="check__text">{inst.label}</span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="muted small">
                No osu! installation was found automatically on this computer. Add a folder below or drop replay files.
              </p>
            )}
          </Field>
          <Field
            label="Extra folders (one per line)"
            hint="Searched recursively for .osr replays and .osu beatmaps. osu!stable keeps your replays in <osu!>/Data/r; in lazer use the Export button on the results screen (files land in <lazer data>/exports)."
          >
            <textarea className="textarea" value={folders} onChange={(e) => setFolders(e.target.value)} spellCheck={false} rows={3} />
          </Field>
          <Dropzone accept=".osr,.osu" onFiles={addFiles} title="…or add replay files" />
        </>
      )}
      {added.length > 0 && (
        <div className="added-files">
          <div className="added-files__head">
            <span className="small muted">
              Added files ({int(added.length)}){kept.length > 0 && kept.length < added.length ? ` · ${int(added.length - kept.length)} new, read at the next Scan` : ""}
            </span>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              disabled={busy || forget.isPending}
              title="Forget every file added by hand; your analysis keeps them until you analyse again"
              onClick={() => forget.mutate(undefined, { onSuccess: () => setUploads([]) })}
            >
              Clear
            </button>
          </div>
          <FileChips files={added} />
        </div>
      )}
      {forget.isError && <Alert tone="bad">{forget.error.message}</Alert>}
      {uploadError && <Alert tone="bad">{uploadError}</Alert>}
      <div className="grow" />
      <JobStatus
        job={scan.job}
        error={scan.error}
        done={(j) =>
          j.kind === "scan" && j.result ? (
            <>
              <Alert tone="good">Found {int(j.result.replays)} osu!standard replays.</Alert>
              {j.result.warnings.map((w) => (
                <Alert key={w} tone="warn">
                  {w}
                </Alert>
              ))}
            </>
          ) : null
        }
      />
      <button
        type="button"
        className={library.data?.scanned ? "btn btn--block" : "btn btn--primary btn--block"}
        disabled={busy || (filesMode && added.length === 0)}
        onClick={() => void startScan()}
      >
        <IconSearch /> Scan
      </button>
    </Card>
  );
}

// ------------------------------------------------------------------ 2 · analyse
function AnalyseCard({ settings }: { settings: Settings }) {
  const meta = useMeta();
  const library = useLibrary();
  const patch = usePatchSettings();
  const scan = useJob("scan");
  const analysis = useJob("analysis");
  const [player, setPlayer] = useState<string | null>(settings.player ?? null);
  const [online, setOnline] = useState(true);
  const busy = scan.running || analysis.running;
  const scanned = !!library.data?.scanned;
  const params = {
    player,
    latest: settings.latest,
    date_range: settings.date_range,
    date_from: settings.date_from,
    date_to: settings.date_to,
  };
  const selection = useSelection(params, scanned && !busy);
  const sel = selection.data;

  if (!scanned)
    return (
      <Card title="2 · Analyse" sub="Which of the found replays go into the analysis.">
        <EmptyState icon={<IconSearch />} title="Scan for replays first">
          Choose where your replays are and press Scan. Then pick the player, the time range and how many of the replays to analyse.
        </EmptyState>
      </Card>
    );

  const players = sel?.players ?? library.data?.players ?? [];
  const names = players.map((p) => p.name);
  const opts = [...names, ...(names.length > 1 ? ["*"] : [])];
  const chosen = sel?.player ?? (player && opts.includes(player) ? player : names[0]);
  const who = chosen === "*" ? "all players" : chosen || "(no name)";
  const dateLabel = meta.data?.date_choices.find((c) => c.key === sel?.date_range)?.label ?? "";
  const when =
    !sel || sel.date_range === "all"
      ? ""
      : sel.date_range === "custom" && sel.date_from && sel.date_to
        ? ` played ${sel.date_from} – ${sel.date_to}`
        : ` played ${dateLabel.toLowerCase()}`;
  const latestOptions: Option<Latest>[] = (meta.data?.latest_choices ?? [100, 500, 1000, 0]).map((n) => ({
    value: n as Latest,
    label: LATEST_LABEL(n),
  }));

  const analyse = () =>
    analysis.run(() =>
      unwrap(api.POST("/api/analysis", { body: { ...params, player: chosen ?? null, online } })),
    );

  return (
    <Card
      title="2 · Analyse"
      sub="The time range and Replays to read pick the replays before anything is analysed; Best replays keeps your best play per map afterwards."
    >
      {players.length === 0 ? (
        <Alert tone="warn">No osu!standard replays found there (relax/autopilot/autoplay replays are skipped).</Alert>
      ) : (
        <>
          <Field label="Player">
            <select className="select" value={chosen ?? ""} onChange={(e) => setPlayer(e.target.value)} disabled={busy}>
              {opts.map((n) => (
                <option key={n} value={n}>
                  {n === "*" ? "All players" : `${n || "(no name)"} (${players.find((p) => p.name === n)?.replays ?? 0} replays found)`}
                </option>
              ))}
            </select>
          </Field>
          {!sel?.files_mode && (
            <Field label="Played" hint="Only replays played in this time: your recent form. Last session = your newest replay and the ones before it with less than an hour between plays.">
              <select
                className="select"
                value={settings.date_range}
                onChange={(e) => patch.mutate({ date_range: e.target.value as Settings["date_range"] })}
              >
                {(meta.data?.date_choices ?? []).map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.label}
                  </option>
                ))}
              </select>
            </Field>
          )}
          {!sel?.files_mode && settings.date_range === "custom" && (
            <div className="split">
              <Field label="From">
                <input
                  className="input"
                  type="date"
                  value={settings.date_from ?? sel?.date_from ?? ""}
                  onChange={(e) => patch.mutate({ date_from: e.target.value || null })}
                />
              </Field>
              <Field label="To (included)">
                <input
                  className="input"
                  type="date"
                  value={settings.date_to ?? sel?.date_to ?? ""}
                  onChange={(e) => patch.mutate({ date_to: e.target.value || null })}
                />
              </Field>
            </div>
          )}
          {!sel?.files_mode && (
            <Field
              label="Replays to read"
              hint="How many of the found replays are analysed, newest first. Fewer = faster, and closer to how you play now. All = every replay found."
            >
              <Segmented
                label="Replays to read"
                block
                value={settings.latest}
                onChange={(latest) => patch.mutate({ latest })}
                options={latestOptions}
              />
            </Field>
          )}
          <Field label="Replays to use" help={`${meta.data?.best_definition ?? ""} All replays = every play, including fails and retries.`}>
            <Segmented
              label="Replays to use"
              block
              value={settings.replay_set}
              onChange={(replay_set) => patch.mutate({ replay_set })}
              options={(meta.data?.replay_sets ?? []).map((c) => ({ value: c.key as Settings["replay_set"], label: c.label }))}
            />
          </Field>
          <Switch
            checked={online}
            onChange={setOnline}
            label="Download missing beatmaps from the internet"
            hint="Looks the map up by its MD5 on osu.direct and downloads the .osu from osu.ppy.sh (verified against the replay)."
          />
          {selection.error && !busy && <Alert tone="bad">{selection.error.message}</Alert>}
          {sel && (
            <div className="stack" style={{ gap: 8 }}>
              <p className="muted">
                {sel.newest_only ? `The newest ${int(sel.replays)} replays` : `${int(sel.replays)} replays`} of {who}
                {when} will be analysed · {int(sel.missing_maps)} of their beatmaps are not on this computer
                {online && sel.missing_maps > 0 ? " (they will be downloaded)" : ""}.
              </p>
              {sel.empty_range && <Alert tone="warn">No replays in that time range — choose a longer one.</Alert>}
              {sel.left_out_total > 0 && (
                <p className="small muted">
                  {sel.left_out_total} replay(s) left out: {sel.left_out.map((r) => `${r.count}× ${r.label}`).join("; ")}.
                </p>
              )}
            </div>
          )}
        </>
      )}
      <div className="grow" />
      <JobStatus
        job={analysis.job}
        error={analysis.error}
        done={(j) =>
          j.kind === "analysis" && j.result ? (
            <>
              <Alert tone="good">
                Analysed {int(j.result.analysed)} replays
                {j.result.skipped ? ` (${j.result.skipped} skipped)` : ""}
                {j.result.best_replays !== null ? `; ${j.result.best_replays} of them are best replays` : ""}.{" "}
                {j.result.profile_ready && <Link to="/overview">Open the Overview →</Link>}
              </Alert>
              {j.result.warnings.map((w) => (
                <Alert key={w} tone="warn">
                  {w}
                </Alert>
              ))}
            </>
          ) : null
        }
      />
      <button
        type="button"
        className="btn btn--primary btn--block"
        disabled={busy || !sel || sel.replays === 0}
        onClick={() => void analyse()}
      >
        <IconPlay /> Analyse replays
      </button>
    </Card>
  );
}

// ------------------------------------------------------------------ analysed replays
type Replay = Schemas["AnalysedReplay"];

const COLUMNS: Column<Replay>[] = [
  { key: "played", header: "Played", cell: (r) => localTime(r.played_at), value: (r) => r.played_at },
  { key: "map", header: "Map", cell: (r) => r.map, strong: true, wrap: true },
  { key: "mods", header: "Mods", cell: (r) => r.mods },
  { key: "stars", header: "Difficulty", cell: (r) => fmt(r.stars, 2, " ★"), value: (r) => r.stars, align: "right",
    title: "Star rating (with the mods of the play, e.g. DT)." },
  {
    key: "weight",
    header: "Weight",
    title: "How much this play counts in the statistics (difficulty weighting, see Overview).",
    value: (r) => r.weight,
    cell: (r) => (
      <span className="cell-bar">
        <Meter value={r.weight * 100} color="var(--accent)" />
        <span className="num">{Math.round(r.weight * 100)}%</span>
      </span>
    ),
  },
  { key: "acc", header: "Accuracy", cell: (r) => pct(r.accuracy, 2), value: (r) => r.accuracy, align: "right" },
  { key: "miss", header: "Misses", cell: (r) => int(r.misses), value: (r) => r.misses, align: "right" },
  { key: "combo", header: "Combo", cell: (r) => int(r.combo), value: (r) => r.combo, align: "right" },
  { key: "ur", header: "UR", cell: (r) => fmt(r.ur, 0), value: (r) => r.ur, align: "right" },
  { key: "check", header: "Check", cell: (r) => pct(r.sim_agreement, 1), value: (r) => r.sim_agreement, align: "right",
    title: "How well the re-simulated judgements match the result stored in the replay (100% = identical)." },
];

function AnalysedCard() {
  const status = useAnalysisStatus();
  const replays = useAnalysedReplays(!!status.data && status.data.profile_replays !== null);
  const navigate = useNavigate();
  const [selected, setSelected] = useState<Replay | null>(null);
  const rows = useMemo(() => replays.data ?? [], [replays.data]);
  const st = status.data;
  if (!st || st.analysed === 0) return null;
  const best = st.replay_set === "best";
  return (
    <Card
      title={`Analysed replays (${rows.length})`}
      sub={
        (best ? "Best replays only — the" : "The") +
        " plays your numbers come from, newest first. Weight = how much a play counts: 100% within ±0.5★ of your level, less the further its difficulty is from it. Pick a row to open it on its own."
      }
      actions={
        <button
          type="button"
          className="btn btn--primary btn--sm"
          disabled={!selected}
          onClick={() => selected && navigate(`/check?path=${encodeURIComponent(selected.path)}`)}
        >
          <IconMagnify /> Detailed map analysis
        </button>
      }
    >
      {st.best_empty ? (
        <Alert tone="warn">None of the analysed replays is a passed play, so Best replays is empty — switch to All replays.</Alert>
      ) : (
        <DataTable
          label="Analysed replays"
          rows={rows}
          columns={COLUMNS}
          rowKey={(r) => r.key}
          selected={selected?.key ?? null}
          onSelect={(r) => setSelected(r)}
          maxHeight={460}
        />
      )}
      {st.skipped_total > 0 && (
        <details className="disclosure">
          <summary>{st.skipped_total} replay(s) skipped</summary>
          <div className="disclosure__body">
            <ul className="list small">
              {st.skipped.map((s, i) => (
                <li key={`${s.file}-${i}`}>
                  <code>{s.file}</code> — {s.reason}
                </li>
              ))}
            </ul>
          </div>
        </details>
      )}
    </Card>
  );
}
