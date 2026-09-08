from testence.evidence import EvidenceWriter
from testence.report import render_report


def test_report_is_self_contained(tmp_path):
    writer = EvidenceWriter(tmp_path, run_id="r-report", worker="")
    writer.emit("run.start", fingerprint={"os": "test", "python": "3.12"})
    writer.emit("test.start", test="login_works")
    writer.emit("step.start", test="login_works", step="s1", intent="open login page")
    writer.emit("step.end", test="login_works", step="s1", status="ok", duration_ms=42.0)
    writer.emit("test.end", test="login_works", status="pass", duration_ms=500.0)
    writer.emit("run.end", duration_ms=600.0, passed=1, failed=0)
    writer.close()

    out = render_report(writer.run_dir, tmp_path / "report.html")
    page = out.read_text(encoding="utf-8")
    assert "login_works" in page
    assert "open login page" in page
    assert "http://" not in page.split("<body>")[0].replace("http://www.w3.org", "")
    assert "prefers-color-scheme" in page
    assert out.stat().st_size < 5 * 1024 * 1024


def test_report_escapes_html(tmp_path):
    writer = EvidenceWriter(tmp_path, run_id="r-esc", worker="")
    writer.emit("run.start")
    writer.emit("test.start", test="<script>alert(1)</script>")
    writer.emit("test.end", test="<script>alert(1)</script>", status="pass", duration_ms=1.0)
    writer.emit("run.end", duration_ms=1.0, passed=1, failed=0)
    writer.close()
    page = render_report(writer.run_dir, tmp_path / "r.html").read_text(encoding="utf-8")
    body = page.split("<script>\nconst EVENTS")[0]
    assert "<script>alert(1)</script>" not in body


def test_oracle_diff_helper():
    from testence.oracle import diff_views

    assert diff_views({"cidr": "10.0.0.0/24"}, {"cidr": "10.0.0.0/24", "id": 5}) == []
    diffs = diff_views({"cidr": "10.0.0.0/24"}, {"cidr": "10.0.1.0/24"})
    assert diffs == [{"field": "cidr", "ui": "10.0.0.0/24", "api": "10.0.1.0/24"}]


def test_report_surfaces_the_plan_and_claims(tmp_path):
    writer = EvidenceWriter(tmp_path, run_id="r-trace", worker="")
    writer.bind_test(
        "create_blocker",
        plan={
            "schema": "testence/planspec/2",
            "project_id": "testence",
            "id": "release-board.create-blocker",
            "path": "specs/create-blocker.md",
        },
        claims=["blocker.create.persisted"],
    )
    writer.emit("run.start")
    writer.emit("test.start", test="create_blocker")
    writer.emit("test.end", test="create_blocker", status="pass", duration_ms=1.0)
    writer.emit("run.end", duration_ms=1.0, passed=1, failed=0)
    writer.close()

    page = render_report(writer.run_dir, tmp_path / "trace.html").read_text(encoding="utf-8")
    assert "Proof contract:" in page
    assert "release-board.create-blocker" in page
    assert "blocker.create.persisted" in page


def test_report_visibly_marks_a_torn_run_incomplete(tmp_path):
    writer = EvidenceWriter(tmp_path, run_id="r-torn-report", worker="")
    writer.emit("run.start")
    writer.emit("test.start", test="case_a")
    writer.close()

    page = render_report(writer.run_dir, tmp_path / "torn.html").read_text(encoding="utf-8")

    assert "INCOMPLETE RUN" in page
    assert "run_not_complete" in page
