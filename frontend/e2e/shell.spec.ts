import { expect, test } from "@playwright/test";

for (const desktop of [false, true]) {
  for (const width of [1440, 390]) {
    test(`content scrolls between the bars (${desktop ? "desktop shell" : "browser shell"}, ${width}px)`, async ({ page }) => {
      await page.setViewportSize({ width, height: 700 });
      await page.goto("/replays");
      if (desktop) {
        // Exercise the desktop geometry without requiring native window APIs in Chromium.
        await page.locator("html").evaluate((el) => el.classList.add("is-desktop"));
        await page.locator(".toolbar").evaluate((el) => el.classList.add("toolbar--desktop"));
      }
      const scroll = page.locator(".workspace__scroll");
      await expect(page.getByRole("heading", { level: 1, name: "Your replays" })).toBeVisible();
      await page.locator(".main").evaluate((el) => { el.style.minHeight = "2000px"; });
      const bars = await page.locator(".toolbar, .statusbar").evaluateAll((els) =>
        els.map((el) => ({ top: el.getBoundingClientRect().top, bottom: el.getBoundingClientRect().bottom })),
      );
      const bounds = await scroll.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.y).toBeCloseTo(bars[0].bottom, 0);
      expect(bounds!.y + bounds!.height).toBeCloseTo(bars[1].top, 0);
      await scroll.evaluate((el) => el.scrollTo(0, 500));
      await expect(page.getByTestId("toolbar-title")).toHaveClass(/shown/);
      expect(await page.evaluate(() => window.scrollY)).toBe(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
      expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBe(700);
      expect(await page.locator(".toolbar, .statusbar").evaluateAll((els) =>
        els.map((el) => ({ top: el.getBoundingClientRect().top, bottom: el.getBoundingClientRect().bottom })),
      )).toEqual(bars);
      if (width < 961) await page.getByRole("button", { name: "Menu" }).click();
      await page.getByRole("navigation", { name: "Pages" }).getByRole("link", { name: "Overview" }).click();
      await expect.poll(() => scroll.evaluate((el) => el.scrollTop)).toBe(0);
      await expect(page.getByTestId("toolbar-title")).not.toHaveClass(/shown/);
    });
  }
}

test("sidebar animates both ways and respects reduced motion", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/replays");
  const sidebar = page.locator(".sidebar");
  await expect(sidebar).toHaveCSS("width", "248px");
  for (const collapsed of [true, false]) {
    const widths = await page.evaluate(async () => {
      const sidebar = document.querySelector<HTMLElement>(".sidebar")!;
      const app = document.querySelector<HTMLElement>(".app")!;
      const before = sidebar.getBoundingClientRect().width;
      document.querySelector<HTMLButtonElement>(".toolbar__fold")!.click();
      await new Promise((resolve) => requestAnimationFrame(resolve));
      // hold the running transition at its midpoint instead of sampling by wall-clock time, which is flaky on slow runners
      const transition = app
        .getAnimations()
        .find((a): a is CSSTransition => a instanceof CSSTransition && a.transitionProperty === "grid-template-columns");
      if (!transition) throw new Error("the sidebar width is not animated");
      transition.pause();
      transition.currentTime = Number(transition.effect!.getComputedTiming().duration) / 2;
      const during = sidebar.getBoundingClientRect().width;
      transition.finish();
      return { before, during, after: sidebar.getBoundingClientRect().width };
    });
    expect(widths.after).toBe(collapsed ? 68 : 248);
    expect(widths.during).toBeGreaterThan(68);
    expect(widths.during).toBeLessThan(248);
    expect(widths.before).toBe(collapsed ? 248 : 68);
  }
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.getByRole("button", { name: "Hide sidebar" }).click();
  await expect(sidebar).toHaveCSS("width", "68px");
  expect(await page.locator(".app").evaluate((el) => parseFloat(getComputedStyle(el).transitionDuration))).toBeLessThan(0.001);
  await page.setViewportSize({ width: 390, height: 700 });
  await page.getByRole("button", { name: "Menu" }).click();
  await expect(page.locator(".sidenav__text").first()).toHaveCSS("opacity", "1");
  await expect(page.getByRole("navigation", { name: "Pages" })).toBeVisible();
});
