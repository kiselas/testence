import json

import pytest

from testence.dsl.steps import Actions, StepFailed
from testence.evidence import EvidenceWriter
from testence.visual import VisualUnavailable, capture_baseline, compare_baseline, digest

Image = pytest.importorskip("PIL.Image")


class PixelEngine:
    capture_screenshots = True

    def __init__(self):
        self.image = Image.new("RGB", (40, 30), "white")
        self.profile = {"width": 40, "height": 30, "dpr": 1}
        self.unstable = False
        self.captures = 0

    def eval_js(self, _expression):
        return self.profile

    def screenshot(self, path):
        self.captures += 1
        image = self.image.copy()
        if self.unstable:
            image.putpixel((0, 0), (self.captures % 256, 0, 0))
        image.save(path)


def test_visual_detects_local_defect_and_restoration_without_changing_baseline(tmp_path):
    engine = PixelEngine()
    baseline = tmp_path / "baseline"
    pinned = capture_baseline(engine, baseline, provenance="synthetic healthy fixture")
    assert (
        compare_baseline(engine, baseline, tmp_path / "green", baseline_digest=pinned)["outcome"]
        == "passed"
    )
    engine.image.putpixel((12, 9), (0, 0, 0))
    result = compare_baseline(engine, baseline, tmp_path / "red", baseline_digest=pinned)
    assert result["outcome"] == "failed"
    assert result["changed_pixels"] == 1
    assert result["changed_bbox"] == (12, 9, 13, 10)
    for artifact in result["artifacts"].values():
        assert digest(tmp_path / "red" / artifact["path"]) == artifact["digest"]
    engine.image.putpixel((12, 9), (255, 255, 255))
    assert (
        compare_baseline(engine, baseline, tmp_path / "restore", baseline_digest=pinned)["outcome"]
        == "passed"
    )
    assert digest(baseline / "baseline.json") == pinned
    with pytest.raises(FileExistsError):
        capture_baseline(engine, baseline, provenance="must not overwrite")


@pytest.mark.parametrize(
    "fault", ["profile", "image", "manifest", "unstable", "consent", "missing"]
)
def test_unusable_visual_evidence_is_inconclusive_in_ledger(tmp_path, fault):
    engine = PixelEngine()
    baseline = tmp_path / "baseline"
    pinned = capture_baseline(engine, baseline, provenance="unit control")
    if fault == "profile":
        engine.profile["dpr"] = 2
    elif fault == "image":
        Image.new("RGB", (40, 30), "black").save(baseline / "baseline.png")
    elif fault == "manifest":
        (baseline / "baseline.json").write_text("{}", encoding="utf-8")
    elif fault == "unstable":
        engine.unstable = True
    elif fault == "consent":
        engine.capture_screenshots = False
    elif fault == "missing":
        (baseline / "baseline.png").unlink()
    with EvidenceWriter(tmp_path / "runs") as writer:
        ex = Actions(engine, writer, "visual")
        with pytest.raises(StepFailed):
            ex.expect_screenshot(
                str(baseline), baseline_digest=pinned, assertion_id="a.visual", claim_id="visual"
            )
        rows = [json.loads(line) for line in writer.path.read_text().splitlines()]
    assertions = [row for row in rows if row["kind"] == "assertion"]
    assert len(assertions) == 1
    assert assertions[0]["outcome"] == "inconclusive"


def test_tolerance_is_frozen_in_manifest_and_does_not_hide_larger_difference(tmp_path):
    engine = PixelEngine()
    pinned = capture_baseline(
        engine, tmp_path / "b", provenance="small channel noise", channel_tolerance=2
    )
    engine.image.putpixel((0, 0), (253, 255, 255))
    assert (
        compare_baseline(engine, tmp_path / "b", tmp_path / "out", baseline_digest=pinned)[
            "outcome"
        ]
        == "passed"
    )
    engine.image.putpixel((0, 0), (252, 255, 255))
    assert (
        compare_baseline(engine, tmp_path / "b", tmp_path / "out", baseline_digest=pinned)[
            "outcome"
        ]
        == "failed"
    )


def test_unstable_baseline_is_not_accepted(tmp_path):
    engine = PixelEngine()
    engine.unstable = True
    with pytest.raises(VisualUnavailable, match="unstable"):
        capture_baseline(engine, tmp_path / "b", provenance="unstable control")
    assert not (tmp_path / "b" / "baseline.json").exists()


def test_visual_capability_rejected_before_capture(tmp_path):
    from testence.engine import UnsupportedCapability

    engine = PixelEngine()
    engine.capabilities = lambda: frozenset({"browser.dom"})
    with pytest.raises(UnsupportedCapability, match="visual.screenshot"):
        capture_baseline(engine, tmp_path / "b", provenance="unsupported engine")
    assert engine.captures == 0
    assert not (tmp_path / "b").exists()


def test_live_viewport_survives_session_reset_and_detects_css_only_defect(tmp_path):
    from testence.config import Settings
    from testence.engine import create_engine

    engine = create_engine(
        Settings(
            headed=False,
            debug_port=0,
            extra={
                "viewport": {"width": 390, "height": 844},
                "capture_policy": {"screenshots": True},
            },
        )
    )
    try:
        engine.start()
        page = "data:text/html,<style>body{background:white}button{background:blue;color:white}</style><button>Save</button>"
        engine.goto(page)
        baseline = tmp_path / "baseline"
        pinned = capture_baseline(engine, baseline, provenance="live CSS control")
        assert engine.eval_js("() => innerWidth") == 390
        engine.reset_session()
        engine.goto(page)
        assert engine.eval_js("() => innerWidth") == 390
        assert (
            compare_baseline(engine, baseline, tmp_path / "green", baseline_digest=pinned)[
                "outcome"
            ]
            == "passed"
        )
        # Explicit test-only defect injection, no user interaction replaced by JS.
        engine.eval_js("() => {document.querySelector('button').style.color='transparent'}")
        with EvidenceWriter(tmp_path / "runs") as writer:
            ex = Actions(engine, writer, "live")
            with pytest.raises(StepFailed, match="visual mismatch"):
                ex.expect_screenshot(
                    str(baseline),
                    baseline_digest=pinned,
                    assertion_id="a.visual",
                    claim_id="visual",
                )
            rows = [json.loads(line) for line in writer.path.read_text().splitlines()]
            assert next(row for row in rows if row["kind"] == "assertion")["outcome"] == "failed"
    finally:
        engine.stop()


@pytest.mark.parametrize(
    "viewport",
    [{"width": 0, "height": 800}, {"width": True, "height": 800}, {"width": 900}, [390, 844]],
)
def test_viewport_rejects_invalid_profiles(viewport):
    from testence.config import Settings
    from testence.engine import create_engine

    with pytest.raises(ValueError, match="viewport"):
        create_engine(Settings(extra={"viewport": viewport}))
