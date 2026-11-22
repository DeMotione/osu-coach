import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { SetupDetails, type Setup } from "./SetupForm";

const sayo = {
  device: "tablet", handedness: "right", client: "stable", keyboard: "sayo", screen_w_px: 1920, screen_h_px: 1080,
  sayo_rt: null, sayo_full_stroke: null, sayo_rt_trigger_mm: 0.2, sayo_rt_upper_mm: 0.5,
} as unknown as Setup;
const field = (name: RegExp) => screen.queryByRole("spinbutton", { name });

it("hides the rapid-trigger values while RT Mode is off, and the bounds while Full Stroke is on", () => {
  const { rerender } = render(<SetupDetails value={sayo} onChange={vi.fn()} />);
  // rapid trigger counts as on until it is switched off
  for (const name of [/^RT Trigger/, /^RT Release/, /^RT Upper Bound/, /^RT Lower Bound/]) expect(field(name)).not.toBeNull();

  rerender(<SetupDetails value={{ ...sayo, sayo_full_stroke: true }} onChange={vi.fn()} />);
  expect(field(/^RT Upper Bound/)).toBeNull();
  expect(field(/^RT Lower Bound/)).toBeNull();
  expect(field(/^RT Trigger/)).not.toBeNull();

  rerender(<SetupDetails value={{ ...sayo, sayo_rt: false }} onChange={vi.fn()} />);
  for (const name of [/^RT Trigger/, /^RT Release/, /^RT Upper Bound/, /^RT Lower Bound/]) expect(field(name)).toBeNull();
  expect(screen.queryByRole("checkbox", { name: /^Full Stroke/ })).toBeNull();
  expect(screen.getByRole("checkbox", { name: /^RT Mode/ })).not.toBeChecked();
  for (const name of [/^Stroke/, /^Trigger/, /^Release/]) expect(field(name)).not.toBeNull();
});
