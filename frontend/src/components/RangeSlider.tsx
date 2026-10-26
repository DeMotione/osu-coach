import type { CSSProperties } from "react";

/** A slider with two handles for a range ``[low, high]`` of ``min``–``max``; the handles can't cross. */
export function RangeSlider({ min, max, step, value: [low, high], onChange, label, format }: {
  min: number;
  max: number;
  step: number;
  value: [number, number];
  onChange: (value: [number, number]) => void;
  label: string;
  format: (v: number) => string;
}) {
  const at = (v: number) => (max > min ? ((v - min) / (max - min)) * 100 : 0);
  return (
    <div className="labelled range-slider" role="group" aria-label={label}>
      <div className="labelled__head">
        <span className="field__label">{label}</span>
        <span className="labelled__value">
          {format(low)} – {format(high)}
        </span>
      </div>
      <div className="range-slider__track" style={{ "--low": `${at(low)}%`, "--high": `${at(high)}%` } as CSSProperties}>
        {/* both handles at the top end: the low one on top, or it couldn't be moved */}
        <input type="range" min={min} max={max} step={step} value={low} aria-label="Lowest" aria-valuetext={format(low)}
          style={low === high && at(low) > 50 ? { zIndex: 2 } : undefined}
          onChange={(e) => onChange([Math.min(Number(e.target.value), high), high])} />
        <input type="range" min={min} max={max} step={step} value={high} aria-label="Highest" aria-valuetext={format(high)}
          onChange={(e) => onChange([low, Math.max(Number(e.target.value), low)])} />
      </div>
    </div>
  );
}
