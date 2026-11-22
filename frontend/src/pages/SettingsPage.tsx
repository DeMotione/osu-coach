import { Link } from "react-router";

import type { Schemas } from "../api/client";
import { useInstalls, useMeta, usePatchSettings, useSettings } from "../api/queries";
import { IconCheck } from "../components/icons";
import { QueryView } from "../components/states";
import { Alert, Card, Field, Page, Row, Segmented, Switch } from "../components/ui";

type Settings = Schemas["AppSettings"];
type Engine = Settings["rating_engine"];

const ABOUT: Record<Engine, { what: string; how: string }> = {
  comfort: {
    what: "Each skill gets a score from 0 to 100. 50 = what maps at your comfort level ask for (assumed from ranked maps, not compared with other players).",
    how: "Uses your best play on each map and mod setup. A skill your maps haven't pushed yet shows as \"at least\".",
  },
  irt: {
    what: "Each skill as the map star rating it holds up on: on maps that hard you'd miss only about 2 in 100 of its notes. Comes with a range for how sure it is. No comparison with other players.",
    how: "Worked out from every note you hit or missed and how hard it was. Experimental: the numbers may still change.",
  },
};

export default function SettingsPage() {
  const settings = useSettings();
  return (
    <Page title="Settings">
      <QueryView query={settings}>
        {(s) => (
          <>
            <EngineCard settings={s} />
            <Row>
              <InstallsCard settings={s} />
              <DownloadsCard settings={s} />
            </Row>
          </>
        )}
      </QueryView>
    </Page>
  );
}

function EngineCard({ settings }: { settings: Settings }) {
  const meta = useMeta();
  const patch = usePatchSettings();
  const engines = meta.data?.rating_engines ?? [];
  const chosen = (patch.isPending ? patch.variables?.rating_engine : undefined) ?? settings.rating_engine;
  const about = ABOUT[chosen];
  return (
    <Card title="Skill measurement" hint="How your skills are measured. Every page that shows skills follows this choice.">
      <div className="stack" style={{ gap: 12 }}>
        <Field label="Measure skills with">
          <Segmented
            label="Skill measurement"
            block
            value={chosen}
            onChange={(rating_engine) => patch.mutate({ rating_engine })}
            options={engines.map((c) => ({ value: c.key as Engine, label: c.label, disabled: patch.isPending }))}
          />
        </Field>
        {about && (
          <p className="muted">
            {about.what} {about.how}
          </p>
        )}
        {patch.isPending && (
          <p className="apply-status" role="status">
            <span className="spinner" aria-hidden="true" />
            Recalculating your skills…
          </p>
        )}
        {patch.isSuccess && !patch.isPending && (
          <p className="apply-status apply-status--good" role="status">
            <IconCheck />
            Applied: every page now uses this engine.
          </p>
        )}
        {patch.isError && <Alert tone="bad">{patch.error.message}</Alert>}
      </div>
    </Card>
  );
}

/** Whose replays a scan reads: the osu! installs found on this computer, each one on or off. */
function InstallsCard({ settings }: { settings: Settings }) {
  const installs = useInstalls();
  const patch = usePatchSettings();
  const skipped = new Set(settings.skipped_installs);
  const found = installs.data ?? [];
  return (
    <Card title="osu! installs" hint="The osu! on this computer whose replays a scan reads. Extra folders and replay files are added on the Replays page.">
      {installs.isPending ? (
        <p className="muted small">Looking for osu! on this computer…</p>
      ) : found.length > 0 ? (
        <div className="stack" style={{ gap: 8 }}>
          {found.map((inst) => (
            <label key={inst.root} className="check">
              <input
                type="checkbox"
                checked={!skipped.has(inst.root)}
                onChange={(e) => {
                  const next = new Set(skipped);
                  if (e.target.checked) next.delete(inst.root);
                  else next.add(inst.root);
                  patch.mutate({ skipped_installs: [...next] });
                }}
              />
              <span className="check__text">{inst.label}</span>
            </label>
          ))}
        </div>
      ) : (
        <p className="muted small">No osu! installation was found automatically on this computer. Add a folder or replay files on the Replays page.</p>
      )}
      <p className="small muted">
        A change counts from the next scan: <Link to="/replays">Replays</Link> → Scan.
      </p>
      {patch.isError && <Alert tone="bad">{patch.error.message}</Alert>}
    </Card>
  );
}

/** Whether a replay whose map isn't on this computer gets the map from the internet. */
function DownloadsCard({ settings }: { settings: Settings }) {
  const patch = usePatchSettings();
  return (
    <Card title="Missing beatmaps" hint="A replay is analysed with its map's .osu file.">
      <Switch
        checked={settings.download_maps}
        onChange={(download_maps) => patch.mutate({ download_maps })}
        label="Download beatmaps that aren't on this computer"
        hint="Looks the map up by its MD5 on osu.direct and downloads the .osu from osu.ppy.sh (checked against the replay)."
      />
      <p className="small muted">
        For analysing your replays, Detailed Map Analysis and Play Goals. Off: a replay whose map isn't on this computer
        can't be analysed.
      </p>
      {patch.isError && <Alert tone="bad">{patch.error.message}</Alert>}
    </Card>
  );
}
