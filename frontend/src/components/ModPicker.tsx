import type { Schemas } from "../api/client";
import { MAX_RATE, MIN_RATE, MOD_PARTS, modsText, toggleMods } from "../lib/playGoals";

type Mods = NonNullable<Schemas["PlayGoalRequest"]["mods"]>;

/** Toggle buttons that build one mod combination; with allowNone, no button on means NM. With ``onRate``, DT has a
 * speed (lazer's custom speeds; empty: DT's own 1.50×), which goes when DT does. */
export function ModPicker({ label, value, onChange, allowNone = false, rate, onRate }: {
  label: string;
  value: Mods;
  onChange: (value: Mods) => void;
  allowNone?: boolean;
  rate?: number | null;
  onRate?: (rate: number | null) => void;
}) {
  return (
    <div className="field">
      <span className="field__label">{label}</span>
      <div className="modpicker" role="group" aria-label={label}>
        {MOD_PARTS.map((p) => {
          const blocked = "blocked" in p ? p.blocked : undefined;
          return (
            <span key={p.value} title={blocked ?? p.label}>
              <button type="button" className="modpicker__chip" disabled={!!blocked} aria-pressed={value.includes(p.value)}
                onClick={() => {
                  const next = toggleMods(value, p.value, !value.includes(p.value), allowNone);
                  onChange(next);
                  if (onRate && rate != null && !next.includes("DT")) onRate(null);
                }}>
                {p.value}
              </button>
            </span>
          );
        })}
        {onRate && value.includes("DT") && (
          <label className="modpicker__speed">
            Speed ×
            <input className="input" type="number" inputMode="decimal" step={0.01} min={MIN_RATE} max={MAX_RATE} placeholder="1.50"
              value={rate ?? ""} onChange={(e) => onRate(e.target.value === "" ? null : Number(e.target.value))} />
          </label>
        )}
        <span className="modpicker__result">{value === "NM" ? "No mods" : modsText(value, rate)}</span>
      </div>
    </div>
  );
}
