import type { ReactNode } from "react";

import { IconBolt, IconKeypad, IconKeys, IconMouse, IconPen } from "../icons";
import { SetupDetails, type Setup, type SetupPatch } from "../SetupForm";
import { Section } from "../ui";
import { ChoiceCards, Step } from "./parts";

/** Step 2: aim device and keys, then their settings — the same form as on Tips & Setup, where they show afterwards. */
export function PlaystyleStep({ setup, onChange, foot }: { setup: Setup; onChange: (patch: SetupPatch) => void; foot: ReactNode }) {
  return (
    <Step
      title="How do you play?"
      sub="Your aim device and keys make the tips concrete: a tablet area or sensitivity to try, key settings to change. Fill in what you know and leave the rest empty — you can change all of it later on Tips & Setup."
      foot={foot}
    >
      <Section title="Aim with">
        <ChoiceCards
          label="Aim with"
          value={setup.device}
          onChange={(device) => onChange({ device })}
          options={[
            { value: "mouse", title: "Mouse", text: "DPI and the osu! sensitivity decide how far the cursor moves.", icon: <IconMouse /> },
            { value: "tablet", title: "Tablet", text: "A pen on a drawing tablet; the area you map decides how far the cursor moves.", icon: <IconPen /> },
          ]}
        />
      </Section>
      <Section title="Tap with">
        <ChoiceCards
          label="Tap with"
          value={setup.keyboard}
          onChange={(keyboard) => onChange({ keyboard })}
          options={[
            { value: "standard", title: "Keyboard", text: "Ordinary keys that click at a fixed point.", icon: <IconKeys /> },
            { value: "rapid_trigger", title: "Rapid trigger keyboard", text: "Magnetic (Hall effect) keys with an adjustable actuation point.", icon: <IconBolt /> },
            { value: "sayo", title: "SayoDevice", text: "An osu! keypad, set up in the SayoDevice web configurator.", icon: <IconKeypad /> },
          ]}
        />
      </Section>
      <Section title="Your settings">
        <SetupDetails value={setup} onChange={onChange} client={false} />
      </Section>
    </Step>
  );
}
