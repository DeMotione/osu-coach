import type { ReactNode } from "react";
import { Link } from "react-router";

import { IconArrowRight } from "./icons";

export type VerdictTone = "bad" | "good" | "info" | "muted";

/** The skills a playlist can be made for (Goals & Training → Playlist for a skill). */
export type PractiseSkill =
  | "aim"
  | "flow_aim"
  | "speed"
  | "stamina"
  | "accuracy"
  | "sliders"
  | "reading"
  | "consistency"
  | "quadrant";

/** A playlist of maps for ``skill``, opened on Goals & Training. */
export function PractiseLink({ skill, children = "Practise this" }: { skill: PractiseSkill; children?: ReactNode }) {
  return (
    <Link className="btn btn--sm verdict__practise" to={`/skills?tab=playlist&skill=${skill}`}>
      {children} <IconArrowRight width={14} height={14} />
    </Link>
  );
}

/**
 * What a card's chart says, first: one sentence and its key number, coloured by what it means (bad = something to
 * work on, good = nothing to worry about, muted = too little to tell), and a way to practise it. The chart under it
 * is the evidence.
 */
export function Verdict({ tone, value, children, practise }: {
  tone: VerdictTone;
  /** the number the sentence is about, shown big */
  value?: ReactNode;
  children: ReactNode;
  practise?: PractiseSkill | null;
}) {
  return (
    <div className={`verdict verdict--${tone}`} role="status">
      {value !== undefined && value !== null && <div className="verdict__value">{value}</div>}
      <div className="verdict__body">
        <p className="verdict__text">{children}</p>
        {practise && <PractiseLink skill={practise} />}
      </div>
    </div>
  );
}
