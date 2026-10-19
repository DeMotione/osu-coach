import { useState } from "react";

import { NAV } from "../../app/nav";
import { IconArrowLeft, IconArrowRight } from "../icons";
import { Step } from "./parts";

/** Step 4: a quick tour of the app's sections (the sidebar's groups, one at a time), or skip it. */
export function GuideStep({ onBack, onNext }: { onBack: () => void; onNext: () => void }) {
  const [slide, setSlide] = useState<number | null>(null);
  const back = (to: () => void) => (
    <button type="button" className="btn btn--ghost" onClick={to}>
      <IconArrowLeft /> Back
    </button>
  );

  if (slide === null)
    return (
      <Step
        title="Want a quick tour?"
        sub="A minute on what each part of osu! coach is for, so you know where to look. Or skip it and find your own way."
        foot={
          <>
            {back(onBack)}
            <span className="grow" />
            <button type="button" className="btn" onClick={onNext}>
              Skip
            </button>
            <button type="button" className="btn btn--primary" onClick={() => setSlide(0)}>
              Show me around <IconArrowRight />
            </button>
          </>
        }
      >
        <ol className="tour-groups">
          {NAV.map((g, i) => (
            <li key={g.group}>
              <button type="button" className="tour-group" onClick={() => setSlide(i)}>
                <span className="tour-group__icons" aria-hidden="true">
                  {g.items.map(({ path, icon: Icon }) => (
                    <Icon key={path} />
                  ))}
                </span>
                <span className="tour-group__name">{g.group}</span>
                <span className="tour-group__about">{g.about}</span>
              </button>
            </li>
          ))}
        </ol>
      </Step>
    );

  const group = NAV[slide];
  const last = slide === NAV.length - 1;
  return (
    <Step
      key={slide}
      title={group.group}
      sub={group.about}
      foot={
        <>
          {back(() => setSlide(slide === 0 ? null : slide - 1))}
          <span className="tour-dots" role="img" aria-label={`Part ${slide + 1} of ${NAV.length}`}>
            {NAV.map((g, i) => (
              <span key={g.group} className={i === slide ? "on" : undefined} />
            ))}
          </span>
          <span className="grow" />
          {!last && (
            <button type="button" className="btn btn--ghost" onClick={onNext}>
              Skip the rest
            </button>
          )}
          <button type="button" className="btn btn--primary" onClick={() => (last ? onNext() : setSlide(slide + 1))}>
            {last ? "Finish the tour" : "Next"} <IconArrowRight />
          </button>
        </>
      }
    >
      <ul className="tour">
        {group.items.map(({ path, label, about, icon: Icon }) => (
          <li key={path} className="tour__item">
            <span className="tour__icon" aria-hidden="true">
              <Icon />
            </span>
            <span className="tour__name">{label}</span>
            <span className="tour__about">{about}</span>
          </li>
        ))}
      </ul>
      <p className="small muted">
        {slide === 0
          ? "All of these are in the sidebar on the left (behind the menu button on a small screen)."
          : "The pages of this group stay greyed out in the sidebar until replays are analysed."}
      </p>
    </Step>
  );
}
