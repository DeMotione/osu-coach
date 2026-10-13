import { defineConfig, devices } from "@playwright/test";
import os from "node:os";
import path from "node:path";

/**
 * End-to-end tests: the built web app served by the real API (with an empty data folder of its own), driven like a
 * player would. Build first (`npm run build`); `OSU_COACH_PYTHON` = the Python with osu-coach and osu-coach-api
 * installed (default: `python`).
 */
const port = Number(process.env.E2E_PORT ?? 8766);
const python = process.env.OSU_COACH_PYTHON ?? "python";
const data = path.join(os.tmpdir(), `osu-coach-e2e-${process.pid}`);

export default defineConfig({
  testDir: "e2e",
  timeout: 180_000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL: `http://localhost:${port}`,
    trace: "retain-on-failure",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {},
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `"${python}" -m osu_coach --port ${port}`,
    url: `http://localhost:${port}/api/health`,
    reuseExistingServer: false,
    timeout: 60_000,
    env: {
      OSU_COACH_CACHE: path.join(data, "cache"),
      OSU_COACH_NO_AUTODETECT: "1",
      OSU_COACH_WEB_DIR: path.resolve("dist"),
      HOME: data,
      USERPROFILE: data,
    },
  },
});
