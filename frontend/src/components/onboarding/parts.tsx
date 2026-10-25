/** Building blocks of the setup guide's steps. */
import { useEffect, useId, useRef, type ReactNode } from "react";

import { IconCheck } from "../icons";

/**
 * One step: its title (focused when the step opens, for screen readers), what it asks, and its buttons at the bottom.
 * ``lead``: something above the title (the finish mark).
 */
export function Step({ title, sub, lead, foot, children }: { title: string; sub?: ReactNode; lead?: ReactNode; foot: ReactNode; children?: ReactNode }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus({ preventScroll: true }), []);
  return (
    <section className="onboarding__step">
      <div className="onboarding__content">
        <header className={lead ? "onboarding__intro onboarding__intro--lead" : "onboarding__intro"}>
          {lead}
          <h2 ref={heading} tabIndex={-1} className="onboarding__title">
            {title}
          </h2>
          {sub && <p className="onboarding__sub">{sub}</p>}
        </header>
        {children}
      </div>
      <footer className="onboarding__foot">{foot}</footer>
    </section>
  );
}

interface Choice<T> {
  value: T;
  title: string;
  text: ReactNode;
  icon: ReactNode;
}

/** A choice between a few things, as big cards with an icon and a line on each. */
export function ChoiceCards<T extends string>({ label, value, onChange, options }: { label: string; value: T; onChange: (v: T) => void; options: Choice<T>[] }) {
  const name = useId();
  return (
    <div className={`choices choices--${options.length}`} role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <label key={o.value} className={`choice${o.value === value ? " checked" : ""}`}>
          {/* named by the title, described by the line under it */}
          <input
            type="radio"
            className="visually-hidden"
            name={name}
            checked={o.value === value}
            onChange={() => onChange(o.value)}
            aria-labelledby={`${name}-${o.value}`}
            aria-describedby={`${name}-${o.value}-text`}
          />
          <span className="choice__icon" aria-hidden="true">
            {o.icon}
          </span>
          <span className="choice__title" id={`${name}-${o.value}`}>
            {o.title}
          </span>
          <span className="choice__text" id={`${name}-${o.value}-text`}>
            {o.text}
          </span>
          <IconCheck className="choice__check" />
        </label>
      ))}
    </div>
  );
}

/**
 * The loading animation: three numbered hit circles, each hit (300!) as its approach circle closes in, with the cursor
 * jumping from one to the next.
 */
export function HitCircles() {
  return (
    <div className="hitcircles" aria-hidden="true">
      {[1, 2, 3].map((n) => (
        <span key={n} className={`hitcircle hitcircle--${n}`}>
          <span className="hitcircle__ring" />
          <span className="hitcircle__body">{n}</span>
          <span className="hitcircle__judge">300</span>
        </span>
      ))}
      <span className="hitcircles__cursor" />
    </div>
  );
}
