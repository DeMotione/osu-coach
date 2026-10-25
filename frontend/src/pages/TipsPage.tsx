import { useState } from "react";

import type { Schemas } from "../api/client";
import { useSaveSetup, useSettings, useSetup, useTips } from "../api/queries";
import { DataTable } from "../components/DataTable";
import { IconSliders } from "../components/icons";
import { SetupDetails, setupToSave, type Setup } from "../components/SetupForm";
import { EmptyState, QueryView } from "../components/states";
import { Alert, Badge, Card, Field, Hint, Page, Segmented, Stat, Tiles } from "../components/ui";
import { signed } from "../lib/format";
import { Md } from "../lib/markdown";

type Tip = Schemas["TipOut"];

const SEVERITY: Record<number, [string, "bad" | "warn" | "muted"]> = {
  3: ["High impact", "bad"],
  2: ["Medium impact", "warn"],
  1: ["Nice to know", "muted"],
};

export default function TipsPage() {
  const q = useTips();
  const setup = useSetup();
  const settings = useSettings();
  return (
    <Page title="Tips & Setup">
      {/* the setup doesn't need analysed replays: what was entered (here or in the setup guide) is always shown */}
      {setup.data && settings.data && <SetupCard key={JSON.stringify(setup.data)} setup={setup.data} open={!settings.data.setup_saved} />}
      <QueryView query={q}>
        {(page) => (
          <>
            <CalibrationCard page={page} />
            <Card title="Tips" hint="Red = biggest impact, orange = medium, grey = nice to know.">
              {page.tips.length ? (
                <div className="stack">{page.tips.map((t, i) => <TipCard key={`${t.title}-${i}`} tip={t} />)}</div>
              ) : (
                <Alert tone="good">No clear problems found in these replays. Keep playing and re-analyse later.</Alert>
              )}
            </Card>
            <Card title="Practice plan" hint="A simple daily routine built around your weakest skills.">
              <ol className="list list--steps">
                {page.practice_plan.map((s) => (
                  <li key={s}>
                    <Md>{s}</Md>
                  </li>
                ))}
              </ol>
            </Card>
          </>
        )}
      </QueryView>
    </Page>
  );
}

// ------------------------------------------------------------------ setup
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
            <Hint text="Makes the tips concrete: tablet area, sensitivity, keyboard / SayoDevice. Click the title to open or fold it." />
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

// ------------------------------------------------------------------ calibration
function CalibrationCard({ page }: { page: Schemas["TipsPage"] }) {
  const c = page.calibration;
  const a = page.tablet_area;
  const mm = (v: number | null) => (v === null ? "–" : `${+v.toFixed(2)}`);
  return (
    <Card
      title="Aim calibration → your setup"
      hint="From the Aim page: how far you move compared with the jumps. Over 4% too far or too short means the tablet area / sensitivity should change; within ±4% keep it."
    >
      {!c ? (
        <EmptyState title="Not enough jumps yet">The calibration needs 40+ jumps.</EmptyState>
      ) : (
        <div className="split">
          <div className="stack">
            <Tiles n={3}>
              <Stat label="Movement vs jumps" value={signed((c.scale - 1) * 100, 1, "%")} hint="+ = you move too far (overaim), − = not far enough (underaim)." />
              <Stat
                label="Change"
                value={!c.step ? "keep" : c.device === "tablet" ? signed(c.step * 100, 0, "% area") : signed((1 / c.scale - 1) * 100, 0, "% sens.")}
                hint="Tablet: + = larger area (less sensitive). Mouse: − = lower sensitivity."
              />
              <Stat label="Try" value={<span style={{ fontSize: 15 }}>{c.suggested ?? "–"}</span>} note={c.now ? `now ${c.now}` : "enter your setup"} />
            </Tiles>
            <ul className="list list--bullets">{c.lines.map((l) => <li key={l}>{l}</li>)}</ul>
          </div>
          <div className="stack">
            <h3 className="section__title">Tablet area to try — OpenTabletDriver values; X / Y = the centre of the area</h3>
            {a ? (
              <>
                <DataTable
                  label="Tablet area to try"
                  rows={[
                    ["Width", a.now_w, a.w],
                    ["Height", a.now_h, a.h],
                    ["X (centre)", a.now_x, a.x],
                    ["Y (centre)", a.now_y, a.y],
                  ] as [string, number | null, number | null][]}
                  rowKey={(r) => r[0]}
                  columns={[
                    { key: "s", header: "Setting", cell: (r) => r[0], strong: true },
                    { key: "now", header: "Now (mm)", cell: (r) => mm(r[1]), align: "right" },
                    { key: "try", header: "Try (mm)", cell: (r) => (r[1] !== r[2] ? <strong>{mm(r[2])}</strong> : mm(r[2])), align: "right" },
                  ]}
                />
                <p className="small muted">
                  {a.why.join("; ").replace(/^./, (x) => x.toUpperCase())}.
                  {a.now_x === null || a.now_y === null ? " Enter X / Y in your setup to get the position too." : ""}
                </p>
              </>
            ) : (
              <EmptyState title={page.setup.device === "tablet" ? "Enter your tablet area" : "Mouse setup"}>
                {page.setup.device === "tablet"
                  ? "With your area width and height (and X / Y) in Your setup, this shows the exact area to try."
                  : "For a mouse, the change is a sensitivity / DPI value — see Try on the left."}
              </EmptyState>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

// ------------------------------------------------------------------ tips
function TipCard({ tip }: { tip: Tip }) {
  const [label, tone] = SEVERITY[tip.severity] ?? ["", "muted"];
  const show = (v: number | boolean) => (typeof v === "boolean" ? (v ? "on" : "off") : `${v.toFixed(2)} mm`);
  return (
    <article className={`tip tip--${tip.severity}`}>
      <div className="tip__head">
        <Badge tone={tone}>{label}</Badge>
        <h3 className="tip__title">{tip.title}</h3>
        <span className="tip__category">{tip.category}</span>
      </div>
      <div className="tip__body">
        <p>{tip.evidence}</p>
        {tip.sayo && (
          <DataTable
            label="SayoDevice settings"
            rows={tip.sayo}
            rowKey={(r) => r.setting}
            columns={[
              { key: "s", header: "Setting", cell: (r) => r.setting, strong: true },
              { key: "now", header: "Now", cell: (r) => show(r.now), align: "right" },
              { key: "try", header: "Try", cell: (r) => (r.changed ? <strong style={{ color: "var(--accent)" }}>{show(r.suggested)} ← change</strong> : show(r.suggested)), align: "right" },
            ]}
          />
        )}
        {tip.actions.length > 0 && (
          <ul className="list list--bullets">
            {tip.actions.map((a) => (
              <li key={a}>
                <Md>{a}</Md>
              </li>
            ))}
          </ul>
        )}
        {tip.settings.length > 0 && (
          <p className="small muted">
            Suggested values:{" "}
            {tip.settings.map((s, i) => (
              <span key={s.name}>
                {i > 0 && " · "}
                <code>{s.name}</code> = {s.value}
              </span>
            ))}
          </p>
        )}
      </div>
    </article>
  );
}
