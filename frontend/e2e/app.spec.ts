import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const RES = path.resolve("..", "backend", "tests", "resources");
const INDEX = JSON.parse(fs.readFileSync(path.join(RES, "index.json"), "utf-8")) as { replay: string; md5: string }[];

/** The sample replays of the core tests, with their beatmaps, copied into a folder to scan. */
function playsFolder(): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "osu-coach-plays-"));
  for (const r of INDEX) {
    fs.copyFileSync(path.join(RES, "replays", r.replay), path.join(dir, r.replay));
    fs.copyFileSync(path.join(RES, "maps", `${r.md5}.osu`), path.join(dir, `${r.replay}.osu`));
  }
  return dir;
}

/** An osu!stable folder with the sample replays in Data/r and their beatmaps in Songs, where detection won't look. */
function stableInstall(): string {
  const root = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "osu-coach-stable-")), "osu!");
  fs.mkdirSync(path.join(root, "Data", "r"), { recursive: true });
  for (const r of INDEX) {
    fs.copyFileSync(path.join(RES, "replays", r.replay), path.join(root, "Data", "r", r.replay));
    fs.mkdirSync(path.join(root, "Songs", r.md5), { recursive: true });
    fs.copyFileSync(path.join(RES, "maps", `${r.md5}.osu`), path.join(root, "Songs", r.md5, `${r.md5}.osu`));
  }
  return root;
}

/** The setup guide's dialog fits the window: nothing scrolls sideways, in the page or in the step. */
async function guideProblems(page: Page): Promise<string[]> {
  const problems: string[] = [];
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 800 });
    problems.push(
      ...(await page.evaluate((w) => {
        const out: string[] = [];
        if (document.documentElement.scrollWidth > window.innerWidth + 1) out.push(`page scrolls sideways at ${w}px`);
        for (const el of Array.from(document.querySelectorAll<HTMLElement>(".onboarding__dialog, .onboarding__content, .onboarding__foot")))
          if (el.scrollWidth > el.clientWidth + 1) out.push(`${el.className} overflows at ${w}px (${el.scrollWidth} > ${el.clientWidth})`);
        return out;
      }, width)),
    );
  }
  return problems;
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
  ["/maps", "Skill Development"],
  ["/skills", "Goals & Training"],
  ["/skills?tab=playlist", "Goals & Training"],
  ["/replays", "Your replays"],
] as const;

test.describe.configure({ mode: "serial" });

test("the setup guide opens on the first start and can be skipped", async ({ page, request }) => {
  await page.goto("/replays");
  const guide = page.getByRole("dialog", { name: "Set up osu! coach" });
  await expect(guide.getByRole("heading", { name: "Which osu! do you play?" })).toBeVisible();
  expect(await guideProblems(page)).toEqual([]);
  await guide.getByRole("button", { name: "Skip setup" }).click();
  await expect(guide).toHaveCount(0);
  expect((await (await request.get("/api/settings")).json()).onboarded).toBe(true);
  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: "Your replays" })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test.describe("after the setup", () => {
  test.beforeEach(async ({ request }) => {
    await request.patch("/api/settings", { data: { onboarded: true } });
  });

  test("pages explain what to do before anything is analysed", async ({ page }) => {
    await page.goto("/overview");
    await expect(page.getByRole("main").getByText("No replays analysed yet", { exact: true })).toBeVisible();
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
    await expect(page.getByText(/^Found 10 osu!standard replays/)).toBeVisible({ timeout: 120_000 });
    // the scan finds every replay; how many of them to analyse is chosen in the Analyse card (#36)
    const card = (title: string) => page.locator(".card", { has: page.getByRole("heading", { name: title }) });
    await expect(card("1 · Find replays").getByRole("radiogroup", { name: "Replays to read" })).toHaveCount(0);
    await expect(card("2 · Analyse").getByRole("radiogroup", { name: "Replays to read" })).toBeVisible();
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

  test("a replay that can't be opened in Detailed Map Analysis leads back to the list (#17)", async ({ page }) => {
    await page.goto(`/check?path=${encodeURIComponent(path.join(playsFolder(), "gone.osr"))}`);
    await expect(page.getByText("The replay file is no longer on this computer.")).toBeVisible();
    await page.getByRole("button", { name: "Back to your replays" }).click();
    await expect(page).toHaveURL(/\/check$/);
    await expect(page.getByRole("combobox", { name: "Replay" }).locator("option")).not.toHaveCount(0);
    expect(await layoutProblems(page)).toEqual([]);
  });

  test("settings are remembered: best replays and the level set by hand", async ({ page, request }) => {
    await page.goto("/replays");
    await page.getByText("Best replays", { exact: true }).click();
    await expect.poll(async () => (await (await request.get("/api/settings")).json()).replay_set).toBe("best");
    await page.goto("/overview");
    const level = async () => (await (await request.get("/api/settings")).json()).level_override;
    const manual = page.locator("label.switch", { hasText: "Set my level by hand" });
    const status = page.locator(".apply-status");
    await manual.click();
    await expect(page.getByLabel("Set my level by hand")).toBeChecked();
    // nothing changes until Apply (#30)
    await expect(status).toHaveText("Not applied yet: press Apply.");
    expect(await level()).toBeNull();
    await page.getByLabel("My level (★)").fill("15");
    await expect(status).toHaveText("Enter a level from 1 to 12★.");
    await expect(page.getByRole("button", { name: "Apply" })).toBeDisabled();
    await page.getByLabel("My level (★)").fill("5.5");
    await page.getByRole("button", { name: "Apply" }).click();
    await expect(status).toHaveText("Applied: every number on this page now uses 5.5★.");
    expect(await level()).toBe(5.5);
    await expect(page.getByText(/^Set by you\./)).toBeVisible();
    await expect(page.getByText("Your level: 5.50★")).toBeVisible();
    await expect(page.getByRole("button", { name: "Apply" })).toBeDisabled();
    await manual.click();
    await expect(status).toHaveText(/^Back to the detected level/);
    expect(await level()).toBeNull();
    await page.goto("/replays");
    await page.getByText("All replays", { exact: true }).click();
    await expect.poll(async () => (await (await request.get("/api/settings")).json()).replay_set).toBe("all");
  });

  test("the sidebar navigates, folds with Ctrl+B and remembers it", async ({ page }) => {
    await page.goto("/replays");
    const nav = page.getByRole("navigation", { name: "Pages" });
    await nav.getByRole("link", { name: "Aim" }).click();
    await expect(page).toHaveURL(/\/aim$/);
    await expect(page.getByTestId("toolbar-title")).toHaveText("Aim"); // the pages have no visible heading
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

  test("map tables are tables at the desktop app's opening size, tidy cards when narrower (#31)", async ({ page }) => {
    for (const path of ["/maps", "/skills?tab=playlist"]) {
      for (const [width, mode] of [[1280, "table"], [1100, "cards"], [390, "cards"]] as const) {
        await page.setViewportSize({ width, height: 820 });
        await page.goto(path);
        const table = page.locator(".map-table table").first();
        await expect(table).toBeVisible({ timeout: 60_000 });
        expect(await table.evaluate((t) => getComputedStyle(t).display), `${path} at ${width}px`).toBe(mode === "table" ? "table" : "block");
        if (mode === "cards") {
          // every line of a card is filled: its cells add up to the card's width
          const ragged = await page.locator(".map-table tbody tr").first().evaluate((tr) => {
            const lines = new Map<number, number>();
            for (const td of Array.from(tr.children)) {
              const r = td.getBoundingClientRect();
              lines.set(Math.round(r.top), (lines.get(Math.round(r.top)) ?? 0) + r.width);
            }
            return [...lines.values()].filter((w) => Math.abs(w - tr.clientWidth) > 2).length;
          });
          expect(ragged, `${path} at ${width}px`).toBe(0);
        }
        expect(await layoutProblems(page), `${path} at ${width}px`).toEqual([]);
      }
    }
  });

  test("Add goal opens a dialog with a button per skill; a skill with a goal can't get a second one", async ({ page }) => {
    await page.goto("/skills");
    await page.getByRole("button", { name: "Add goal" }).click();
    const dialog = page.getByRole("dialog", { name: "Add a goal" });
    await expect(dialog).toBeVisible();
    expect(await layoutProblems(page)).toEqual([]);
    const skill = dialog.getByRole("group", { name: "Skill" }).getByRole("button").and(page.locator(":enabled")).first();
    const name = (await skill.locator("span").innerText()).trim();
    await skill.click();
    await dialog.getByRole("button", { name: "2 weeks" }).click();
    await dialog.getByRole("button", { name: "Add goal" }).click();
    await expect(dialog).toBeHidden();
    await expect(page.locator(".goal__title").filter({ hasText: name })).toBeVisible();
    // the dialog again: that skill is taken now, and listed under Your goals
    await page.getByRole("button", { name: "Add goal" }).click();
    await expect(dialog.locator(".chip").filter({ hasText: name })).toBeVisible();
    await expect(dialog.getByRole("button", { name: new RegExp(`^${name}`) })).toBeDisabled();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });

  test("playlist stages show five maps each, and Other maps shows the next five", async ({ page }) => {
    await page.goto("/skills?tab=playlist");
    const tables = page.locator(".map-table");
    await expect(tables.first()).toBeVisible({ timeout: 60_000 });
    await expect(page.locator(".map-pagination")).toHaveCount(0);
    for (const table of await tables.all()) expect(await table.locator("tbody tr").count()).toBeLessThanOrEqual(5);
    const stage = page.locator(".card").filter({ has: page.getByRole("button", { name: "Other maps" }) }).first();
    if (await stage.count()) {
      const firstMap = () => stage.locator(".map-table tbody tr").first().locator("td").first().innerText();
      const before = await firstMap();
      await expect(stage.getByText(/showing 1–5 of \d+/)).toBeVisible();
      await stage.getByRole("button", { name: "Other maps" }).click();
      await expect(stage.getByText(/showing 6–\d+ of \d+/)).toBeVisible();
      expect(await firstMap()).not.toBe(before);
    }
    expect(await layoutProblems(page)).toEqual([]);
  });

  test("a big drop of replay files names only the first 15 (#37)", async ({ page }) => {
    await page.goto("/replays");
    const files = INDEX.flatMap((r) => [path.join(RES, "replays", r.replay), path.join(RES, "maps", `${r.md5}.osu`)]);
    await page.locator(".dropzone input[type=file]").setInputFiles(files);
    await expect(page.getByText(`and ${files.length - 15} more`)).toBeVisible();
    await expect(page.locator(".file-list .chip")).toHaveCount(16);
    expect(await layoutProblems(page)).toEqual([]);
  });

  test("replay files added by hand stay when more are added later (#38)", async ({ page, request }) => {
    const mine = INDEX.filter((r) => r.replay.startsWith("mot1one__"));
    const files = (r: (typeof INDEX)[number]) => [path.join(RES, "replays", r.replay), path.join(RES, "maps", `${r.md5}.osu`)];
    const library = async () => (await (await request.get("/api/library")).json()) as { replays: number; files: unknown[] };
    await page.goto("/replays");
    await page.getByText("Only these files", { exact: true }).click();
    // the drop zone of this mode replaces the other one: drop only once it is there
    await expect(page.getByText(/^Drop the replay files to analyse/)).toBeVisible();
    const drop = page.locator(".dropzone input[type=file]");
    await drop.setInputFiles([...files(mine[0]), ...files(mine[1])]);
    await page.getByRole("button", { name: "Scan", exact: true }).click();
    await expect.poll(async () => (await library()).replays, { timeout: 120_000 }).toBe(2);
    // later (the page opened again): the two are still there, and one more joins them
    await page.reload();
    await expect(page.getByText("Added files (4)", { exact: true })).toBeVisible();
    await drop.setInputFiles(files(mine[2]));
    await expect(page.getByText(/^Added files \(6\) · 2 new/)).toBeVisible();
    await page.getByRole("button", { name: "Scan", exact: true }).click();
    await expect.poll(async () => (await library()).replays, { timeout: 120_000 }).toBe(3);
    expect(await layoutProblems(page)).toEqual([]);
    await page.getByRole("button", { name: "Clear", exact: true }).click();
    await expect(page.getByText(/^Added files \(/)).toHaveCount(0);
    expect((await library()).files).toEqual([]);
    await page.getByText(/^My replays/).click(); // back to the osu! installs for the tests after this one
  });

  test("players of deleted replays leave the Analyse card at the next scan (#35)", async ({ page }) => {
    const folder = fs.mkdtempSync(path.join(os.tmpdir(), "osu-coach-deleted-"));
    for (const r of INDEX.filter((x) => x.replay.startsWith("mot1one__")).slice(0, 2))
      fs.copyFileSync(path.join(RES, "replays", r.replay), path.join(folder, r.replay));
    const folders = page.getByLabel("Extra folders (one per line)");
    const scan = async (found: number) => {
      await page.getByRole("button", { name: "Scan", exact: true }).click();
      await expect(page.getByText(new RegExp(`^Found ${found} osu!standard replays`))).toBeVisible({ timeout: 120_000 });
    };
    await page.goto("/replays");
    await folders.fill(folder);
    await scan(2);
    await expect(page.getByLabel("Player")).toContainText("Mot1one");
    // the replays are deleted, then scanned again: nobody is left to analyse
    for (const f of fs.readdirSync(folder)) fs.rmSync(path.join(folder, f));
    await scan(0);
    await expect(page.getByText(/^No osu!standard replays found there/)).toBeVisible();
    await expect(page.getByLabel("Player")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Analyse replays" })).toBeDisabled();
    await folders.fill(playsFolder()); // back to the sample plays for the tests after this one
    await scan(10);
  });
});

test("the setup guide: osu! folder, playstyle, replays, tour", async ({ page, request }) => {
  await request.patch("/api/settings", { data: { onboarded: false } });
  await page.setViewportSize({ width: 1440, height: 800 });
  await page.goto("/replays");
  const guide = page.getByRole("dialog", { name: "Set up osu! coach" });

  // 1 · osu! version, and its folder, which wasn't found automatically
  await expect(guide.getByRole("heading", { name: "Which osu! do you play?" })).toBeVisible();
  await guide.getByText("osu!stable", { exact: true }).click();
  await expect(guide.getByText(/osu!stable wasn't found automatically/)).toBeVisible();
  const folder = guide.getByLabel("osu!stable folder");
  await folder.fill(path.join(os.tmpdir(), "no-osu-here"));
  await guide.getByRole("button", { name: "Check folder" }).click();
  await expect(guide.getByText(/^No osu! found in/)).toBeVisible();
  const osu = stableInstall();
  await folder.fill(osu);
  await guide.getByRole("button", { name: "Check folder" }).click();
  await expect(guide.getByText(/^Found osu!stable/).first()).toBeVisible();
  expect(await guideProblems(page)).toEqual([]);
  await guide.getByRole("button", { name: "Continue", exact: true }).click();

  // 2 · playstyle and its settings
  await expect(guide.getByRole("heading", { name: "How do you play?" })).toBeVisible();
  await guide.getByText("Mouse", { exact: true }).click();
  await guide.getByText("Rapid trigger keyboard", { exact: true }).click();
  await expect(guide.getByRole("radio", { name: "Rapid trigger keyboard" })).toBeChecked();
  await guide.getByRole("spinbutton", { name: "Mouse DPI" }).fill("1600");
  await guide.getByRole("spinbutton", { name: "osu! sensitivity" }).fill("0.8");
  await guide.getByRole("spinbutton", { name: "Actuation point (mm)" }).fill("0.4");
  expect(await guideProblems(page)).toEqual([]);
  await guide.getByRole("button", { name: "Continue", exact: true }).click();
  await expect(guide.getByRole("heading", { name: "Find your replays" })).toBeVisible();
  expect(await (await request.get("/api/setup")).json()).toMatchObject({
    client: "stable",
    device: "mouse",
    keyboard: "rapid_trigger",
    mouse_dpi: 1600,
    ingame_sens: 0.8,
    actuation_mm: 0.4,
  });

  // 3 · the folder from step 1 is read, then analysed by itself
  await expect(guide.getByLabel(`osu!stable – ${osu}`)).toBeChecked();
  expect(await guideProblems(page)).toEqual([]);
  await guide.getByRole("button", { name: "Find and analyse my replays" }).click();
  await expect(guide.getByText(/^Analysed \d+ replays/)).toBeVisible({ timeout: 300_000 }); // of the player chosen last
  await guide.getByRole("button", { name: "Continue", exact: true }).click();

  // 4 · the tour
  await guide.getByRole("button", { name: "Show me around" }).click();
  for (const group of ["Replays", "Analysis"]) {
    await expect(guide.getByRole("heading", { name: group, exact: true })).toBeVisible();
    expect(await guideProblems(page)).toEqual([]);
    await guide.getByRole("button", { name: "Next", exact: true }).click();
  }
  await expect(guide.getByText("Goals & Training")).toBeVisible();
  await guide.getByRole("button", { name: "Finish the tour" }).click();

  // 5 · done: on to the Overview, and the guide stays closed
  await expect(guide.getByRole("heading", { name: "You're all set!" })).toBeVisible();
  await expect(guide.getByText("Mouse · 1,600 DPI, sensitivity 0.8")).toBeVisible();
  await guide.getByRole("button", { name: "Start using osu! coach" }).click();
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect((await (await request.get("/api/settings")).json()).onboarded).toBe(true);

  // what was entered is on Tips & Setup; the guide opens again from the toolbar
  await page.goto("/tips");
  await page.getByText("Your setup", { exact: true }).click();
  await expect(page.getByRole("spinbutton", { name: "Mouse DPI" })).toHaveValue("1600");
  await expect(page.getByRole("spinbutton", { name: "Actuation point (mm)" })).toHaveValue("0.4");
  await page.getByRole("button", { name: "Setup guide" }).click();
  await expect(page.getByRole("dialog", { name: "Setup guide" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});
