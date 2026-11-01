import { expect, test } from "@playwright/test";

test("custom DT badge fits desktop rows and narrow map cards", async ({ page }) => {
  await page.goto("/maps"); // Load the app's production styles and public icon assets.
  expect((await page.request.get("/mod-double-time-custom.svg")).ok()).toBe(true);
  const css = await page.locator('link[rel="stylesheet"]').first().getAttribute("href");
  expect(css).toBeTruthy();

  const cells = (custom: boolean, hide: boolean) => {
    const badge = '<span class="map-mods__badge"><span class="map-mods__badge-rate">1.36×</span></span>';
    const regular = '<img src="/mod-double-time.svg" alt="">';
    const mods = `<span class="map-mods">${custom ? badge : regular}<img src="/mod-hidden.svg" alt=""><img src="/mod-hard-rock.svg" alt=""></span>`;
    return `<td class="wrap strong" data-label="Map">Pyxis – Koise yo Minna, Hai! (TV Size) [Hai!]</td>
      <td data-label="Mods">${mods}</td><td data-label="Difficulty">6.94 ★</td>
      <td data-label="BPM">218</td><td data-label="AR">10.1</td><td data-label="Length">0:22</td>
      <td class="wrap" data-label="Why this map">Jumps to practise</td><td data-label="Skill demand">61.4</td>
      <td data-label="F(m)">-0.7844</td><td data-label="Breakdown">Calculation</td><td data-label="Link">open ↗</td>
      ${hide ? '<td><button>Hide</button></td>' : ""}`;
  };
  await page.setContent(`<link rel="stylesheet" href="${css}"><div class="map-table"><div class="table-wrap">
    <table class="table"><tbody><tr id="custom">${cells(true, false)}</tr><tr id="regular">${cells(false, false)}</tr>
    <tr id="hide">${cells(true, true)}</tr></tbody></table></div></div>`);
  await page.locator(".map-mods__badge").first().evaluate((el) => document.fonts.ready.then(() => el.getBoundingClientRect()));

  await page.setViewportSize({ width: 1280, height: 820 });
  const heights = await page.locator("#custom, #regular").evaluateAll((rows) => rows.map((row) => row.getBoundingClientRect().height));
  expect(heights[0]).toBeLessThanOrEqual(heights[1] + 1);
  expect(await page.locator(".map-mods__badge").first().evaluate((el) => getComputedStyle(el).height)).toBe("18px");

  for (const width of [1100, 900]) {
    await page.setViewportSize({ width, height: 820 });
    expect(await page.locator(".table-wrap").evaluate((el) => el.scrollWidth - el.clientWidth), `${width}px`).toBeLessThanOrEqual(1);
  }

  await page.setViewportSize({ width: 390, height: 820 });
  for (const row of await page.locator("#custom, #hide").all()) {
    const ragged = await row.evaluate((tr) => {
      const lines = new Map<number, number>();
      for (const td of Array.from(tr.children)) {
        const rect = td.getBoundingClientRect();
        lines.set(Math.round(rect.top), (lines.get(Math.round(rect.top)) ?? 0) + rect.width);
      }
      return [...lines.values()].some((width) => Math.abs(width - tr.clientWidth) > 2);
    });
    expect(ragged).toBe(false);
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);

  await page.setContent(`<link rel="stylesheet" href="${css}"><div class="map-table map-table--compact"><div class="table-wrap">
    <table class="table"><tbody><tr id="compact">
      <td data-label="Map">Pyxis – Koise yo Minna, Hai! (TV Size) [Hai!]</td>
      <td data-label="Mods"><span class="map-mods"><span class="map-mods__badge"><span class="map-mods__badge-rate">1.36×</span></span><img src="/mod-hidden.svg" alt=""><img src="/mod-hard-rock.svg" alt=""></span></td>
      <td data-label="Difficulty">6.94 ★</td><td data-label="BPM">218</td><td data-label="Length">0:22</td>
      <td data-label="Skill demand">61.4</td><td data-label="F(m)">-0.7844</td>
      <td data-label="Breakdown">Calculation</td><td data-label="Link">open ↗</td>
    </tr></tbody></table></div></div>`);
  const compactRagged = await page.locator("#compact").evaluate((tr) => {
    const lines = new Map<number, number>();
    for (const td of Array.from(tr.children)) {
      const rect = td.getBoundingClientRect();
      lines.set(Math.round(rect.top), (lines.get(Math.round(rect.top)) ?? 0) + rect.width);
    }
    return [...lines.values()].some((width) => Math.abs(width - tr.clientWidth) > 2);
  });
  expect(compactRagged).toBe(false);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});
