import type { Schemas } from "../api/client";
import { useMeta, usePatchSettings, useSettings } from "../api/queries";
import { IconCheck } from "../components/icons";
import { QueryView } from "../components/states";
import { Alert, Card, Field, Page, Segmented } from "../components/ui";

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
      <QueryView query={settings}>{(s) => <EngineCard settings={s} />}</QueryView>
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
