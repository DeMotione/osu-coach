/**
 * The setup guide: shown over the app on the first start (until it is finished or skipped), and again from the
 * toolbar. Five steps: osu! version (and where it is), playstyle and setup, replays (scanned and analysed right
 * away), a quick tour of the app, done.
 */
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router";

import { usePatchSettings, useSaveSetup, useSetup } from "../../api/queries";
import { IconArrowLeft, IconArrowRight, IconCheck } from "../icons";
import { setupToSave, type Setup, type SetupPatch } from "../SetupForm";
import { ClientStep } from "./ClientStep";
import { DoneStep } from "./DoneStep";
import { GuideStep } from "./GuideStep";
import { PlaystyleStep } from "./PlaystyleStep";
import { ReplaysStep, useReplayRun, type ReplayRun } from "./ReplaysStep";

const STEPS = [
  { key: "client", label: "osu! version" },
  { key: "playstyle", label: "Playstyle" },
  { key: "replays", label: "Replays" },
  { key: "guide", label: "Quick guide" },
  { key: "done", label: "Done" },
] as const;

type StepKey = (typeof STEPS)[number]["key"];

/** Where the guide is, kept for the browser tab: a reload (or the app restarting) goes on where it was. */
interface Saved {
  step: StepKey;
  run: ReplayRun | null;
}

const STORE = "osu-coach:setup-guide";

function load(): Saved {
  try {
    const v = JSON.parse(sessionStorage.getItem(STORE) ?? "null") as Partial<Saved> | null;
    if (v && STEPS.some((s) => s.key === v.step))
      return { step: v.step as StepKey, run: v.run && typeof v.run.scan === "string" ? v.run : null };
  } catch {
    /* storage blocked or garbled: start at the beginning */
  }
  return { step: "client", run: null };
}

function store(saved: Saved | null) {
  try {
    if (saved) sessionStorage.setItem(STORE, JSON.stringify(saved));
    else sessionStorage.removeItem(STORE);
  } catch {
    /* a convenience only */
  }
}

export function Onboarding({ first, onClose }: { first: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const patchSettings = usePatchSettings();
  const saved = useSetup();
  const save = useSaveSetup();
  const [state, setState] = useState<Saved>(load);
  const [draft, setDraft] = useState<Setup | null>(null);
  const setup = draft ?? saved.data ?? null;
  const index = STEPS.findIndex((s) => s.key === state.step);

  useEffect(() => store(state), [state]);

  const go = (step: StepKey) => {
    save.reset();
    setState((s) => ({ ...s, step }));
  };
  const setRun = useCallback((run: ReplayRun | null) => setState((s) => ({ ...s, run })), []);
  const r = useReplayRun(state.run, setRun);
  const change = (patch: SetupPatch) => setup && setDraft({ ...setup, ...patch });

  /** Finished or skipped: not shown again on the next start. */
  const finish = (to?: string) => {
    patchSettings.mutate({ onboarded: true });
    store(null);
    onClose();
    if (to) void navigate(to);
  };

  /** Steps 1 and 2 save the setup on the way out, so it is on Tips & Setup right away. */
  const saveFoot = (back: StepKey | null, next: StepKey) => (
    <>
      {back && (
        <button type="button" className="btn btn--ghost" onClick={() => go(back)}>
          <IconArrowLeft /> Back
        </button>
      )}
      {save.isError && (
        <span className="onboarding__error" role="alert">
          {save.error.message}
        </span>
      )}
      <span className="grow" />
      <button
        type="button"
        className="btn btn--primary"
        disabled={!setup || save.isPending}
        onClick={() => setup && save.mutate(setupToSave(setup), { onSuccess: () => go(next) })}
      >
        {save.isPending ? "Saving…" : "Continue"} <IconArrowRight />
      </button>
    </>
  );

  let content;
  if (!setup) content = <div className="onboarding__step onboarding__content"><div className="skeleton" style={{ height: 260 }} /></div>;
  else if (state.step === "client") content = <ClientStep setup={setup} onChange={change} foot={saveFoot(null, "playstyle")} />;
  else if (state.step === "playstyle") content = <PlaystyleStep setup={setup} onChange={change} foot={saveFoot("client", "replays")} />;
  else if (state.step === "replays")
    content = <ReplaysStep client={setup.client} r={r} onBack={() => go("playstyle")} onNext={() => go("guide")} />;
  else if (state.step === "guide") content = <GuideStep onBack={() => go("replays")} onNext={() => go("done")} />;
  else content = <DoneStep setup={setup} r={r} onBack={() => go("guide")} onFinish={finish} />;

  return (
    <div className="onboarding">
      <div
        className="onboarding__dialog"
        role="dialog"
        aria-modal="true"
        aria-label={first ? "Set up osu! coach" : "Setup guide"}
        onKeyDown={(e) => {
          if (e.key === "Escape" && !first) onClose();
        }}
      >
        <header className="onboarding__head">
          <svg className="brand__mark" viewBox="0 0 256 256" aria-hidden="true">
            <circle cx="128" cy="128" r="120" className="brand__disc" />
            <circle cx="128" cy="128" r="85" className="brand__ring" />
            <circle cx="128" cy="128" r="36" className="brand__dot" />
          </svg>
          <div className="onboarding__heading">
            <strong>{first ? "Welcome to osu! coach" : "Setup guide"}</strong>
            <span>
              {first ? "First-time setup" : "Go through the setup again"} · step {index + 1} of {STEPS.length}
            </span>
          </div>
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => (first ? finish() : onClose())}>
            {first ? "Skip setup" : "Close"}
          </button>
        </header>
        <ol className="stepper">
          {STEPS.map((s, i) => {
            const cls = `stepper__item${i < index ? " done" : i === index ? " current" : ""}`;
            const inner = (
              <>
                <span className="stepper__bar" />
                <span className="stepper__label">
                  {i < index && <IconCheck />}
                  {s.label}
                </span>
              </>
            );
            return (
              <li key={s.key} className={cls} aria-current={i === index ? "step" : undefined}>
                {i < index ? (
                  <button type="button" className="stepper__btn" onClick={() => go(s.key)} title={`Back to: ${s.label}`}>
                    {inner}
                  </button>
                ) : (
                  <span className="stepper__btn">{inner}</span>
                )}
              </li>
            );
          })}
        </ol>
        <div className="onboarding__body" key={state.step}>
          {content}
        </div>
      </div>
    </div>
  );
}
