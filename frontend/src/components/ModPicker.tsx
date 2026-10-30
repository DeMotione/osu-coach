import type { Schemas } from "../api/client";
import { MOD_PARTS, toggleMods } from "../lib/playGoals";

type Mods = NonNullable<Schemas["PlayGoalRequest"]["mods"]>;

/** Toggle buttons that build one mod combination; with allowNone, no button on means NM. */
export function ModPicker({ label, value, onChange, allowNone = false }: {
  label: string;
  value: Mods;
  onChange: (value: Mods) => void;
  allowNone?: boolean;
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
                onClick={() => onChange(toggleMods(value, p.value, !value.includes(p.value), allowNone))}>
                {p.value}
              </button>
            </span>
          );
        })}
        <span className="modpicker__result">{value === "NM" ? "No mods" : `+${value}`}</span>
      </div>
    </div>
  );
}
