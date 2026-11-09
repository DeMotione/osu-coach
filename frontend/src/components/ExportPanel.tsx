import { useMemo, useState } from "react";

import { api, downloadFile, saveBlob, unwrap, type Schemas } from "../api/client";
import { useJob } from "../api/jobs";
import { useExportPreview, useMergeStable, useMeta } from "../api/queries";
import { Md } from "../lib/markdown";
import { IconDownload, IconFolder, IconList } from "./icons";
import { JobStatus } from "./states";
import { Alert, Card, Field, Section, Tabs } from "./ui";

type MapRow = Schemas["MapRow"];
type Client = "lazer" | "stable";

/** Get a list of pool maps into osu!: lazer import folder, stable collection + .osz, or a map list. */
export function ExportPanel({ maps, name, preferred, title, sub }: {
  maps: MapRow[];
  name: string;
  preferred: Client;
  title: string;
  sub: string;
}) {
  const body = useMemo<Schemas["ExportRequest"]>(
    () => ({ name, maps: maps.map((m) => ({ md5: m.md5, beatmapset_id: m.beatmapset_id })) }),
    [name, maps],
  );
  const [tab, setTab] = useState<Client>(preferred);
  const preview = useExportPreview(maps.length ? body : null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const order: Client[] = preferred === "lazer" ? ["lazer", "stable"] : ["stable", "lazer"];
  const mapList = () => {
    const text = maps
      .map((m) => `[${m.stage ?? ""}] ${m.stars !== null ? `${m.stars.toFixed(2)}* ` : ""}${m.artist} - ${m.title} [${m.version}] · ${m.mods} · ${m.rate.toFixed(2)}×  ${m.url}${m.goal ? `  ${m.goal}` : ""}`)
      .join("\n");
    saveBlob(new Blob([`${name}\n\n${text}\n`], { type: "text/plain" }), "playlist.txt");
  };
  const download = (path: string, fallback: string) => {
    setDownloadError(null);
    downloadFile(path, body, fallback).catch((e: Error) => setDownloadError(e.message));
  };

  return (
    <Card
      title={title}
      hint={sub}
      actions={
        <button type="button" className="btn btn--sm" onClick={mapList} disabled={!maps.length}>
          <IconList /> Map list (.txt)
        </button>
      }
    >
      <p className="small muted">The .txt list includes exact mods and speed. Collection and map downloads contain maps only; set the shown mods and speed in osu! before playing.</p>
      <Tabs
        tabs={order.map((c) => ({ value: c, label: c === "lazer" ? "osu!lazer" : "osu!stable" }))}
        value={tab}
        onChange={setTab}
      />
      {downloadError && <Alert tone="bad">{downloadError}</Alert>}
      {tab === "lazer" ? (
        <LazerTab body={body} preview={preview.data} onZip={() => download("/api/exports/lazer-zip", "playlist.zip")} />
      ) : (
        <StableTab
          body={body}
          preview={preview.data}
          setIds={[...new Set(maps.map((m) => m.beatmapset_id).filter((s) => s > 0))]}
          unknownSets={maps.filter((m) => m.beatmapset_id <= 0).length}
          onCollection={() => download("/api/exports/collection-db", "collection.db")}
        />
      )}
    </Card>
  );
}

function LazerTab({ body, preview, onZip }: {
  body: Schemas["ExportRequest"];
  preview?: Schemas["ExportPreview"];
  onZip: () => void;
}) {
  const meta = useMeta();
  const pack = useJob("lazer_pack");
  const count = preview
    ? preview.lazer_approximate
      ? `Up to ${preview.lazer_sets} of ${preview.total_sets} beatmap sets will be downloaded (maps you already have are skipped)`
      : `${preview.lazer_sets} of ${preview.total_sets} beatmap sets will be downloaded` +
        (preview.lazer_sets < preview.total_sets ? " (you already have the others)" : "")
    : "…";
  return (
    <div className="split">
      <Section title="One folder with the maps and the collection">
        <p className="muted">
          lazer can't open a collection file by itself, but its <strong>import from a previous osu! version</strong> takes maps{" "}
          <em>and</em> collections from any folder that looks like an osu!stable install. osu! coach makes that folder for you.
        </p>
        <p className="small muted">
          {count} · folder: <code>{preview?.lazer_folder ?? "…"}</code>
        </p>
        <div className="btn-row">
          <button
            type="button"
            className="btn btn--primary"
            disabled={pack.running}
            onClick={() => void pack.run(() => unwrap(api.POST("/api/exports/lazer-pack", { body })))}
          >
            <IconFolder /> Make lazer import folder
          </button>
          <button type="button" className="btn" onClick={onZip} title="Just the collection, e.g. for lazer on another computer.">
            <IconDownload /> Folder without maps (.zip)
          </button>
        </div>
        <JobStatus
          job={pack.job}
          error={pack.error}
          onCancel={pack.cancel}
          cancelled="Cancelled. The map sets downloaded so far stay in the folder; making it again picks up where it stopped."
          done={(j) =>
            j.kind === "lazer_pack" && j.result ? (
              <Alert tone="good">
                Ready: <code>{j.result.path}</code> with {j.result.maps.length} map set(s) and the collection.
                {j.result.failed.length > 0 &&
                  ` Couldn't download set(s) ${j.result.failed.join(", ")}: use the links in the map list.`}
                {j.result.not_found > 0 &&
                  ` ${j.result.not_found} map(s) you don't have weren't found online: they're in the collection, but you need to get them yourself.`}
              </Alert>
            ) : null
          }
        />
      </Section>
      <Section title="Then, in lazer">
        <ol className="list list--steps">
          {(meta.data?.lazer_instructions ?? []).map((s) => (
            <li key={s}>
              <Md>{s}</Md>
            </li>
          ))}
        </ol>
      </Section>
    </div>
  );
}

function StableTab({ body, preview, setIds, unknownSets, onCollection }: {
  body: Schemas["ExportRequest"];
  preview?: Schemas["ExportPreview"];
  setIds: number[];
  unknownSets: number;
  onCollection: () => void;
}) {
  const merge = useMergeStable();
  const osz = useJob("osz_download");
  const [folder, setFolder] = useState<string | null>(null);
  const dest = folder ?? preview?.osz_folder ?? "";
  return (
    <div className="split">
      <Section title="The collection">
        <p className="muted">
          Add it to your osu!stable collections (with osu! closed — your old collection.db is backed up first), or save a
          collection.db, e.g. for Collection Manager.
        </p>
        <div className="btn-row">
          <button
            type="button"
            className="btn btn--primary"
            disabled={!preview?.stable_available || merge.isPending}
            title={preview && !preview.stable_available ? "No osu!stable install was found on this computer." : undefined}
            onClick={() => merge.mutate(body)}
          >
            Add to my osu!stable collections
          </button>
          <button type="button" className="btn" onClick={onCollection}>
            <IconDownload /> collection.db
          </button>
        </div>
        {merge.isSuccess && (
          <Alert tone="good">
            Added “{body.name}” to <code>{merge.data.path}</code> (backup: {merge.data.backup ?? "none needed"}).
          </Alert>
        )}
        {merge.isError && <Alert tone="bad">{merge.error.message}</Alert>}
      </Section>
      <Section title="The maps (.osz)">
        <Field label="Download the maps to" help="osu!stable picks up .osz files in its Songs folder on the next start (or F5 in song select).">
          <input className="input" value={dest} onChange={(e) => setFolder(e.target.value)} spellCheck={false} />
        </Field>
        <button
          type="button"
          className="btn"
          disabled={osz.running || !dest.trim() || !setIds.length}
          onClick={() =>
            void osz.run(() => unwrap(api.POST("/api/exports/osz", { body: { folder: dest.trim(), set_ids: setIds } })))
          }
        >
          <IconDownload /> Download all {setIds.length} maps
        </button>
        {unknownSets > 0 && (
          <p className="small muted">
            {unknownSets} map(s) have no known beatmap set, so they can't be downloaded here (the lazer folder looks them up).
            They're still in the collection.
          </p>
        )}
        <JobStatus
          job={osz.job}
          error={osz.error}
          onCancel={osz.cancel}
          cancelled="Cancelled. The maps downloaded so far stay in the folder."
          done={(j) =>
            j.kind === "osz_download" && j.result ? (
              <Alert tone={j.result.failed.length ? "warn" : "good"}>
                Downloaded {j.result.downloaded}/{j.result.downloaded + j.result.failed.length} beatmap sets to{" "}
                <code>{j.result.folder}</code>.{j.result.failed.length > 0 && ` Failed: ${j.result.failed.join(", ")}.`}
              </Alert>
            ) : null
          }
        />
      </Section>
    </div>
  );
}
