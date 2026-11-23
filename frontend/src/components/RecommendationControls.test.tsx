import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { RecommendationControls } from "./RecommendationControls";

it("applies exact mod search settings while keeping the selected skill controls", () => {
  const onApply = vi.fn();
  render(<RecommendationControls current="aim" measured={{ aim: 50 }} comfort={4} onApply={onApply} />);
  fireEvent.click(screen.getByRole("button", { name: /Fine-tune/ }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Allow Hard Rock" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Allow Hidden" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Search adjustable DT" }));
  fireEvent.change(screen.getByRole("spinbutton", { name: "Minimum DT rate" }), { target: { value: "1.20" } });
  fireEvent.change(screen.getByRole("spinbutton", { name: "Maximum DT rate" }), { target: { value: "1.50" } });
  fireEvent.click(screen.getByRole("button", { name: "Show maps" }));
  expect(onApply).toHaveBeenCalledWith(expect.objectContaining({
    skill: "aim", assessed: "aim", allow_hr: true, allow_hd: true,
    adjustable_dt: true, min_rate: 1.20, max_rate: 1.50,
  }));
});

it("assesses every skill with a rating unless others are chosen", () => {
  const onApply = vi.fn();
  render(<RecommendationControls current="aim" measured={{ aim: 50, speed: 60, reading: 40 }} comfort={4} onApply={onApply} />);
  fireEvent.click(screen.getByRole("button", { name: "Show maps" }));
  expect(onApply).toHaveBeenLastCalledWith(expect.objectContaining({ skill: "aim", assessed: "aim,speed,reading" }));
  fireEvent.change(screen.getByRole("combobox", { name: "Target skill" }), { target: { value: "speed" } });
  fireEvent.click(screen.getByRole("button", { name: /Fine-tune/ }));
  expect(screen.getByRole("checkbox", { name: "Reading" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "Stamina" })).not.toBeChecked(); // no rating
  fireEvent.click(screen.getByRole("checkbox", { name: "Reading" }));
  fireEvent.click(screen.getByRole("button", { name: "Show maps" }));
  expect(onApply).toHaveBeenLastCalledWith(expect.objectContaining({ skill: "speed", assessed: "speed,aim" }));
});

it("rejects a reversed DT range before applying", () => {
  render(<RecommendationControls current="aim" measured={{ aim: 50 }} comfort={4} onApply={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: /Fine-tune/ }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Search adjustable DT" }));
  fireEvent.change(screen.getByRole("spinbutton", { name: "Minimum DT rate" }), { target: { value: "1.80" } });
  fireEvent.change(screen.getByRole("spinbutton", { name: "Maximum DT rate" }), { target: { value: "1.50" } });
  expect(screen.getByRole("button", { name: "Show maps" })).toBeDisabled();
});

it("accepts both default DT endpoints and rejects finer than hundredth rates", () => {
  const onApply = vi.fn();
  render(<RecommendationControls current="aim" measured={{ aim: 50 }} comfort={4} onApply={onApply} />);
  fireEvent.click(screen.getByRole("button", { name: /Fine-tune/ }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Search adjustable DT" }));
  fireEvent.click(screen.getByRole("button", { name: "Show maps" }));
  expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ min_rate: 1.10, max_rate: 2.00 }));
  fireEvent.change(screen.getByRole("spinbutton", { name: "Minimum DT rate" }), { target: { value: "1.105" } });
  expect(screen.getByRole("button", { name: "Show maps" })).toBeDisabled();
});

it("Star Levels: no comfort, κₛ or relevance to set; the playlist is moved toward the skill's level", () => {
  const onApply = vi.fn();
  render(<RecommendationControls current="speed" measured={{ speed: 50 }} comfort={6.4} levels={{ speed: 6.82 }} initial={{ comfort: 5, kappa: 0.8 }} onApply={onApply} />);
  fireEvent.click(screen.getByRole("button", { name: /Fine-tune/ }));
  expect(screen.queryByRole("spinbutton", { name: /Comfort difficulty/ })).toBeNull();
  expect(screen.queryByRole("spinbutton", { name: /Skill star adjustment/ })).toBeNull();
  expect(screen.queryByRole("spinbutton", { name: /relevance/ })).toBeNull();
  expect(screen.getByText(/6\.82★: your comfort level moved toward your Tapping speed level/)).toBeTruthy();
  fireEvent.change(screen.getByRole("combobox", { name: "Target skill" }), { target: { value: "consistency" } });
  expect(screen.getByText(/your comfort level \(Consistency has no measured star level\)/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Show maps" }));
  expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ skill: "consistency", comfort: undefined, kappa: 0.5, min_relevance: 0.3 }));
});

it("Star Levels: no other skill ratings to try, and none left from Comfort Score are sent (#126)", () => {
  const onApply = vi.fn();
  render(<RecommendationControls current="speed" measured={{ speed: 50 }} comfort={6.4} levels={{ speed: 6.82 }}
    initial={{ ratings: JSON.stringify({ speed: 140 }) }} onApply={onApply} />);
  expect(screen.queryByRole("button", { name: "Try other skill ratings" })).toBeNull();
  // an out-of-range rating left from a Comfort Score search neither blocks Show maps nor is sent
  fireEvent.click(screen.getByRole("button", { name: "Show maps" }));
  expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ skill: "speed", ratings: undefined }));
});

it("Comfort Score: other skill ratings can be tried", () => {
  const onApply = vi.fn();
  render(<RecommendationControls current="aim" measured={{ aim: 50 }} comfort={4} onApply={onApply} />);
  fireEvent.click(screen.getByRole("button", { name: "Try other skill ratings" }));
  fireEvent.change(screen.getByRole("spinbutton", { name: /^Jumps/ }), { target: { value: "70" } });
  fireEvent.click(screen.getByRole("button", { name: "Show maps" }));
  expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ ratings: JSON.stringify({ aim: 70 }) }));
});

it("starts from the selection applied last, and applies it again unchanged (#107)", () => {
  const onApply = vi.fn();
  const applied = {
    skill: "stamina", assessed: "stamina,speed", ratings: JSON.stringify({ speed: 70 }), comfort: 6.5,
    kappa: 0.8, min_relevance: 0.4, exclude_played: false, allow_hr: true, allow_hd: false,
    adjustable_dt: true, min_rate: 1.2, max_rate: 1.5,
  };
  render(<RecommendationControls current="aim" measured={{ aim: 50 }} comfort={4} initial={applied} onApply={onApply} />);
  expect(screen.getByRole("combobox", { name: "Target skill" })).toHaveValue("stamina");
  fireEvent.click(screen.getByRole("button", { name: /Fine-tune/ }));
  expect(screen.getByRole("checkbox", { name: "Allow Hard Rock" })).toBeChecked();
  expect(screen.getByRole("spinbutton", { name: "Minimum DT rate" })).toHaveValue(1.2);
  fireEvent.click(screen.getByRole("button", { name: "Show maps" }));
  expect(onApply).toHaveBeenCalledWith(applied);
});
