import type { ReactNode } from "react";
import { Link } from "react-router";

import { type Practise, practiseUrl } from "../lib/practise";
import { IconArrowRight } from "./icons";

export type VerdictTone = "bad" | "good" | "info" | "muted";

/** A playlist of maps for the weak spot, made at once on Goals & Training. */
export function PractiseLink({ practise, children = "Practise this" }: { practise: Practise; children?: ReactNode }) {
  return (
    <Link className="btn btn--sm verdict__practise" to={practiseUrl(practise)}>
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
  /** the playlist that practises what it says (#144) */
  practise?: Practise | null;
}) {
  return (
    <div className={`verdict verdict--${tone}`} role="status">
      {value !== undefined && value !== null && <div className="verdict__value">{value}</div>}
      <div className="verdict__body">
        <p className="verdict__text">{children}</p>
        {practise && <PractiseLink practise={practise} />}
      </div>
    </div>
  );
}
