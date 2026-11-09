import { useMemo, useState } from "react";

import { api, downloadFile, saveBlob, unwrap, type Schemas } from "../api/client";
import { useJob } from "../api/jobs";
import { useExportPreview, useMergeStable, useMeta } from "../api/queries";
import { IconDownload, IconList, IconPlay } from "./icons";
import { JobStatus } from "./states";
import { Alert, Card, Field, Section, Tabs } from "./ui";

type MapRow = Schemas["MapRow"];
type Client = "lazer" | "stable";

/** Get a list of pool maps into osu!: maps straight into lazer, stable collection + .osz, or a map list. */
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
        <LazerTab body={body} preview={preview.data} />
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

function LazerTab({ body, preview }: {
  body: Schemas["ExportRequest"];
  preview?: Schemas["ExportPreview"];
}) {
  const meta = useMeta();
  const send = useJob("lazer_send");
  const found = meta.data?.lazer_found ?? false;
  const count = preview
    ? (preview.lazer_approximate
      ? `Up to ${preview.lazer_sets} of ${preview.total_sets} beatmap sets will be downloaded (maps you already have are skipped)`
      : `${preview.lazer_sets} of ${preview.total_sets} beatmap sets will be downloaded` +
        (preview.lazer_sets < preview.total_sets ? " (you already have the others)" : ""))
    : "…";
  return (
    <div className="split">
      <Section title="The maps, straight into lazer">
        <p className="muted">
          osu! coach downloads the maps you don't have and hands them to lazer, which imports them and deletes the
          downloads (lazer opens if it's closed). Nothing is left in your Downloads.
        </p>
        <p className="small muted">{count}</p>
        <div className="btn-row">
          <button
            type="button"
            className="btn btn--primary"
            disabled={!found || send.running}
            onClick={() => void send.run(() => unwrap(api.POST("/api/exports/lazer-send", { body })))}
          >
            <IconDownload /> Send the maps to lazer
          </button>
        </div>
        {meta.data && !found && (
          <Alert tone="warn">
            osu!lazer wasn't found on this computer. Use the links in the map list, or the osu!stable tab's .osz download.
          </Alert>
        )}
        <JobStatus
          job={send.job}
          error={send.error}
          onCancel={send.cancel}
          cancelled="Cancelled. The maps lazer already took stay in lazer."
          done={(j) =>
            j.kind === "lazer_send" && j.result ? (
              <Alert tone={j.result.not_imported?.length || j.result.failed?.length ? "warn" : "good"}>
                {(j.result.maps?.length ?? 0) === 0
                  ? "lazer already has every map."
                  : `lazer imported ${j.result.imported?.length ?? 0} of ${j.result.maps?.length ?? 0} map set(s).`}
                {(j.result.not_imported?.length ?? 0) > 0 &&
                  ` It hadn't taken set(s) ${j.result.not_imported?.join(", ")} yet: check lazer's notifications.`}
                {(j.result.failed?.length ?? 0) > 0 &&
                  ` Couldn't download set(s) ${j.result.failed?.join(", ")}: use the links in the map list.`}
                {(j.result.not_found ?? 0) > 0 &&
                  ` ${j.result.not_found} map(s) you don't have weren't found online: you need to get them yourself.`}
              </Alert>
            ) : null
          }
        />
      </Section>
      <Section title="Then, in lazer">
        <ol className="list list--steps">
          <li>
            Press <IconPlay width={12} height={12} /> <strong>in lazer</strong> next to a map in the list: lazer shows that
            map with its difficulty picked.
          </li>
          <li>
            Press lazer's <strong>Go to beatmap</strong> button (») there: the map opens in song select.
          </li>
          <li>Set the mods and speed shown in the list, then play.</li>
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
            {unknownSets} map(s) have no known beatmap set, so they can't be downloaded here (sending them to lazer looks them up).
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
