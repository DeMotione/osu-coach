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
    const icons = screen.getByRole("img", { name: "Double Time, Hidden, Hard Rock" }).querySelectorAll("img");
    expect(Array.from(icons, (icon) => icon.getAttribute("src"))).toEqual([
      "/mod-double-time.svg", "/mod-hidden.svg", "/mod-hard-rock.svg",
    ]);
    expect(Array.from(icons, (icon) => icon.getAttribute("alt"))).toEqual(["", "", ""]);
  });

  it("keeps unfamiliar mods visible", () => {
    const { container } = render(<ModsIcons mods="NC" />);
    expect(container.textContent).toBe("NC");
  });

  it("puts a custom DT rate on the badge, before other mods", () => {
    render(<ModsIcons mods="HDHRDT" rate={1.36} />);
    const group = screen.getByRole("img", { name: "Double Time 1.36×, Hidden, Hard Rock" });
    expect(group.firstElementChild).toHaveClass("map-mods__badge");
    expect(group.querySelector(".map-mods__badge-rate")).toHaveTextContent("1.36×");
    expect(Array.from(group.querySelectorAll("img"), (icon) => icon.getAttribute("src"))).toEqual([
      "/mod-hidden.svg", "/mod-hard-rock.svg",
    ]);
  });

  it("keeps the ordinary DT icon at 1.50×", () => {
    render(<ModsIcons mods="DT" rate={1.5} />);
    const group = screen.getByRole("img", { name: "Double Time" });
    expect(group.querySelector("img")?.getAttribute("src")).toBe("/mod-double-time.svg");
    expect(group.querySelector(".map-mods__badge")).toBeNull();
  });

  it("keeps a non-DT speed visible in Mods and leaves NM at 1× blank", () => {
    const { container, rerender } = render(<ModsIcons mods="NM" rate={1} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<ModsIcons mods="HR" rate={1.2} />);
    expect(screen.getByRole("img", { name: "Hard Rock, 1.20×" })).toHaveTextContent("1.20×");
    rerender(<ModsIcons mods="NC" rate={1.2} />);
    expect(container).toHaveTextContent("NC · 1.20×");
  });
});
