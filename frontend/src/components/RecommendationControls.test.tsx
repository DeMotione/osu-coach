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
