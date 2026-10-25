import { useState } from "react";

import type { Schemas } from "../api/client";
import { useSaveSetup, useSettings, useSetup, useSetupTips } from "../api/queries";
import { IconCheck, IconSliders } from "../components/icons";
import { SetupDetails, setupToSave, type Setup } from "../components/SetupForm";
import { QueryView } from "../components/states";
import { Alert, Card, Field, Hint, Page, Segmented } from "../components/ui";

type Advice = Schemas["SetupAdvice"];

export default function SetupTipsPage() {
  const q = useSetupTips();
  const setup = useSetup();
  const settings = useSettings();
  return (
    <Page title="Setup Tips">
      <QueryView query={q}>{(page) => <AdviceCard advice={page.advice} />}</QueryView>
      {/* the setup doesn't need analysed replays: what was entered (here or in the setup guide) is always shown */}
      {setup.data && settings.data && <SetupCard key={JSON.stringify(setup.data)} setup={setup.data} open={!settings.data.setup_saved} />}
    </Page>
  );
}

/** What to change in the setup, with the exact values, and what to keep. */
function AdviceCard({ advice }: { advice: Advice[] }) {
  const changes = advice.filter((a) => a.verdict === "change");
  const rest = advice.filter((a) => a.verdict !== "change");
  return (
    <Card
      title="Setup tips"
      hint="A change shows up only when it is big enough to feel and your misses show it costs you; then you get the exact new value. Everything else: keep it."
    >
      <p className="setup-verdict">
        {changes.length ? `${changes.length} ${changes.length === 1 ? "change" : "changes"} to try` : "Your setup fits: nothing to change."}
      </p>
      {changes.map((a) => (
        <ChangeItem key={a.key} advice={a} />
      ))}
      <ul className="setup-rows">
        {rest.map((a) => (
          <li key={a.key} className={`setup-row setup-row--${a.verdict}`}>
            <span className="setup-row__mark" aria-label={a.verdict === "keep" ? "keep" : "not enough data yet"}>
              {a.verdict === "keep" ? <IconCheck /> : "?"}
            </span>
            <span className="setup-row__title">{a.title}</span>
            <span className="setup-row__why">{a.why}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function ChangeItem({ advice: a }: { advice: Advice }) {
  return (
    <section className="setup-change">
      <h3 className="setup-change__title">{a.title}</h3>
      <p className="setup-change__why">{a.why}</p>
      <ul className="setup-change__values">
        {a.changes.map((c) => (
          <li key={c.setting}>
            <span className="setup-change__setting">{c.setting}</span>
            {c.now && (
              <>
                <span className="setup-change__now">{c.now}</span>
                <span aria-hidden="true">→</span>
              </>
            )}
            <strong className="setup-change__to">{c.to}</strong>
          </li>
        ))}
      </ul>
      {a.where && <p className="small muted">{a.where}</p>}
    </section>
  );
}

/** What the player plays with: the devices and their settings, shared with the setup guide. */
function SetupCard({ setup, open }: { setup: Setup; open: boolean }) {
  const [s, setS] = useState<Setup>(setup);
  const save = useSaveSetup();
  const set = <K extends keyof Setup>(k: K, v: Setup[K]) => setS((x) => ({ ...x, [k]: v }));
  return (
    <details className="card disclosure-card" open={open}>
      <summary className="card__head">
        <div>
          <h2 className="card__title">
            <IconSliders width={16} height={16} style={{ verticalAlign: "-3px", marginRight: 8 }} />
            Your setup
            <Hint text="Makes the setup tips exact: your tablet area, sensitivity, keyboard / SayoDevice values. Click the title to open or fold it." />
          </h2>
        </div>
      </summary>
      <div className="card__body">
        <div className="split">
          <Field label="Aim with">
            <Segmented label="Aim with" block value={s.device} onChange={(v) => set("device", v)} options={[{ value: "tablet", label: "Tablet" }, { value: "mouse", label: "Mouse" }]} />
          </Field>
          <Field label="Keys">
            <Segmented
              label="Keys"
              block
              value={s.keyboard}
              onChange={(v) => set("keyboard", v)}
              options={[
                { value: "standard", label: "Keyboard" },
                { value: "rapid_trigger", label: "Rapid trigger" },
                { value: "sayo", label: "SayoDevice" },
              ]}
            />
          </Field>
        </div>
        <SetupDetails value={s} onChange={(patch) => setS((x) => ({ ...x, ...patch }))} />
        {save.isError && <Alert tone="bad">{save.error.message}</Alert>}
        <div className="btn-row">
          <button type="button" className="btn btn--primary" disabled={save.isPending} onClick={() => save.mutate(setupToSave(s))}>
            {save.isPending ? "Saving…" : "Save setup"}
          </button>
        </div>
      </div>
    </details>
  );
}
