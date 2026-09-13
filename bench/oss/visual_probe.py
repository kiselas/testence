"""Supplemental pixel probes on pinned OSS builds; not PlanSpec/client acceptance.

Use an installed visual wheel Python with -I. No upstream checkout is modified.
"""

import argparse
import functools
import hashlib
import http.server
import json
import subprocess
import threading
import time
from pathlib import Path

from testence.config import Settings
from testence.distribution import verify_installed_wheel
from testence.engine import create_engine
from testence.visual import capture_baseline, compare_baseline, digest

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--distribution", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    targets = json.loads((ROOT / "bench/oss/targets.json").read_text())["targets"]
    receipt = {
        "scope": "Supplemental OSS pixel probes; not bound pytest/client acceptance",
        "records": [],
        "status": "incomplete",
        "distribution": verify_installed_wheel(args.distribution.resolve()),
        "targets": [],
    }
    mode = {"phase": "healthy"}

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            path = Path(self.translate_path(self.path))
            if path.suffix != ".html" or not path.is_file():
                return super().do_GET()
            body = path.read_text(encoding="utf-8")
            if mode["phase"] == "shift":
                body = body.replace(
                    "</head>", "<style>.card{transform:translateX(24px)!important}</style></head>"
                )
            elif mode["phase"] == "dom-only":
                body = body.replace("<body", '<body data-probe="refactored"', 1)
            raw = body.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    def save():
        (output / "result.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    try:
        for target in targets:
            checkout = ROOT / target["checkout"]
            if (
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=checkout, text=True
                ).strip()
                != target["revision"]
            ):
                raise ValueError("target revision mismatch")
            if subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=checkout, text=True
            ).strip():
                raise ValueError("upstream checkout changed")
            tree_hash = hashlib.sha256()
            web_root = checkout / target["web_root"]
            for asset in sorted(web_root.rglob("*")):
                if asset.is_file():
                    tree_hash.update(asset.relative_to(web_root).as_posix().encode() + b"\0")
                    tree_hash.update(hashlib.sha256(asset.read_bytes()).digest())
            receipt["targets"].append({**target, "build_sha256": tree_hash.hexdigest()})
            handler = functools.partial(Handler, directory=str(checkout / target["web_root"]))
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                for profile, width, height in (("desktop", 1280, 900), ("mobile", 390, 844)):
                    baseline = output / f"{target['name']}-{profile}-baseline"
                    pinned = None
                    for phase in ("baseline", "healthy", "shift", "dom-only", "restored"):
                        mode["phase"] = phase
                        page = (
                            "/forms/elements.html"
                            if target["name"] == "adminlte"
                            else "/sign-in.html"
                        )
                        settings = Settings(
                            base_url=f"http://127.0.0.1:{server.server_port}",
                            headed=False,
                            debug_port=0,
                            timeout_ms=10000,
                            extra={
                                "capture_policy": {"screenshots": True},
                                "viewport": {"width": width, "height": height},
                            },
                        )
                        engine = create_engine(settings)
                        started = time.perf_counter()
                        try:
                            engine.start()
                            engine.goto(page)
                            engine.eval_js("() => document.fonts.ready.then(() => true)")
                            if not engine.wait_for_predicate_js(
                                "() => !!document.querySelector('.card') && [...document.images].every(image => image.complete)",
                                timeout_ms=10000,
                            ):
                                raise RuntimeError("OSS page readiness not established")
                            if phase == "baseline":
                                pinned = capture_baseline(
                                    engine,
                                    baseline,
                                    provenance=f"{target['repository']} @ {target['revision']}; local candidate",
                                )
                                continue
                            result = compare_baseline(
                                engine,
                                baseline,
                                output / f"{target['name']}-{profile}-{phase}",
                                baseline_digest=pinned,
                            )
                            receipt["records"].append(
                                {
                                    "target": target["name"],
                                    "revision": target["revision"],
                                    "license_digest": digest(checkout / target["license"]),
                                    "profile": profile,
                                    "phase": phase,
                                    "wall_ms": round((time.perf_counter() - started) * 1000, 1),
                                    "passed": result["outcome"]
                                    == ("failed" if phase == "shift" else "passed"),
                                    "comparison": result,
                                }
                            )
                            save()
                            print(
                                f"{target['name']}/{profile}/{phase}: {result['outcome']}",
                                flush=True,
                            )
                            if not receipt["records"][-1]["passed"]:
                                raise RuntimeError(
                                    "unexpected visual probe outcome; attempt retained"
                                )
                        finally:
                            engine.stop()
            finally:
                server.shutdown()
                server.server_close()
        if (
            not targets
            or len(receipt["records"]) != len(targets) * 8
            or not all(row["passed"] for row in receipt["records"])
        ):
            raise RuntimeError("incomplete OSS visual probe matrix")
        receipt["status"] = "passed"
    except Exception as exc:
        receipt["status"] = "failed"
        receipt["error"] = str(exc)
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
