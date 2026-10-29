import { expect, test, type APIRequestContext } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

async function finished(request: APIRequestContext, id: string) {
  await expect.poll(async () => (await (await request.get(`/api/jobs/${id}`)).json()).status).not.toBe("running");
  const job = await (await request.get(`/api/jobs/${id}`)).json();
  expect(job.status, job.error).toBe("succeeded");
}

test.beforeEach(async ({ request }) => {
  await request.patch("/api/settings", { data: { onboarded: true } });
});

test("farming and HD/DT goals show concrete plays and fit small windows", async ({ page }) => {
  await page.goto("/play-goals?tab=farm");
  await expect(page.getByRole("heading", { level: 1, name: "Play Goals" })).toBeVisible();
  await page.getByRole("button", { name: "Find maps" }).click();
  const next = page.locator(".card").filter({ has: page.getByRole("heading", { name: /^Maps to / }) });
  await expect(next.locator("tbody tr").first()).toBeVisible();
  await expect(next.getByRole("columnheader", { name: "PP at target" })).toBeVisible();
  await expect(next.getByRole("columnheader", { name: "Target", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Get these maps into osu!" })).toBeVisible();
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
    expect(await page.locator(".card").evaluateAll((cards) => cards.some((card) => card.scrollWidth > card.clientWidth + 1))).toBe(false);
  }
  await page.getByRole("tab", { name: "Improve a mod" }).click();
  await page.getByRole("button", { name: "Find training maps" }).click();
  await expect(next.locator("tbody tr").first()).toContainText("+HD");
  const training = page.getByRole("group", { name: "Training mods" });
  await training.getByRole("button", { name: "DT", exact: true }).click();
  await training.getByRole("button", { name: "HD", exact: true }).click();
  await page.getByRole("button", { name: "Find training maps" }).click();
  await expect(next.locator("tbody tr").first()).toContainText("+DT");
  await expect(next.locator("tbody tr").first()).not.toContainText("+HD");
  await expect(training.getByRole("button", { name: "EZ", exact: true })).toBeDisabled();
  await training.getByRole("button", { name: "HR", exact: true }).click();
  await training.getByRole("button", { name: "DT", exact: true }).click();
  await page.getByRole("button", { name: "Find training maps" }).click();
  await expect(next.locator("tbody tr").first()).toContainText("+HR");
});

test("a chosen replay gets an FC diagnosis and keeps a deep link to its details", async ({ page, request }) => {
  const resources = path.resolve("..", "backend", "tests", "resources");
  const index = JSON.parse(fs.readFileSync(path.join(resources, "index.json"), "utf8")) as { replay: string; md5: string }[];
  const fixture = index.find((r) => r.replay === "mot1one__lazer_nm.osr")!;
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), "osu-coach-goal-test-"));
  try {
    fs.copyFileSync(path.join(resources, "replays", fixture.replay), path.join(folder, fixture.replay));
    fs.copyFileSync(path.join(resources, "maps", `${fixture.md5}.osu`), path.join(folder, "target.osu"));
    const scan = await request.post("/api/library/scan", { data: { mode: "library", folders: [folder], installs: [] } });
    await finished(request, (await scan.json()).id);
    const analysis = await request.post("/api/analysis", { data: { player: "Mot1one", online: false } });
    await finished(request, (await analysis.json()).id);
    await page.goto(`/play-goals?tab=fc&path=${encodeURIComponent(path.join(folder, fixture.replay))}&client=lazer`);
    await page.getByRole("button", { name: "Assess my FC goal" }).click();
    await expect(page.getByRole("heading", { name: "What to work on for this map" })).toBeVisible();
    await expect(page.getByText("Observed").first()).toBeVisible();
    await expect(page.getByText("Practise around:").first()).toBeVisible();
    await page.getByRole("link", { name: "Open detailed map analysis" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Detailed Map Analysis" })).toBeVisible();
    await expect(page.getByRole("link", { name: "I want to FC this map" })).toBeVisible();
  } finally {
    fs.rmSync(folder, { recursive: true, force: true });
  }
});

test("a map URL without a chosen difficulty is an actionable error", async ({ page }) => {
  await page.goto("/play-goals?tab=fc&beatmap=https%3A%2F%2Fosu.ppy.sh%2Fbeatmapsets%2F123");
  await page.getByRole("button", { name: "Assess my FC goal" }).click();
  await expect(page.getByText("Choose a specific osu!standard difficulty, not just a beatmapset.")).toBeVisible();
});
