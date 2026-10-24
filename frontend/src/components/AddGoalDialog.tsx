import { useEffect, useRef, useState } from "react";

import type { Schemas } from "../api/client";
import { useAddGoal } from "../api/queries";
import { isoDay } from "../lib/format";
import { blockedSkills } from "../lib/goals";
import { IconPlus, IconX } from "./icons";
import { Alert, Field } from "./ui";

type Goals = Schemas["GoalsOut"];

const WEEKS = [2, 4, 8] as const;

/** "Add goal" and its dialog: the goals you have, a button per skill, then the target and by when. */
export function AddGoal({ goals }: { goals: Goals }) {
  const [open, setOpen] = useState(false);
  const usable = goals.has_profile && goals.skills.length > 0;
  return (
    <>
      <button
        type="button"
        className="btn btn--primary"
        disabled={!usable}
        title={usable ? undefined : "Analyse your replays first: goals follow your skill scores."}
        onClick={() => setOpen(true)}
      >
        <IconPlus /> Add goal
      </button>
      {open && <AddGoalDialog goals={goals} onClose={() => setOpen(false)} />}
    </>
  );
}

function AddGoalDialog({ goals, onClose }: { goals: Goals; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const add = useAddGoal();
  const blocked = blockedSkills(goals);
  const active = goals.open.filter((g) => g.state !== "paused");
  const [skill, setSkill] = useState<string | null>(null);
  const [target, setTarget] = useState("");
  const [deadline, setDeadline] = useState(isoDay(28));
  const chosen = goals.skills.find((s) => s.key === skill);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (typeof d.showModal === "function") d.showModal();
    else d.setAttribute("open", "");
    return () => d.close?.();
  }, []);

  const pick = (key: string, score: number) => {
    setSkill(key);
    setTarget(String(Math.min(100, Math.round(score) + 10)));
    add.reset();
  };

  return (
    <dialog ref={ref} className="goal-dialog" aria-labelledby="goal-dialog-title" onClose={onClose}>
      <div className="goal-dialog__head">
        <h2 id="goal-dialog-title" className="card__title">Add a goal</h2>
        <button type="button" className="btn btn--ghost btn--sm" aria-label="Close" onClick={onClose}>
          <IconX />
        </button>
      </div>
      <div className="goal-dialog__body">
        <section>
          <h3 className="section__title">Your goals</h3>
          {active.length ? (
            <div className="goal-dialog__chips">
              {active.map((g) => (
                <span key={g.id} className="chip">
                  {g.label} → {g.target.toFixed(0)} by {g.deadline}
                </span>
              ))}
            </div>
          ) : (
            <p className="small muted">None yet.</p>
          )}
        </section>
        <section>
          <h3 className="section__title">Skill</h3>
          <div className="skill-picks" role="group" aria-label="Skill">
            {goals.skills.map((s) => {
              const why = blocked.get(s.key);
              return (
                <button
                  key={s.key}
                  type="button"
                  className="skill-pick"
                  aria-pressed={skill === s.key}
                  disabled={why !== undefined}
                  onClick={() => pick(s.key, s.score)}
                >
                  <span>{s.label}</span>
                  <small>{why ?? `now ${s.score.toFixed(0)}`}</small>
                </button>
              );
            })}
          </div>
        </section>
        {chosen && (
          <section className="goal-dialog__when">
            <Field label={`Target (now ${chosen.score.toFixed(0)})`}>
              <input className="input" type="number" min={Math.ceil(chosen.score + 0.01)} max={100} value={target}
                onChange={(e) => setTarget(e.target.value)} />
            </Field>
            {/* buttons, so not inside a <label> like the other fields */}
            <div className="field" role="group" aria-labelledby="goal-dialog-by">
              <span id="goal-dialog-by" className="field__label">By</span>
              <div className="goal-dialog__dates">
                {WEEKS.map((w) => (
                  <button key={w} type="button" className="btn btn--sm" aria-pressed={deadline === isoDay(w * 7)}
                    onClick={() => setDeadline(isoDay(w * 7))}>
                    {w} weeks
                  </button>
                ))}
                <input className="input" type="date" min={isoDay()} value={deadline} aria-label="Deadline"
                  onChange={(e) => setDeadline(e.target.value)} />
              </div>
            </div>
          </section>
        )}
        {add.isError && <Alert tone="bad">{add.error.message}</Alert>}
      </div>
      <div className="goal-dialog__foot">
        <button type="button" className="btn btn--ghost" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={!chosen || !target || !deadline || add.isPending}
          onClick={() => chosen && add.mutate({ skill: chosen.key, target: Number(target), deadline }, { onSuccess: onClose })}
        >
          <IconPlus /> Add goal
        </button>
      </div>
    </dialog>
  );
}
