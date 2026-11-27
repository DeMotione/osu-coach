import { useId, useState } from "react";

import { RangeSlider } from "./RangeSlider";
import { Card, Field, Segmented } from "./ui";

export interface RecommendationOptions {
  skill?: string;
  assessed?: string;
  ratings?: string;
  comfort?: number;
  kappa?: number;
  min_relevance?: number;
  exclude_played?: boolean;
  allow_hr?: boolean;
  allow_hd?: boolean;
  adjustable_dt?: boolean;
  min_rate?: number;
  max_rate?: number;
  /** the weak spot the playlist keeps to ("Practise this" on an analysis page, #144); maps without mods only */
  focus?: string;
  /** approach rates to keep to (with mods): none = around your level (without mods; with mods any), "any", "9.2-9.8" */
  ar?: string;
}

/** Skills no map is checked on (unless it is the target): accuracy can't be practised apart from the rest, the
 * approach rate range takes reading's place, and consistency isn't rated against what maps ask (#149). */
const NOT_ASSESSED = new Set(["accuracy", "reading", "consistency"]);

type ArMode = "level" | "any" | "choose";
const AR_DEFAULT: [number, number] = [9.2, 9.8];

/** The AR choice as applied back into the control: its mode and its range ("9.2-9.8"). */
function arChoice(applied: string | undefined, level: [number, number] | null): { mode: ArMode; range: [number, number] } {
  const m = /^(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)$/.exec(applied ?? "");
  if (m) return { mode: "choose", range: [Number(m[1]), Number(m[2])] };
  return { mode: applied === "any" ? "any" : "level", range: level ?? AR_DEFAULT };
}

const SKILLS = [
  ["aim", "Jumps"], ["flow_aim", "Spaced streams"], ["speed", "Tapping speed"],
  ["stamina", "Stamina"], ["accuracy", "Accuracy"], ["sliders", "Sliders"],
  ["reading", "Reading"], ["consistency", "Consistency"],
] as const;

const skillName = (id: string) => SKILLS.find(([key]) => key === id)?.[1] ?? id;

/** Manual ratings as applied (a JSON object of numbers) back into the fields' texts. */
function ratingTexts(applied: string | undefined): Record<string, string> {
  try {
    const v: unknown = applied ? JSON.parse(applied) : null;
    if (typeof v !== "object" || v === null) return {};
    return Object.fromEntries(Object.entries(v).filter(([, n]) => typeof n === "number").map(([k, n]) => [k, String(n)]));
  } catch {
    return {};
  }
}

/** Draft every control locally; the one Show maps action applies the complete selection. The draft starts from
 * ``initial``, the selection applied last (a playlist come back to, #107); unless skills to assess were chosen there,
 * every skill with a rating (``measured``) is assessed, so no map asks one for much more than the player has. With
 * ``levels`` (Star Levels: the star rating each skill's playlist is made around, the comfort level moved toward the
 * skill's own level) there is no comfort difficulty, κₛ or relevance to set, and no other skill ratings to try: a skill
 * is a star level, not a 0–100 score (#126). */
export function RecommendationControls({ current, measured, comfort, levels, levelAr = null, initial = {}, onApply }: {
  current: string;
  measured: Record<string, number>;
  comfort: number;
  levels?: Record<string, number>;
  /** the AR range around the level (maps without mods): what "Around your level" keeps to */
  levelAr?: [number, number] | null;
  initial?: RecommendationOptions;
  onApply: (options: RecommendationOptions) => void;
}) {
  const [skill, setSkill] = useState(initial.skill ?? current);
  const [panel, setPanel] = useState<"fine" | "ratings" | null>(null);
  const panelId = useId();
  const [assessed, setAssessed] = useState<string[] | null>(initial.assessed ? initial.assessed.split(",") : null);
  const [ratings, setRatings] = useState<Record<string, string>>(() => ratingTexts(initial.ratings));
  const [starsOverride, setStarsOverride] = useState<string | null>(initial.comfort !== undefined ? String(initial.comfort) : null);
  const stars = starsOverride ?? comfort.toFixed(2);
  const [kappa, setKappa] = useState(String(initial.kappa ?? 0.5));
  const [relevance, setRelevance] = useState(String(initial.min_relevance ?? 0.3));
  const [excludePlayed, setExcludePlayed] = useState(initial.exclude_played ?? true);
  const [allowHr, setAllowHr] = useState(!!initial.allow_hr);
  const [allowHd, setAllowHd] = useState(!!initial.allow_hd);
  const [adjustableDt, setAdjustableDt] = useState(!!initial.adjustable_dt);
  const [minRate, setMinRate] = useState((initial.min_rate ?? 1.1).toFixed(2));
  const [maxRate, setMaxRate] = useState((initial.max_rate ?? 2).toFixed(2));
  const [ar, setAr] = useState(() => arChoice(initial.ar, levelAr));
  const rated = SKILLS.map(([id]) => id).filter((id) => measured[id] !== undefined);
  const selected = [skill, ...(assessed ?? rated).filter((id) => id !== skill && !NOT_ASSESSED.has(id))];
  const modded = allowHr || allowHd || adjustableDt;
  const tenth = (v: number) => v.toFixed(1);
  const byLevel = levels !== undefined;
  const valid = (byLevel || (Number(stars) > 0 && Number(kappa) >= 0 && Number(relevance) >= 0 && Number(relevance) <= 1 &&
    [stars, kappa, relevance].every((n) => n.trim() !== "" && Number.isFinite(Number(n))))) &&
    (byLevel || Object.values(ratings).every((n) => n.trim() === "" || (Number.isFinite(Number(n)) && Number(n) >= 0 && Number(n) <= 100))) &&
    (!adjustableDt || (Number(minRate) >= 1.10 && Number(maxRate) <= 2.00 && Number(minRate) <= Number(maxRate) &&
      [minRate, maxRate].every((n) => n.trim() !== "" &&
        Math.abs(Number(n) * 100 - Math.round(Number(n) * 100)) < 1e-8)));

  const showMaps = () => {
    const manual = Object.fromEntries(Object.entries(ratings).filter(([, value]) => value.trim() !== "")
      .map(([key, value]) => [key, Number(value)]));
    onApply({
      skill,
      assessed: selected.join(","),
      // Star Levels: no ratings to try or comfort; κₛ is unused (the skill's level moves the playlist), and relevance keeps
      // its default
      ratings: !byLevel && Object.keys(manual).length ? JSON.stringify(manual) : undefined,
      comfort: !byLevel && starsOverride !== null ? Number(stars) : undefined,
      kappa: byLevel ? 0.5 : Number(kappa),
      min_relevance: byLevel ? 0.3 : Number(relevance),
      exclude_played: excludePlayed,
      allow_hr: allowHr,
      allow_hd: allowHd,
      adjustable_dt: adjustableDt,
      min_rate: Number(minRate),
      max_rate: Number(maxRate),
      ar: ar.mode === "level" ? undefined : ar.mode === "any" ? "any" : `${tenth(ar.range[0])}-${tenth(ar.range[1])}`,
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
        {!byLevel && <button type="button" className={panel === "ratings" ? "recommendation-mode active" : "recommendation-mode"}
          aria-expanded={panel === "ratings"} aria-controls={panelId} onClick={() => setPanel(panel === "ratings" ? null : "ratings")}>Try other skill ratings</button>}
      </div>

      {panel && !(byLevel && panel === "ratings") && <div className="recommendation-panel" id={panelId} role="region" aria-label={panel === "fine" ? "Fine-tune" : "Skill ratings"}>
        <div className="recommendation-panel__head">
          <h3>{panel === "fine" ? "Fine-tune" : "Try other skill ratings"}</h3>
          <button type="button" className="recommendation-close" aria-label="Close settings" onClick={() => setPanel(null)}>×</button>
        </div>
        {panel === "fine" ? <>
          {byLevel ? (
            <p className="small muted">
              Difficulty:{" "}
              {levels[skill] !== undefined
                ? `${levels[skill].toFixed(2)}★: your comfort level moved toward your ${skillName(skill)} level, as far as it is likely at least and half a star at most.`
                : `your comfort level (${skillName(skill)} has no measured star level).`}
            </p>
          ) : (
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
          )}
          <label className="recommendation-check">
            <input type="checkbox" checked={excludePlayed} onChange={(event) => setExcludePlayed(event.target.checked)} />
            Hide maps I have already completed
          </label>
          <div className="recommendation-grid">
            <label className="recommendation-check"><input type="checkbox" checked={allowHr} onChange={(event) => setAllowHr(event.target.checked)} />Allow Hard Rock</label>
            <label className="recommendation-check"><input type="checkbox" checked={allowHd} onChange={(event) => setAllowHd(event.target.checked)} />Allow Hidden</label>
            <label className="recommendation-check"><input type="checkbox" checked={adjustableDt} onChange={(event) => setAdjustableDt(event.target.checked)} />Search adjustable DT</label>
          </div>
          {adjustableDt && <div className="recommendation-grid">
            <Field label="Minimum DT rate"><input className="input" type="number" min="1.10" max="2.00" step="0.01" value={minRate} onChange={(event) => setMinRate(event.target.value)} /></Field>
            <Field label="Maximum DT rate"><input className="input" type="number" min="1.10" max="2.00" step="0.01" value={maxRate} onChange={(event) => setMaxRate(event.target.value)} /></Field>
          </div>}
          <div className="recommendation-assessed">
            <h4>Approach rate</h4>
            <Segmented
              label="Approach rate"
              value={ar.mode}
              onChange={(mode) => setAr({ mode, range: mode === "choose" && ar.mode !== "choose" ? (levelAr ?? AR_DEFAULT) : ar.range })}
              options={[
                { value: "level", label: levelAr && !modded ? `Around your level (${tenth(levelAr[0])}–${tenth(levelAr[1])})` : "Around your level" },
                { value: "any", label: "Any AR" },
                { value: "choose", label: "Choose" },
              ]}
            />
            {ar.mode === "choose" && (
              <RangeSlider label="AR (with mods)" min={5} max={11} step={0.1} value={ar.range} format={tenth}
                onChange={(range) => setAr({ mode: "choose", range })} />
            )}
            <p className="small muted">
              {ar.mode === "level"
                ? modded
                  ? "With mods, a map's AR changes with each mod and speed, so any AR is kept: choose a range to limit it."
                  : "Maps at the approach rate typical of your level, 0.3 either way."
                : ar.mode === "any"
                  ? "Maps at any approach rate."
                  : "Only maps whose approach rate (with the mods: HR and DT raise it) is in this range."}
            </p>
          </div>
          <div className="recommendation-assessed">
            <h4>Skills to assess</h4>
            <p className="small muted">Every skill with a rating is checked: a map that asks one for more than half a star beyond your rating (a warm-up: beyond your rating) is left out, and one that asks it for more than your rating ranks lower. The target skill is always included; unchecked demands are unassessed; a checked skill with unknown player ability excludes the map. Accuracy, reading and consistency aren't checked: accuracy can't be trained apart from the rest, the approach rate above takes reading's place, and consistency is rated by how steadily you hold combo and accuracy, not against what a map asks.</p>
            <div className="recommendation-skills">
              {SKILLS.filter(([id]) => id === skill || !NOT_ASSESSED.has(id)).map(([id, label]) => (
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
