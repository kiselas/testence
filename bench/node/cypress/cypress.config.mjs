import { defineConfig } from "cypress";

// Same policy as the other arms: one spec, no retries, no video or screenshots.
export default defineConfig({
  e2e: {
    baseUrl: process.env.BENCH_BASE_URL,
    specPattern: "cypress/flow.cy.mjs",
    supportFile: false,
    video: false,
    screenshotOnRunFailure: false,
    retries: 0,
    allowCypressEnv: false,
    defaultCommandTimeout: 10000,
  },
  screenshotsFolder: process.env.BENCH_ARTIFACT_DIR || "cypress-artifacts",
  downloadsFolder: process.env.BENCH_ARTIFACT_DIR || "cypress-artifacts",
});
