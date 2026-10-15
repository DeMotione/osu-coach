import { useState } from "react";

import { Card, Field } from "./ui";

export interface RecommendationOptions {
  skill?: string;
  assessed?: string;
  ratings?: string;
  comfort?: number;
  kappa?: number;
  min_relevance?: number;
  exclude_played?: boolean;
}

const SKILLS = [
  ["aim", "Jump aim"], ["flow_aim", "Flow aim"], ["speed", "Tapping speed"],
  ["stamina", "Stamina"], ["accuracy", "Accuracy"], ["sliders", "Slider control"],
  ["reading", "Reading"], ["consistency", "Consistency"],
] as const;

/** Keep goal selection prominent; put the experimental tuning knobs together. */
export function RecommendationControls({ current, abilities, comfort, onApply }: {
  current: string;
  abilities: Record<string, number>;
  comfort: number;
  onApply: (options: RecommendationOptions) => void;
}) {
  const [skill, setSkill] = useState(current);
  const [assessed, setAssessed] = useState<string[] | null>(null);
  const [ratings, setRatings] = useState<Record<string, string>>({});
  const [starsOverride, setStarsOverride] = useState<string | null>(null);
  const stars = starsOverride ?? String(comfort);
  const [kappa, setKappa] = useState("0.5");
  const [relevance, setRelevance] = useState("0.3");
  const [excludePlayed, setExcludePlayed] = useState(true);
  const checked = assessed ?? Object.keys(abilities).filter((key) => SKILLS.some(([id]) => id === key));
  const included = checked.includes(skill) ? checked : [skill, ...checked];
  const valid = Number(stars) > 0 && Number(kappa) >= 0 && Number(relevance) >= 0 && Number(relevance) <= 1 &&
    [stars, kappa, relevance].every((n) => n.trim() !== "" && Number.isFinite(Number(n))) &&
    Object.values(ratings).every((n) => n.trim() === "" || (Number.isFinite(Number(n)) && Number(n) >= 0 && Number(n) <= 100));
  return (
    <Card title="Choose your practice target" sub="Results update when you apply these choices. The target skill is always assessed.">
      <div className="controls">
        <Field label="Target skill">
          <select className="select" value={skill} onChange={(e) => setSkill(e.target.value)}>
            {SKILLS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </Field>
        <button type="button" className="btn" disabled={!valid} onClick={() => onApply({
          skill, assessed: included.join(","),
          ratings: JSON.stringify(Object.fromEntries(Object.entries(ratings).filter(([, n]) => n.trim() !== "").map(([key, n]) => [key, Number(n)]))),
          comfort: starsOverride !== null ? Number(stars) : undefined,
          kappa: Number(kappa), min_relevance: Number(relevance), exclude_played: excludePlayed,
        })}>Show maps</button>
      </div>
      <details style={{ marginTop: 14 }}>
        <summary>Adjust scoring and player ratings</summary>
        <p className="small muted">Experimental defaults: warm-up −1★ / −15 demand, comfort 0★ / −5, push +0.3★ / +5; star window ±0.2★, star scale 0.2★, demand scale 20, bottleneck weight 1 and history weight 0.5. History is neutral (H=1) until measured. Pool demand uses 20 points per star plus feature weights against nearby pool medians: aim, flow, sliders, reading and consistency 12; speed 20; stamina and accuracy 15. F(m) compares maps within one goal.</p>
        <div className="controls">
          <Field label="Comfort stars"><input className="input" type="number" min="0.1" step="0.1" value={stars} onChange={(e) => setStarsOverride(e.target.value)} /></Field>
          <Field label="Skill star adjustment κₛ (stars)"><input className="input" type="number" min="0" step="0.1" value={kappa} onChange={(e) => setKappa(e.target.value)} /></Field>
          <Field label="Minimum target-skill relevance"><input className="input" type="number" min="0" max="1" step="0.05" value={relevance} onChange={(e) => setRelevance(e.target.value)} /></Field>
        </div>
        <p className="small muted">Demand skills to assess. Unchecked demands are unassessed. A checked demand with unknown player ability excludes the map.</p>
        <div className="controls">
          {SKILLS.map(([id, label]) => (
            <label key={id} className="small" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <input type="checkbox" checked={included.includes(id)} disabled={id === skill} onChange={(e) => setAssessed(
                e.target.checked ? [...included, id] : included.filter((value) => value !== id),
              )} /> {label}
            </label>
          ))}
        </div>
        <p className="small muted">Supply player ratings manually (0–100). Blank keeps the replay rating, or unknown if no rating was measured.</p>
        <div className="controls">
          {SKILLS.map(([id, label]) => (
            <Field key={id} label={`${label} · ${abilities[id] === undefined ? "unknown" : `current ${abilities[id].toFixed(0)}`}`}>
              <input className="input" type="number" min="0" max="100" step="1" placeholder={abilities[id] === undefined ? "Unknown" : String(Math.round(abilities[id]))}
                value={ratings[id] ?? ""} onChange={(e) => setRatings({ ...ratings, [id]: e.target.value })} />
            </Field>
          ))}
        </div>
        <label className="small" style={{ display: "inline-flex", alignItems: "center", gap: 6, marginTop: 10 }}>
          <input type="checkbox" checked={excludePlayed} onChange={(e) => setExcludePlayed(e.target.checked)} />
          Exclude maps already present in this player's replay dataset
        </label>
      </details>
    </Card>
  );
}
