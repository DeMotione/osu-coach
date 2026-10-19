import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FileChips } from "./ui";

const files = (n: number) => Array.from({ length: n }, (_, i) => ({ id: `f${i}`, name: `replay ${i + 1}.osr`, path: `/r/${i}.osr` }));

describe("FileChips", () => {
  it("names the first 15 files and counts the rest", () => {
    const { container } = render(<FileChips files={files(1250)} />);
    expect(container.querySelectorAll(".chip")).toHaveLength(16);
    expect(screen.getByText("replay 15.osr")).toBeInTheDocument();
    expect(screen.queryByText("replay 16.osr")).toBeNull();
    expect(screen.getByText("and 1,235 more")).toBeInTheDocument();
  });

  it("names every file when they fit", () => {
    const { container } = render(<FileChips files={files(15)} />);
    expect(container.querySelectorAll(".chip")).toHaveLength(15);
    expect(screen.queryByText(/more$/)).toBeNull();
  });

  it("shows nothing before files are added", () => {
    const { container } = render(<FileChips files={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
