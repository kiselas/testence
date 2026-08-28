// E1 (Node arm) — symmetric twin of ../e1_python.py. Same page, steps, counts.
import { chromium } from "playwright";
import { expect } from "@playwright/test";
import { pathToFileURL } from "node:url";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { writeFileSync, mkdirSync } from "node:fs";

const ITERATIONS = 30;
const here = dirname(fileURLToPath(import.meta.url));
const TARGET = pathToFileURL(join(here, "..", "target", "index.html")).href;

const pctl = (values, pct) => {
  const ordered = [...values].sort((a, b) => a - b);
  const k = ((ordered.length - 1) * pct) / 100;
  const lower = Math.floor(k);
  const upper = Math.min(lower + 1, ordered.length - 1);
  return Math.round((ordered[lower] + (ordered[upper] - ordered[lower]) * (k - lower)) * 100) / 100;
};

const samples = {};
const timed = async (label, fn) => {
  const start = process.hrtime.bigint();
  await fn();
  const ms = Number(process.hrtime.bigint() - start) / 1e6;
  (samples[label] ??= []).push(ms);
};

const t0 = process.hrtime.bigint();
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage();
const launchMs = Math.round(Number(process.hrtime.bigint() - t0) / 1e6 * 10) / 10;
await page.goto(TARGET);

for (let i = 1; i <= ITERATIONS; i++) {
  await timed("click_instant", () => page.click("#inc"));
  await timed("assert_instant", () => expect(page.locator("#count")).toHaveText(String(i)));
  await timed("fill_instant", () => page.fill("#name", `user-${i}`));
  await timed("click_add", () => page.click("#add"));
  await timed("assert_row",
    () => expect(page.locator("#list li").last()).toHaveText(`row-user-${i}`));
  await timed("click_async", () => page.click("#load"));
  await timed("assert_async",
    () => expect(page.locator("#asyncout")).toHaveText(`loaded-${i}`, { timeout: 5000 }));
}
await browser.close();

const instantLabels = ["click_instant", "assert_instant", "fill_instant", "click_add",
  "assert_row", "click_async"];
const instant = instantLabels.flatMap((l) => samples[l]);
const result = {
  arm: "node",
  node: process.version,
  iterations: ITERATIONS,
  launch_ms: launchMs,
  per_step: Object.fromEntries(Object.entries(samples).map(([label, vals]) =>
    [label, { p50: pctl(vals, 50), p95: pctl(vals, 95), n: vals.length }])),
  instant_all: { p50: pctl(instant, 50), p95: pctl(instant, 95), n: instant.length },
};
mkdirSync(join(here, "..", "results"), { recursive: true });
writeFileSync(join(here, "..", "results", "e1_node.json"), JSON.stringify(result, null, 1));
console.log(JSON.stringify(result, null, 1));
