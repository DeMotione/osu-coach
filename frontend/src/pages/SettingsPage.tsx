import type { Schemas } from "../api/client";
import { useMeta, usePatchSettings, useSettings } from "../api/queries";
import { IconCheck } from "../components/icons";
import { QueryView } from "../components/states";
import { Alert, Card, Field, Page, Segmented } from "../components/ui";

type Settings = Schemas["AppSettings"];
type Engine = Settings["rating_engine"];

const ABOUT: Record<Engine, { what: string; how: string }> = {
  comfort: {
    what: "Each skill from 0 to 100 against what is typical at your comfort level (50 = typical).",
    how: "Uses your best play per map and mod setup. A skill your maps haven't challenged shows as \"at least\".",
  },
  irt: {
    what: "Each skill in stars, on the same scale as map difficulty, with a range for how sure it is.",
    how: "Fitted from every note you hit or missed against how hard it was. Experimental: the numbers may still change.",
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
    <Card title="Rating engine" hint="How your skill ratings are worked out. Every page that shows skills follows this choice.">
      <div className="stack" style={{ gap: 12 }}>
        <Field label="Engine">
          <Segmented
            label="Rating engine"
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
