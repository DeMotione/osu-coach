import { useAnalysisStatus } from "../../api/queries";
import { int } from "../../lib/format";
import { IconArrowLeft, IconArrowRight, IconCheck, IconCompass } from "../icons";
import type { Setup } from "../SetupForm";
import type { ReplayRunState } from "./ReplaysStep";
import { Step } from "./parts";

const KEYS: Record<Setup["keyboard"], string> = { standard: "Keyboard", rapid_trigger: "Rapid trigger keyboard", sayo: "SayoDevice" };

function aim(s: Setup): string {
  const parts =
    s.device === "tablet"
      ? [s.area_w_mm && s.area_h_mm ? `area ${+s.area_w_mm.toFixed(1)} × ${+s.area_h_mm.toFixed(1)} mm` : null]
      : [s.mouse_dpi ? `${int(s.mouse_dpi)} DPI` : null, s.ingame_sens ? `sensitivity ${s.ingame_sens}` : null];
  const known = parts.filter(Boolean);
  return `${s.device === "tablet" ? "Tablet" : "Mouse"}${known.length ? ` · ${known.join(", ")}` : ""}`;
}

/** Step 5: the setup is finished — what was set up, and where to go first. */
export function DoneStep({ setup, r, onBack, onFinish }: { setup: Setup; r: ReplayRunState; onBack: () => void; onFinish: (to: string) => void }) {
  const status = useAnalysisStatus();
  const st = status.data;
  const running = r.phase === "scanning" || r.phase === "analysing";
  const analysed = !running && !!st && st.profile_replays !== null;
  return (
    <Step
      lead={
        <span className="done-mark done-mark--big" aria-hidden="true">
          <IconCheck />
        </span>
      }
      title="You're all set!"
      sub="The first setup is finished — osu! coach is ready to use."
      foot={
        <>
          <button type="button" className="btn btn--ghost" onClick={onBack}>
            <IconArrowLeft /> Back
          </button>
          <span className="grow" />
          <button type="button" className="btn btn--primary" onClick={() => onFinish(analysed ? "/overview" : "/replays")}>
            Start using osu! coach <IconArrowRight />
          </button>
        </>
      }
    >
      <dl className="kv onboarding__summary">
        <dt>osu!</dt>
        <dd>osu!{setup.client}</dd>
        <dt>Aim</dt>
        <dd>{aim(setup)}</dd>
        <dt>Keys</dt>
        <dd>{KEYS[setup.keyboard]}</dd>
        <dt>Replays</dt>
        <dd>
          {running
            ? "Still being analysed — the status bar at the bottom shows how far it is."
            : analysed
              ? `${int(st.analysed)} analysed${st.player_label ? ` (${st.player_label})` : ""}`
              : "None analysed yet — the Replays page is where to add them."}
        </dd>
      </dl>
      <p>
        {analysed
          ? "Start with the Overview: your level, your skills and what to work on first."
          : running
            ? "The analysis pages fill in as soon as it is done; until then you land on the Replays page."
            : "Once your replays are analysed, every page fills in with your numbers."}
      </p>
      <p className="small muted">
        Your setup is on Setup Tips, where you can change it any time. This guide opens again from the{" "}
        <IconCompass className="inline-icon" /> Setup guide button at the top.
      </p>
    </Step>
  );
}
