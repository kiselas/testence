import { defineConfig } from "@playwright/test";


export default defineConfig({
  testDir: ".",
  testMatch: "playwright_flow.spec.mjs",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "line",
  outputDir: process.env.BENCH_ARTIFACT_DIR,
  use: {
    baseURL: process.env.BENCH_BASE_URL,
    browserName: "chromium",
    channel: process.env.BENCH_CHANNEL || "chromium",
    headless: true,
    trace: "off",
    screenshot: "off",
    video: "off",
  },
});
