"""Render a local visual proof gallery without copying or modifying captured pixels."""

import argparse
import html
import json
import statistics
from pathlib import Path
from urllib.parse import quote


def render(root: Path) -> Path:
    receipt = json.loads((root / "result.json").read_text(encoding="utf-8"))
    records = receipt["records"]
    samples = [row["wall_ms"] for row in records]
    passed = sum(row["passed"] for row in records)
    judgments = [item for row in records for item in row.get("judgments", [])]
    parts = [
        "<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>",
        "<title>Testence — visual proof</title><style>body{font:16px system-ui;margin:40px;background:#f3f5f7;color:#132638}main{max-width:1500px;margin:auto}h1{font-size:36px}p{max-width:1000px;line-height:1.6}.stats{display:flex;gap:16px;flex-wrap:wrap}.stat,details{background:white;border:1px solid #ccd5df;padding:20px;border-radius:12px}.stat b{font-size:28px;display:block}.frames{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}img{width:100%;height:auto;border:1px solid #ccd5df}figure{margin:0}figcaption{padding:8px 0}details{margin:18px 0}summary{cursor:pointer;font-weight:600}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #ccd5df}a{color:#075bba}@media(max-width:700px){body{margin:16px}.frames{grid-template-columns:1fr}}</style><main>",
        "<p>TESTENCE / ENGINEERING EVIDENCE</p><h1>Visual regression, proved by controls</h1>",
        "<p>Installed-wheel simulation with Codex and Claude skill layouts. One scripted actor; independent customer or model acceptance is not claimed. Baselines are synthetic engineering candidates. Captured pixels are shown unchanged.</p>",
        f"<div class=stats><div class=stat><b>{passed}/{len(records)}</b>processes matched expectations</div><div class=stat><b>{statistics.median(samples) / 1000:.2f}s</b>median two-case replay</div><div class=stat><b>{len(judgments)}</b>pack judgments/submissions</div></div>"
        if samples
        else "<p>No completed replay samples.</p>",
        f"<p>Status: <strong>{html.escape(receipt['status'])}</strong>. <a href=result.json>Machine-readable receipt</a>. Replay excludes setup, baseline authoring and judgment.</p>",
        "<h2>Inspect the change</h2><p>One overview example per defect/profile from the Codex-layout project. Pink pixels in the diff exceed the frozen allowance. The complete image sets, dialog cases and second adapter are retained beside this report.</p>",
    ]
    for row in records:
        if row["client"] != "codex" or row["repeat"] != 1 or not row["expected_defect"]:
            continue
        run = root / f"codex-{row['profile']}" / "runs" / row.get("run_id", f"{row['phase']}-1")
        for pack in sorted(run.glob("*overview*/pack")):
            for comparison in sorted(pack.glob("visual-*.json")):
                visual = json.loads(comparison.read_text())
                parts.append(
                    f"<details open><summary>{html.escape(row['profile'] + ' / ' + row['phase'])} · {visual['changed_pixels']:,} changed pixels</summary><div class=frames>"
                )
                for key in ("expected", "actual", "diff"):
                    path = pack / visual["artifacts"][key]["path"]
                    href = quote(path.relative_to(root).as_posix())
                    parts.append(
                        f"<figure><figcaption>{key.capitalize()}</figcaption><a href='{href}'><img loading=lazy alt='{key} viewport' src='{href}'></a></figure>"
                    )
                parts.append("</div></details>")
    parts.append(
        "<h2>All fresh processes</h2><table><tr><th>Client layout</th><th>Viewport</th><th>Phase</th><th>Repeat</th><th>Replay ms</th><th>Expected outcome met</th></tr>"
    )
    for row in records:
        parts.append(
            "<tr>"
            + "".join(
                f"<td>{html.escape(str(row[key]))}</td>"
                for key in ("client", "profile", "phase", "repeat", "wall_ms", "passed")
            )
            + "</tr>"
        )
    parts.append("</table></main></html>")
    output = root / "report.html"
    output.write_text("\n".join(parts), encoding="utf-8")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(render(parser.parse_args().output.resolve()))
