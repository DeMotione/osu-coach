import { useState } from "react";

import type { Schemas } from "../api/client";
import { useSaveSetup, useTips } from "../api/queries";
import { DataTable } from "../components/DataTable";
import { IconSliders } from "../components/icons";
import { EmptyState, QueryView } from "../components/states";
import { Alert, Badge, Card, Field, Page, Segmented, Stat, Switch, Tiles } from "../components/ui";
import { signed } from "../lib/format";
import { Md } from "../lib/markdown";

type Setup = Schemas["SetupModel"];
type Tip = Schemas["TipOut"];

const SEVERITY: Record<number, [string, "bad" | "warn" | "muted"]> = {
  3: ["High impact", "bad"],
  2: ["Medium impact", "warn"],
  1: ["Nice to know", "muted"],
};

export default function TipsPage() {
  const q = useTips();
  return (
    <Page
      title="Tips & Setup"
      sub="Concrete tips from your numbers, most important first — each with the evidence it is based on — and setup changes to try (tablet area / sensitivity, keys)."
    >
      <QueryView query={q}>
        {(page) => (
          <>
            <SetupCard key={JSON.stringify(page.setup)} setup={page.setup} open={!page.setup_saved} />
            <CalibrationCard page={page} />
            <Card title="Tips" sub="Red = biggest impact, orange = medium, grey = nice to know.">
              {page.tips.length ? (
                <div className="stack">{page.tips.map((t, i) => <TipCard key={`${t.title}-${i}`} tip={t} />)}</div>
              ) : (
                <Alert tone="good">No clear problems found in these replays. Keep playing and re-analyse later.</Alert>
              )}
            </Card>
            <Card title="Practice plan" sub="A simple daily routine built around your weakest skills.">
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
type NumKey = { [K in keyof Setup]-?: Setup[K] extends number | null | undefined ? K : never }[keyof Setup];

function NumberField({ label, value, onChange, step, min, max, hint, placeholder = "unknown" }: {
  label: string;
  value: number | null | undefined;
  onChange: (v: number | null) => void;
  step: number;
  min: number;
  max: number;
  hint?: string;
  placeholder?: string;
}) {
  return (
    <Field label={label} hint={hint}>
      <input
        className="input"
        type="number"
        inputMode="decimal"
        step={step}
        min={min}
        max={max}
        placeholder={placeholder}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      />
    </Field>
  );
}

const SAYO: [string, keyof Setup, "mm" | "toggle", string][][] = [
  [
    ["Stroke", "sayo_stroke_mm", "mm", "Full travel of your switches (4.0 mm for most magnetic switches)."],
    ["Trigger", "sayo_trigger_mm", "mm", "Fixed press depth (actuation point)."],
    ["Release", "sayo_release_mm", "mm", "Fixed reset depth — must be above (smaller than) Trigger."],
  ],
  [
    ["RT Mode", "sayo_rt", "toggle", "Rapid trigger on/off."],
    ["RT Trigger", "sayo_rt_trigger_mm", "mm", "Inside the RT zone: press again after moving down this far (≤ RT Release)."],
    ["RT Release", "sayo_rt_release_mm", "mm", "Inside the RT zone: release after moving up this far."],
  ],
  [
    ["Full Stroke", "sayo_full_stroke", "toggle", "Rapid trigger over the whole stroke (ignores the bounds)."],
    ["RT Upper Bound", "sayo_rt_upper_mm", "mm", "Depth where rapid trigger starts working."],
    ["RT Lower Bound", "sayo_rt_lower_mm", "mm", "Depth where rapid trigger stops working (keep it a bit above the full stroke)."],
  ],
];

function SetupCard({ setup, open }: { setup: Setup; open: boolean }) {
  const [s, setS] = useState<Setup>(setup);
  const save = useSaveSetup();
  const set = <K extends keyof Setup>(k: K, v: Setup[K]) => setS((x) => ({ ...x, [k]: v }));
  const num = (k: NumKey) => (v: number | null) => set(k, v as Setup[typeof k]);
  return (
    <details className="card disclosure-card" open={open}>
      <summary className="card__head">
        <div>
          <h2 className="card__title">
            <IconSliders width={16} height={16} style={{ verticalAlign: "-3px", marginRight: 8 }} />
            Your setup
          </h2>
          <p className="card__sub">Makes the tips concrete: tablet area, sensitivity, keyboard / SayoDevice. Click to {open ? "fold" : "edit"}.</p>
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
        <div className="form-grid">
          <Field label="Pen / mouse hand">
            <Segmented label="Hand" block value={s.handedness} onChange={(v) => set("handedness", v)} options={[{ value: "right", label: "Right" }, { value: "left", label: "Left" }]} />
          </Field>
          <Field label="osu! client">
            <Segmented label="osu! client" block value={s.client} onChange={(v) => set("client", v)} options={[{ value: "stable", label: "stable" }, { value: "lazer", label: "lazer" }]} />
          </Field>
          <NumberField label="Screen width (px)" value={s.screen_w_px} onChange={(v) => set("screen_w_px", v ?? 1920)} step={1} min={640} max={7680} placeholder="1920" />
          <NumberField label="Screen height (px)" value={s.screen_h_px} onChange={(v) => set("screen_h_px", v ?? 1080)} step={1} min={480} max={4320} placeholder="1080" />
          {s.device === "tablet" ? (
            <>
              <NumberField label="Area width (mm)" value={s.area_w_mm} onChange={num("area_w_mm")} step={1} min={0} max={500} />
              <NumberField label="Area height (mm)" value={s.area_h_mm} onChange={num("area_h_mm")} step={1} min={0} max={500} />
              <NumberField label="Area X (mm)" value={s.area_x_mm} onChange={num("area_x_mm")} step={0.1} min={0} max={500} hint="Where the area sits on the tablet: OpenTabletDriver → Output → X (the centre of the area)." />
              <NumberField label="Area Y (mm)" value={s.area_y_mm} onChange={num("area_y_mm")} step={0.1} min={0} max={500} hint="OpenTabletDriver → Output → Y." />
            </>
          ) : (
            <>
              <div className="span-2">
                <NumberField label="Mouse DPI" value={s.mouse_dpi} onChange={num("mouse_dpi")} step={50} min={0} max={50000} />
              </div>
              <div className="span-2">
                <NumberField label="osu! sensitivity" value={s.ingame_sens} onChange={num("ingame_sens")} step={0.05} min={0} max={10} placeholder="1.0" />
              </div>
            </>
          )}
        </div>
        {s.keyboard === "rapid_trigger" && (
          <div className="split">
            <NumberField label="Actuation point (mm)" value={s.actuation_mm} onChange={num("actuation_mm")} step={0.05} min={0} max={4} />
            <NumberField
              label="Rapid-trigger sensitivity (mm)"
              value={s.rt_release_mm}
              onChange={(v) => setS((x) => ({ ...x, rt_press_mm: v, rt_release_mm: v }))}
              step={0.05}
              min={0}
              max={2}
            />
          </div>
        )}
        {s.keyboard === "sayo" && (
          <div className="section">
            <h3 className="section__title">SayoDevice — the values from its configurator (sayodevice.com → Key stroke); leave empty what you don't know</h3>
            <div className="sayo-grid">
              {SAYO.flat().map(([label, key, kind, hint]) =>
                kind === "toggle" ? (
                  <div key={key} className="field sayo-toggle">
                    <Switch
                      label={label}
                      hint={hint}
                      checked={key === "sayo_rt" ? s.sayo_rt ?? true : !!s[key]}
                      onChange={(v) => set(key, v as Setup[typeof key])}
                    />
                  </div>
                ) : (
                  <NumberField key={key} label={`${label} (mm)`} hint={hint} value={s[key] as number | null} onChange={(v) => set(key, v as Setup[typeof key])} step={0.05} min={0} max={6} />
                ),
              )}
            </div>
          </div>
        )}
        {save.isError && <Alert tone="bad">{save.error.message}</Alert>}
        <div className="btn-row">
          <button
            type="button"
            className="btn btn--primary"
            disabled={save.isPending}
            onClick={() => save.mutate({ ...s, sayo_rt: s.keyboard === "sayo" ? s.sayo_rt ?? true : s.sayo_rt })}
          >
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
      sub="From the Aim page: how far you move compared with the jumps. Over 4% too far or too short means the tablet area / sensitivity should change; within ±4% keep it."
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
