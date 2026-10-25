import { useId, useState } from "react";

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

/** Draft every control locally; the one Show maps action applies the complete selection. */
export function RecommendationControls({ current, measured, comfort, onApply }: {
  current: string;
  measured: Record<string, number>;
  comfort: number;
  onApply: (options: RecommendationOptions) => void;
}) {
  const [skill, setSkill] = useState(current);
  const [panel, setPanel] = useState<"fine" | "ratings" | null>(null);
  const panelId = useId();
  const [assessed, setAssessed] = useState<string[] | null>(null);
  const [ratings, setRatings] = useState<Record<string, string>>({});
  const [starsOverride, setStarsOverride] = useState<string | null>(null);
  const stars = starsOverride ?? comfort.toFixed(2);
  const [kappa, setKappa] = useState("0.5");
  const [relevance, setRelevance] = useState("0.3");
  const [excludePlayed, setExcludePlayed] = useState(true);
  const selected = [skill, ...(assessed ?? []).filter((id) => id !== skill)];
  const valid = Number(stars) > 0 && Number(kappa) >= 0 && Number(relevance) >= 0 && Number(relevance) <= 1 &&
    [stars, kappa, relevance].every((n) => n.trim() !== "" && Number.isFinite(Number(n))) &&
    Object.values(ratings).every((n) => n.trim() === "" || (Number.isFinite(Number(n)) && Number(n) >= 0 && Number(n) <= 100));

  const showMaps = () => {
    const manual = Object.fromEntries(Object.entries(ratings).filter(([, value]) => value.trim() !== "")
      .map(([key, value]) => [key, Number(value)]));
    onApply({
      skill,
      assessed: selected.join(","),
      ratings: Object.keys(manual).length ? JSON.stringify(manual) : undefined,
      comfort: starsOverride !== null ? Number(stars) : undefined,
      kappa: Number(kappa),
      min_relevance: Number(relevance),
      exclude_played: excludePlayed,
    });
  };

  return (
    <Card className="recommendation-controls" title="Choose your practice target" hint="Pick a skill, then explore the warm-up, comfort, and push map tables below.">
      <div className="recommendation-target">
        <Field label="Target skill">
          <select className="select" value={skill} onChange={(event) => {
            setAssessed((previous) => previous?.filter((id) => id !== skill) ?? null);
            setSkill(event.target.value);
          }}>
            {SKILLS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </Field>
        <button type="button" className="btn btn--primary" disabled={!valid} onClick={showMaps}>Show maps</button>
      </div>

      <div className="recommendation-modes">
        <button type="button" className={panel === "fine" ? "recommendation-mode active" : "recommendation-mode"}
          aria-expanded={panel === "fine"} aria-controls={panelId} onClick={() => setPanel(panel === "fine" ? null : "fine")}>⚙ Fine-tune</button>
        <button type="button" className={panel === "ratings" ? "recommendation-mode active" : "recommendation-mode"}
          aria-expanded={panel === "ratings"} aria-controls={panelId} onClick={() => setPanel(panel === "ratings" ? null : "ratings")}>Try other skill ratings</button>
      </div>

      {panel && <div className="recommendation-panel" id={panelId} role="region" aria-label={panel === "fine" ? "Fine-tune" : "Skill ratings"}>
        <div className="recommendation-panel__head">
          <h3>{panel === "fine" ? "Fine-tune" : "Try other skill ratings"}</h3>
          <button type="button" className="recommendation-close" aria-label="Close settings" onClick={() => setPanel(null)}>×</button>
        </div>
        {panel === "fine" ? <>
          <div className="recommendation-grid">
            <Field label="Comfort difficulty" help="Your starting difficulty in stars.">
              <input className="input" type="number" min="0.1" step="0.01" value={stars} onChange={(event) => setStarsOverride(event.target.value)} />
            </Field>
            <Field label="Skill star adjustment κₛ (stars)" help="How much your skill rating shifts the star target.">
              <input className="input" type="number" min="0" step="0.1" value={kappa} onChange={(event) => setKappa(event.target.value)} />
            </Field>
            <Field label="Minimum target-skill relevance" help="Only maps with at least this much material for the target skill (0–1).">
              <input className="input" type="number" min="0" max="1" step="0.05" value={relevance} onChange={(event) => setRelevance(event.target.value)} />
            </Field>
          </div>
          <label className="recommendation-check">
            <input type="checkbox" checked={excludePlayed} onChange={(event) => setExcludePlayed(event.target.checked)} />
            Hide maps I have already completed
          </label>
          <div className="recommendation-assessed">
            <h4>Skills to assess</h4>
            <p className="small muted">The target skill is always included. Unchecked demands are unassessed; a checked skill with unknown player ability excludes the map.</p>
            <div className="recommendation-skills">
              {SKILLS.map(([id, label]) => (
                <label key={id} className="recommendation-check">
                  <input type="checkbox" checked={selected.includes(id)} disabled={id === skill} onChange={(event) => setAssessed(
                    event.target.checked ? [...selected, id] : selected.filter((value) => value !== id),
                  )} />
                  {label}{id === skill ? " · target" : ""}
                </label>
              ))}
            </div>
          </div>
        </> : <>
          <p className="small muted">Measured values come from your replay analysis. Edits override them for the next search; blank keeps the measured value or unknown.</p>
          <div className="recommendation-grid recommendation-grid--ratings">
            {SKILLS.map(([id, label]) => (
              <Field key={id} label={label} help={`Measured: ${measured[id] === undefined ? "unknown" : measured[id].toFixed(0)}`}>
                <input className="input" type="number" min="0" max="100" step="1"
                  value={ratings[id] ?? (measured[id] === undefined ? "" : String(Math.round(measured[id])))}
                  onChange={(event) => setRatings({ ...ratings, [id]: event.target.value })} />
              </Field>
            ))}
          </div>
        </>}
        <p className="small muted">Changes affect the next search when you select Show maps.</p>
      </div>}
    </Card>
  );
}
