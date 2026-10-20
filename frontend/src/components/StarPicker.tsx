import { useId, type CSSProperties } from "react";

import type { TargetOption } from "../lib/starCompare";
import { starColor, starGlow, starTextColor } from "../lib/starColors";
import { IconLock } from "./icons";

/** Star ratings to pick from, each in osu!'s colour for it; from 9★ they glow gold, locked ones are greyed out. */
export function StarPicker({
  options,
  value,
  onChange,
  label,
}: {
  options: TargetOption[];
  value: number;
  onChange: (v: number) => void;
  label: string;
}) {
  const name = useId();
  return (
    <div className="star-picker" role="radiogroup" aria-label={label}>
      {options.map((o) => {
        const glow = starGlow(o.value);
        const style = { "--star": starColor(o.value), "--star-text": starTextColor(o.value), "--glow": glow } as CSSProperties;
        const cls = [
          "star-picker__option",
          o.value === value && "checked",
          o.disabled && "locked",
          o.comfort && "comfort",
          glow > 0 && "milestone",
        ]
          .filter(Boolean)
          .join(" ");
        const spoken = o.title ? `${o.label}, ${o.title}` : o.disabled ? `${o.label}, locked` : o.label;
        return (
          <label key={o.value} className={cls} style={style} title={o.title}>
            <input
              type="radio"
              name={name}
              checked={o.value === value}
              disabled={o.disabled}
              aria-label={spoken}
              onChange={() => onChange(o.value)}
            />
            {o.disabled && <IconLock />}
            {o.label}
          </label>
        );
      })}
    </div>
  );
}
