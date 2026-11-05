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
