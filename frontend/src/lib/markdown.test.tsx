import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Md } from "./markdown";

describe("inline markdown", () => {
  it("renders bold, italic and code", () => {
    const { container } = render(
      <p>
        <Md>{"In osu!lazer open **Settings → General** and click *previous osu! install* or `F5`."}</Md>
      </p>,
    );
    expect(container.querySelector("strong")?.textContent).toBe("Settings → General");
    expect(container.querySelector("em")?.textContent).toBe("previous osu! install");
    expect(container.querySelector("code")?.textContent).toBe("F5");
    expect(container.textContent).toBe("In osu!lazer open Settings → General and click previous osu! install or F5.");
  });

  it("never turns text into markup", () => {
    const { container } = render(
      <p>
        <Md>{'<img src=x onerror="alert(1)"> **<b>bold</b>**'}</Md>
      </p>,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror="alert(1)">');
  });

  it("leaves lone asterisks alone", () => {
    const { container } = render(
      <p>
        <Md>{"5* maps and 3 * 4"}</Md>
      </p>,
    );
    expect(container.querySelector("em")).toBeNull();
    expect(container.textContent).toBe("5* maps and 3 * 4");
  });
});
