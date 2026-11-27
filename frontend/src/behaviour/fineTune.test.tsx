/**
 * Behaviour: Fine-tune on Goals & Training → Playlist for a skill. A failing test here means the app broke a rule:
 * fix the code, not the test (see "Behaviour tests" in AGENTS.md).
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RecommendationControls } from "../components/RecommendationControls";

const measured = { aim: 50, speed: 60, sliders: 55, accuracy: 45, reading: 40, consistency: 30 };

describe("Fine-tune", () => {
  it("doesn't offer accuracy, reading or consistency as skills to check maps on (#149)", () => {
    const onApply = vi.fn();
    render(<RecommendationControls current="aim" measured={measured} comfort={6.6} onApply={onApply} />);
    fireEvent.click(screen.getByRole("button", { name: /Fine-tune/ }));
    for (const name of ["Accuracy", "Reading", "Consistency"]) expect(screen.queryByRole("checkbox", { name })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show maps" }));
    expect(onApply).toHaveBeenLastCalledWith(expect.objectContaining({ assessed: "aim,speed,sliders" }));
  });

  it("keeps to the approach rates around your level unless you choose any AR or a range", () => {
    const onApply = vi.fn();
    render(<RecommendationControls current="aim" measured={measured} comfort={6.6} levelAr={[9.1, 9.7]} onApply={onApply} />);
    fireEvent.click(screen.getByRole("button", { name: "Show maps" }));
    expect(onApply).toHaveBeenLastCalledWith(expect.objectContaining({ ar: undefined })); // around the level
    fireEvent.click(screen.getByRole("button", { name: /Fine-tune/ }));
    expect(screen.getByRole("radio", { name: "Around your level (9.1–9.7)" })).toBeChecked();
    fireEvent.click(screen.getByRole("radio", { name: "Any AR" }));
    fireEvent.click(screen.getByRole("button", { name: "Show maps" }));
    expect(onApply).toHaveBeenLastCalledWith(expect.objectContaining({ ar: "any" }));
  });
});
