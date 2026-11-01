import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ModsIcons } from "./ModsIcons";

describe("ModsIcons", () => {
  it("leaves no-mod suggestions empty", () => {
    const { container, rerender } = render(<ModsIcons mods="NM" />);
    expect(container).toBeEmptyDOMElement();
    rerender(<ModsIcons mods={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows each supplied icon and names combined mods", () => {
    const { rerender } = render(<ModsIcons mods="HR" />);
    expect(screen.getByRole("img", { name: "Hard Rock" }).querySelector("img")?.getAttribute("src")).toBe("/mod-hard-rock.svg");

    rerender(<ModsIcons mods="HDHRDT" />);
    const icons = screen.getByRole("img", { name: "Hidden, Hard Rock, Double Time" }).querySelectorAll("img");
    expect(Array.from(icons, (icon) => icon.getAttribute("src"))).toEqual([
      "/mod-hidden.svg", "/mod-hard-rock.svg", "/mod-double-time.svg",
    ]);
    expect(Array.from(icons, (icon) => icon.getAttribute("alt"))).toEqual(["", "", ""]);
  });

  it("keeps unfamiliar mods visible", () => {
    const { container } = render(<ModsIcons mods="NC" />);
    expect(container.textContent).toBe("NC");
  });
});
