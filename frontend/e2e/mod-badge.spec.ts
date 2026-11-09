import { expect, test } from "@playwright/test";

test("custom DT badge fits desktop rows and narrow map cards", async ({ page }) => {
  await page.goto("/maps"); // Load the app's production styles and public icon assets.
  expect((await page.request.get("/mod-double-time-custom.svg")).ok()).toBe(true);
  const css = await page.locator('link[rel="stylesheet"]').first().getAttribute("href");
  expect(css).toBeTruthy();

  // as MapTable draws them: F(m) opens its calculation, the link column is two icon buttons
  const score = '<details class="map-breakdown"><summary>-0.7844</summary><dl><div><dt>Stars</dt><dd>-0.03</dd></div></dl></details>';
  const icon = '<svg viewBox="0 0 24 24" width="16" height="16"></svg>';
  const links = `<span class="map-links"><a class="btn btn--sm btn--ghost btn--icon">${icon}</a>` +
    `<button class="btn btn--sm btn--ghost btn--icon">${icon}</button></span>`;
  const head = ["Map", "Mods", "Difficulty", "BPM", "AR", "Length", "Why this map", "Skill demand", "F(m)", "Link", ""]
    .map((h, i) => `<th class="${i === 7 ? "center" : ""}"><button>${h}</button></th>`).join("");
  const cells = (custom: boolean, hide: boolean) => {
    const badge = '<span class="map-mods__badge"><span class="map-mods__badge-rate">1.36×</span></span>';
    const regular = '<img src="/mod-double-time.svg" alt="">';
    const mods = `<span class="map-mods">${custom ? badge : regular}<img src="/mod-hidden.svg" alt=""><img src="/mod-hard-rock.svg" alt=""></span>`;
    return `<td class="wrap strong" data-label="Map">Pyxis – Koise yo Minna, Hai! (TV Size) [Hai!]</td>
      <td data-label="Mods">${mods}</td><td data-label="Difficulty">6.94 ★</td>
      <td data-label="BPM">218</td><td data-label="AR">10.1</td><td data-label="Length">0:22</td>
      <td class="wrap" data-label="Why this map">evenly hard from start to end (73%)</td>
      <td class="center" data-label="Skill demand">61.4</td>
      <td class="num" data-label="F(m)">${score}</td><td data-label="Link">${links}</td>
      ${hide ? '<td><button class="btn btn--ghost btn--sm">Hide</button></td>' : ""}`;
  };
  await page.setContent(`<link rel="stylesheet" href="${css}"><div class="map-table"><div class="table-wrap">
    <table class="table"><thead><tr>${head}</tr></thead><tbody><tr id="custom">${cells(true, false)}</tr><tr id="regular">${cells(false, false)}</tr>
    <tr id="hide">${cells(true, true)}</tr></tbody></table></div></div>`);
  await page.locator(".map-mods__badge").first().evaluate((el) => document.fonts.ready.then(() => el.getBoundingClientRect()));

  await page.setViewportSize({ width: 1280, height: 820 });
  const heights = await page.locator("#custom, #regular").evaluateAll((rows) => rows.map((row) => row.getBoundingClientRect().height));
  expect(heights[0]).toBeLessThanOrEqual(heights[1] + 1);
  expect(await page.locator(".map-mods__badge").first().evaluate((el) => getComputedStyle(el).height)).toBe("18px");

  // a table at every width down to the cards, without a sideways scrollbar (with Hide: the widest rows)
  for (const width of [1440, 1280, 1130, 1121, 1100, 900, 880]) {
    await page.setViewportSize({ width, height: 820 });
    expect(await page.locator(".table-wrap").evaluate((el) => el.scrollWidth - el.clientWidth), `${width}px`).toBeLessThanOrEqual(1);
  }
  // Skill demand: a narrow column with the number in its middle
  await page.setViewportSize({ width: 1280, height: 820 });
  const demand = await page.locator("#regular td:nth-child(8)").evaluate((td) => {
    const range = document.createRange();
    range.selectNodeContents(td);
    const text = range.getBoundingClientRect();
    const cell = td.getBoundingClientRect();
    return { width: cell.width, left: text.left - cell.left, right: cell.right - text.right, align: getComputedStyle(td).textAlign };
  });
  expect(demand.align).toBe("center");
  expect(Math.abs(demand.left - demand.right)).toBeLessThanOrEqual(2);
  expect(demand.width).toBeLessThan(110);

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
      <td class="center" data-label="Skill demand">61.4</td><td class="num" data-label="F(m)">-0.7844</td>
      <td data-label="Link">open ↗</td>
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
