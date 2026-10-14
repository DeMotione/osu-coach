import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

/** The sample replays of the core tests, with their beatmaps, copied into a folder to scan. */
function playsFolder(): string {
  const res = path.resolve("..", "backend", "tests", "resources");
  const index = JSON.parse(fs.readFileSync(path.join(res, "index.json"), "utf-8")) as { replay: string; md5: string }[];
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "osu-coach-plays-"));
  for (const r of index) {
    fs.copyFileSync(path.join(res, "replays", r.replay), path.join(dir, r.replay));
    fs.copyFileSync(path.join(res, "maps", `${r.md5}.osu`), path.join(dir, `${r.replay}.osu`));
  }
  return dir;
}

/**
 * The layout rules of the app: nothing scrolls sideways, cards never overflow, the two cards of a row are equally
 * tall, and every tile grid is completely filled (no half-empty last row).
 */
async function layoutProblems(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const problems: string[] = [];
    const root = document.documentElement;
    if (root.scrollWidth > window.innerWidth + 1) problems.push(`page scrolls sideways (${root.scrollWidth} > ${window.innerWidth})`);
    for (const card of Array.from(document.querySelectorAll<HTMLElement>(".card"))) {
      if (card.scrollWidth > card.clientWidth + 1)
        problems.push(`card "${card.querySelector(".card__title")?.textContent}" overflows (${card.scrollWidth} > ${card.clientWidth})`);
    }
    for (const row of Array.from(document.querySelectorAll<HTMLElement>(".row"))) {
      const kids = Array.from(row.children) as HTMLElement[];
      if (kids.length !== 2) {
        problems.push(`a row has ${kids.length} cards`);
        continue;
      }
      const [a, b] = kids.map((k) => k.getBoundingClientRect());
      const sideBySide = Math.abs(a.top - b.top) < 1;
      if (sideBySide && Math.abs(a.height - b.height) > 1) problems.push(`row cards differ in height (${a.height} vs ${b.height})`);
    }
    for (const grid of Array.from(document.querySelectorAll<HTMLElement>(".tiles"))) {
      const cols = getComputedStyle(grid).gridTemplateColumns.split(" ").filter(Boolean).length;
      const n = grid.children.length;
      if (n % cols !== 0) problems.push(`${n} tiles in ${cols} columns leave a gap`);
    }
    return problems;
  });
}

const PAGES = [
  ["/overview", "Overview"],
  ["/progress", "Progress"],
  ["/aim", "Aim"],
  ["/tapping", "Tapping"],
  ["/sliders-reading", "Sliders & Reading"],
  ["/tips", "Tips & Setup"],
  ["/maps", "Map Suggestion"],
  ["/skills", "Skill Development"],
  ["/skills?tab=playlist", "Skill Development"],
  ["/replays", "Your replays"],
] as const;

test.describe.configure({ mode: "serial" });

test("pages explain what to do before anything is analysed", async ({ page }) => {
  await page.goto("/overview");
  await expect(page.getByText("No replays analysed yet", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Go to Replays" }).click();
  await expect(page).toHaveURL(/\/replays$/);
  await expect(page.getByText("Scan for replays first")).toBeVisible();
});

test("scan, analyse and read every page", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

  await page.goto("/replays");
  await page.getByLabel("Extra folders (one per line)").fill(playsFolder());
  await page.getByRole("button", { name: "Scan" }).click();
  await expect(page.getByText(/10 osu!standard replays/)).toBeVisible({ timeout: 120_000 });
  await page.getByLabel("Player").selectOption("*");
  await expect(page.getByText(/10 replays of all players will be analysed/)).toBeVisible();
  await page.getByRole("button", { name: "Analyse replays" }).click();
  await expect(page.getByText(/^Analysed 10 replays/)).toBeVisible({ timeout: 300_000 });
  await expect(page.getByRole("heading", { name: "Analysed replays (10)" })).toBeVisible();
  await expect(page.locator(".status-line")).toContainText("10 replays");

  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const [url, title] of PAGES) {
      await page.goto(url);
      await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
      await expect(page.locator(".skeleton")).toHaveCount(0, { timeout: 60_000 });
      await page.waitForTimeout(400);       // charts lay out after their card has its size
      const chartHeights = () => page.locator(".chart").evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().height)));
      const before = await chartHeights();
      await page.waitForTimeout(1000);
      expect(await chartHeights(), `charts grew on ${url} at ${width}px`).toEqual(before);
      expect(await layoutProblems(page), `${url} at ${width}px`).toEqual([]);
    }
  }
  expect(errors).toEqual([]);
});

test("open a replay from the list in Detailed Map Analysis", async ({ page }) => {
  await page.goto("/replays");
  await page.getByRole("row", { name: /Miraie/ }).click();
  await page.getByRole("button", { name: "Detailed map analysis" }).click();
  await expect(page).toHaveURL(/\/check\?path=/);
  await expect(page.getByRole("heading", { name: "Misses and combo breaks" })).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText(/30 misses/)).toBeVisible();
  await expect(page.getByLabel("Only plays of this map")).toBeChecked();
  await expect(page.getByRole("heading", { name: "Timing through the map" })).toBeVisible();
  expect(await layoutProblems(page)).toEqual([]);
});

test("settings are remembered: best replays and the level set by hand", async ({ page, request }) => {
  await page.goto("/replays");
  await page.getByText("Best replays", { exact: true }).click();
  await expect.poll(async () => (await (await request.get("/api/settings")).json()).replay_set).toBe("best");
  await page.goto("/overview");
  const manual = page.locator("label.switch", { hasText: "Set my level by hand" });
  await manual.click();
  await expect(page.getByLabel("Set my level by hand")).toBeChecked();
  await expect.poll(async () => (await (await request.get("/api/settings")).json()).level_override).not.toBeNull();
  await expect(page.getByText(/^Set by you\./)).toBeVisible();
  await manual.click();
  await expect.poll(async () => (await (await request.get("/api/settings")).json()).level_override).toBeNull();
  await page.goto("/replays");
  await page.getByText("All replays", { exact: true }).click();
  await expect.poll(async () => (await (await request.get("/api/settings")).json()).replay_set).toBe("all");
});

test("the sidebar navigates, folds with Ctrl+B and remembers it", async ({ page }) => {
  await page.goto("/replays");
  const nav = page.getByRole("navigation", { name: "Pages" });
  await nav.getByRole("link", { name: "Aim" }).click();
  await expect(page).toHaveURL(/\/aim$/);
  await expect(page.getByTestId("toolbar-title")).not.toHaveClass(/shown/);
  await expect(nav.getByRole("link", { name: "Aim" })).toHaveClass(/active/);
  await expect(page.getByRole("button", { name: "Back" })).toHaveCount(0);
  await nav.getByRole("link", { name: "Overview" }).click();
  await expect(page).toHaveURL(/\/overview$/);
  await nav.getByRole("link", { name: /^Replays/ }).click();
  await expect(page).toHaveURL(/\/replays$/);
  await page.keyboard.press("Control+b");
  await expect(page.locator(".app")).toHaveClass(/is-rail/);
  await page.reload();
  await expect(page.locator(".app")).toHaveClass(/is-rail/);
  await page.getByRole("button", { name: "Show sidebar" }).click();
  await expect(page.locator(".app")).not.toHaveClass(/is-rail/);
  await page.setViewportSize({ width: 390, height: 800 });
  await expect(nav).toBeHidden();
  await page.getByRole("button", { name: "Menu" }).click();
  await expect(nav.getByRole("link", { name: "Overview" })).toBeVisible();
});

test("the API reference and the installable app", async ({ page, request }) => {
  const docs = await request.get("/docs");
  expect(docs.ok()).toBe(true);
  expect(await docs.text()).toContain("/api/openapi.json");
  const manifest = await request.get("/manifest.webmanifest");
  expect(manifest.headers()["content-type"]).toBe("application/manifest+json");
  expect((await manifest.json()).icons).toHaveLength(3);
  await page.goto("/overview");
  await expect.poll(() => page.evaluate(async () => !!(await navigator.serviceWorker.getRegistration())), { timeout: 30_000 }).toBe(true);
});
