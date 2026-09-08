"""Self-contained single-file HTML report rendered from run.jsonl (ADR-0005).

Constraints: opens from file:// offline, no external
assets, click depth verdict→raw evidence ≤ 3, ≤ 5 MB for a 20-case run, renders in
both light and dark themes. The report is a *view* over the same ledger agents read —
never a second source of truth.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from testence.metrics import load_run

_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Testence run __RUN_ID__</title>
<style>
:root {
  --bg:#f7f7f8; --fg:#1c1c1f; --muted:#6b6b74; --card:#ffffff; --line:#e3e3e8;
  --ok:#1a7f37; --ok-bg:#e6f4ea; --fail:#c62828; --fail-bg:#fdecea; --accent:#4053b8;
}
@media (prefers-color-scheme: dark) {
  :root { --bg:#131316; --fg:#e8e8ec; --muted:#9a9aa5; --card:#1d1d22; --line:#2c2c33;
          --ok:#4caf7d; --ok-bg:#12281b; --fail:#ef6e6e; --fail-bg:#2d1516; --accent:#8fa0ff; }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
       font:14px/1.5 system-ui, "Segoe UI", sans-serif; }
main { max-width:960px; margin:0 auto; padding:24px 16px 64px; }
h1 { font-size:20px; margin:0 0 4px; }
.sub { color:var(--muted); margin-bottom:20px; }
.integrity { color:var(--fail); background:var(--fail-bg); border:1px solid var(--fail);
             border-radius:10px; padding:10px 14px; margin-bottom:18px; }
.summary { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:24px; }
.stat { background:var(--card); border:1px solid var(--line); border-radius:10px;
        padding:10px 16px; min-width:110px; }
.stat b { display:block; font-size:20px; }
.stat span { color:var(--muted); font-size:12px; }
details.test { background:var(--card); border:1px solid var(--line); border-radius:10px;
               margin-bottom:10px; overflow:hidden; }
details.test > summary { list-style:none; cursor:pointer; display:flex; gap:10px;
                         align-items:center; padding:12px 16px; }
details.test > summary::-webkit-details-marker { display:none; }
.chip { border-radius:20px; padding:2px 10px; font-size:12px; font-weight:600; }
.chip.pass { color:var(--ok); background:var(--ok-bg); }
.chip.fail { color:var(--fail); background:var(--fail-bg); }
.chip.skip { color:var(--muted); background:var(--line); }
.tname { font-weight:600; flex:1; overflow-wrap:anywhere; }
.tdur { color:var(--muted); font-variant-numeric:tabular-nums; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th, td { text-align:left; padding:6px 16px; border-top:1px solid var(--line);
         vertical-align:top; }
th { color:var(--muted); font-weight:500; }
td.ms { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
tr.fail td { background:var(--fail-bg); }
.pack { margin:0 16px 14px; padding:12px 14px; border:1px dashed var(--fail);
        border-radius:8px; font-size:13px; }
.pack code { background:var(--bg); padding:1px 5px; border-radius:4px; }
.pack .err { white-space:pre-wrap; overflow-wrap:anywhere; color:var(--fail);
             max-height:180px; overflow:auto; margin-top:8px; }
.trace { margin:0; padding:10px 16px; border-top:1px solid var(--line);
         background:var(--bg); font-size:13px; }
.trace code { color:var(--accent); }
.trace .claim { display:inline-block; margin:3px 4px 0 0; padding:1px 7px;
                border:1px solid var(--line); border-radius:12px; background:var(--card); }
.overflow { overflow-x:auto; }
.heal { margin:0 16px 14px; padding:12px 14px; border:1px solid var(--accent);
        border-left-width:4px; border-radius:8px; font-size:13px; }
.heal .why { color:var(--muted); margin:6px 0; }
.heal pre { background:var(--bg); padding:8px 10px; border-radius:6px; margin:8px 0 0;
            overflow-x:auto; font-size:12px; }
.heal .add { color:var(--ok); }
.heal .del { color:var(--fail); }
.verdict { font-weight:600; }
.oracle-diff { font-family:ui-monospace, monospace; font-size:12px; }
footer { color:var(--muted); font-size:12px; margin-top:32px; }
</style>
</head>
<body>
<main>
  <h1>Testence run <code>__RUN_ID__</code></h1>
  <div class="sub" id="fingerprint"></div>
  <div class="integrity" id="integrity" hidden></div>
  <div class="summary" id="summary"></div>
  <div id="tests"></div>
  <footer>schema testence/2 · report is a view over run.jsonl — agents read the ledger,
  humans read this page</footer>
</main>
<script>
const EVENTS = __EVENTS__;
const esc = s => String(s ?? "").replace(/[&<>"]/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const byTest = new Map();
let runStart = null, runEnd = null;
for (const e of EVENTS) {
  if (e.kind === "run.start") runStart = e;
  else if (e.kind === "run.end") runEnd = e;
  else if (e.test) {
    const identity = [e.project_id, e.case_id, e.variant_id, e.attempt_id];
    const key = identity.every(Boolean) ? identity.join("|") : e.test;
    if (!byTest.has(key)) byTest.set(key, []);
    byTest.get(key).push(e);
  }
}
const fp = runStart?.fingerprint || {};
document.getElementById("fingerprint").textContent =
  `${runStart?.ts ?? ""} · ${fp.os ?? ""} · python ${fp.python ?? ""}` +
  (fp.base_url ? ` · ${fp.base_url}` : "");
if (runEnd?.run_status === "incomplete") {
  const issues = (runEnd.integrity_errors || []).map(item =>
    `${item.code}: ${item.error}${item.path ? ` (${item.path})` : ""}`
  );
  const warning = document.getElementById("integrity");
  warning.hidden = false;
  warning.textContent = `INCOMPLETE RUN${issues.length ? " · " + issues.join(" · ") : ""}`;
}
const stats = [
  ["tests", byTest.size],
  ["passed", runEnd?.passed ?? "—"],
  ["failed", runEnd?.failed ?? "—"],
  ["broken", runEnd?.broken ?? 0],
  ["skipped", runEnd?.skipped ?? 0],
  ["aborted", runEnd?.aborted ?? 0],
  ["duration", runEnd ? (runEnd.duration_ms / 1000).toFixed(1) + " s" : "—"],
];
document.getElementById("summary").innerHTML = stats.map(([label, value]) =>
  `<div class="stat"><b>${esc(value)}</b><span>${esc(label)}</span></div>`).join("");
const container = document.getElementById("tests");
for (const [name, events] of byTest) {
  const end = events.find(e => e.kind === "test.end");
  const status = end?.status === "pass" ? "passed" : (end?.status ?? "not_run");
  const assurance = end?.assurance ?? "unverified";
  const failed = ["fail", "failed", "broken", "aborted"].includes(status);
  const chip = failed ? "fail" : (status === "passed" ? "pass" : "skip");
  const steps = events.filter(e => e.kind === "step.end");
  const starts = new Map(events.filter(e => e.kind === "step.start")
                               .map(e => [e.step, e]));
  const pack = events.find(e => e.kind === "pack");
  const contract = events.find(e => e.plan?.id);
  const oracle = events.filter(e => e.kind === "oracle");
  const rows = steps.map(s => {
    const st = starts.get(s.step) || {};
    return `<tr class="${s.status === "fail" ? "fail" : ""}">
      <td>${esc(st.intent)}</td><td>${esc(st.target ?? "")}</td>
      <td>${esc(s.status)}${s.error ? " — " + esc(s.error) : ""}</td>
      <td class="ms">${s.duration_ms} ms</td></tr>`;
  }).join("");
  const oracleRows = oracle.map(o => {
    const detail = o.ok
      ? "UI and API agree"
      : (o.diff || []).map(d =>
          `${esc(d.field)}: UI ${esc(JSON.stringify(d.ui))} vs API ${esc(JSON.stringify(d.api))}`
        ).join("<br>");
    return `<tr class="${o.ok ? "" : "fail"}">
      <td>oracle: ${esc(o.name)}</td><td></td>
      <td class="oracle-diff">${detail}</td><td></td></tr>`;
  }).join("");
  const packHtml = pack ? `<div class="pack">
      <b>Evidence pack:</b> <code>${esc(pack.dir)}</code> ·
      ${Object.entries(pack.sections_est_tokens || {})
        .map(([k, v]) => `${esc(k)} ~${v} tok`).join(" · ")}
      <div class="err">${esc(pack.error)}</div></div>` : "";
  const traceHtml = contract ? `<div class="trace">
      <b>Proof contract:</b> <code>${esc(contract.plan.id)}</code>
      ${contract.plan.path ? ` · ${esc(contract.plan.path)}` : ""}<br>
      ${(contract.claims || []).map(claim =>
        `<span class="claim">${esc(claim)}</span>`).join("")}
    </div>` : "";
  // A heal proposal is the actionable half of a failure: show the verdict reading,
  // why it was reached, and the exact edit a reviewer is being asked to accept.
  const proposal = pack && pack.heal_hint ? pack : null;
  const healHtml = proposal ? `<div class="heal">
      <span class="verdict">framework reading: ${esc(proposal.heal_hint.verdict_hint)}</span>
      (similarity ${esc(proposal.heal_hint.score)})
      <div class="why">${esc(proposal.heal_rationale || "see heal.json in the pack")}</div>
      ${proposal.heal_edit ? `<pre>${esc(proposal.heal_edit)}</pre>` : ""}
    </div>` : "";
  container.insertAdjacentHTML("beforeend", `
    <details class="test" ${failed ? "open" : ""}>
      <summary><span class="chip ${chip}">${esc(status.toUpperCase())}</span>
        <span class="chip ${assurance === "verified" ? "pass" : (assurance === "violated" ? "fail" : "skip")}">
          ${esc(assurance.toUpperCase())}</span>
        <span class="tname">${esc(end?.nodeid ?? events[0]?.nodeid ?? name)}</span>
        <span class="tdur">${end ? (end.duration_ms / 1000).toFixed(1) + " s" : ""}</span>
      </summary>
      ${traceHtml}
      <div class="overflow"><table>
        <tr><th>intent</th><th>target</th><th>status</th><th>ms</th></tr>
        ${rows}${oracleRows}
      </table></div>
      ${packHtml}
      ${healHtml}
    </details>`);
}
</script>
</body>
</html>
"""


def render_report(run_dir: Path, out: Path) -> Path:
    events = load_run(run_dir)
    run_id = str(next((e.get("run_id") or e.get("run") for e in events), run_dir.name))
    page = _TEMPLATE.replace("__RUN_ID__", html.escape(run_id)).replace(
        "__EVENTS__", json.dumps(events, ensure_ascii=False)
    )
    out.write_text(page, encoding="utf-8", newline="\n")
    return out
