/* eslint-disable react-refresh/only-export-components -- the form and the shape it saves in belong together */
/** The player's setup as a form: shared by Tips & Setup and the first-start setup guide, so both ask the same. */
import type { Schemas } from "../api/client";
import { Field, Segmented, Switch } from "./ui";

export type Setup = Schemas["SetupModel"];
export type SetupPatch = Partial<Setup>;

export function NumberField({ label, value, onChange, step, min, max, hint, placeholder = "unknown" }: {
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

/**
 * Everything after the aim device and the keys: hand, screen, tablet area or mouse sensitivity, and the values of a
 * rapid-trigger keyboard or a SayoDevice. ``client``: also ask for the osu! client (the guide asks for it earlier).
 */
export function SetupDetails({ value: s, onChange, client = true }: { value: Setup; onChange: (patch: SetupPatch) => void; client?: boolean }) {
  const num = (k: keyof Setup) => (v: number | null) => onChange({ [k]: v });
  return (
    <>
      <div className="form-grid">
        <div className={client ? undefined : "span-2"}>
          <Field label="Pen / mouse hand">
            <Segmented label="Hand" block value={s.handedness} onChange={(v) => onChange({ handedness: v })} options={[{ value: "right", label: "Right" }, { value: "left", label: "Left" }]} />
          </Field>
        </div>
        {client && (
          <Field label="osu! client">
            <Segmented label="osu! client" block value={s.client} onChange={(v) => onChange({ client: v })} options={[{ value: "stable", label: "stable" }, { value: "lazer", label: "lazer" }]} />
          </Field>
        )}
        <NumberField label="Screen width (px)" value={s.screen_w_px} onChange={(v) => onChange({ screen_w_px: v ?? 1920 })} step={1} min={640} max={7680} placeholder="1920" />
        <NumberField label="Screen height (px)" value={s.screen_h_px} onChange={(v) => onChange({ screen_h_px: v ?? 1080 })} step={1} min={480} max={4320} placeholder="1080" />
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
            onChange={(v) => onChange({ rt_press_mm: v, rt_release_mm: v })}
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
                    onChange={(v) => onChange({ [key]: v })}
                  />
                </div>
              ) : (
                <NumberField key={key} label={`${label} (mm)`} hint={hint} value={s[key] as number | null} onChange={num(key)} step={0.05} min={0} max={6} />
              ),
            )}
          </div>
        </div>
      )}
    </>
  );
}

/** The setup as it is saved: rapid trigger counts as on for a SayoDevice until it is switched off. */
export const setupToSave = (s: Setup): Schemas["SetupUpdate"] => ({ ...s, sayo_rt: s.keyboard === "sayo" ? s.sayo_rt ?? true : s.sayo_rt });
