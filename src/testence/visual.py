"""Opt-in, baseline-bound viewport comparison. No baseline updates during replay."""

from __future__ import annotations

import hashlib
import json
import platform
import uuid
from pathlib import Path
from typing import Any

from testence.engine import Capability, Engine, require_capabilities

MAX_BYTES = 16 * 1024 * 1024
MAX_PIXELS = 8_000_000
PROFILE_JS = """() => ({width: innerWidth, height: innerHeight,
    dpr: devicePixelRatio, userAgent: navigator.userAgent, language: navigator.language,
    dark: matchMedia('(prefers-color-scheme: dark)').matches,
    reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches})"""


class VisualUnavailable(RuntimeError):
    """Missing, incompatible or unstable evidence cannot violate a product claim."""


def _pillow() -> Any:
    try:
        from PIL import Image
    except ImportError as exc:
        raise VisualUnavailable("install testence[visual] to compare screenshots") from exc
    return Image


def _bytes(path: Path) -> bytes:
    if path.is_symlink() or path.stat().st_size > MAX_BYTES:
        raise VisualUnavailable("visual artifact is a symlink or exceeds 16 MiB")
    return path.read_bytes()


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(_bytes(path)).hexdigest()


def _image(path: Path) -> Any:
    import io

    image = _pillow().open(io.BytesIO(_bytes(path)))
    if image.format != "PNG" or image.width * image.height > MAX_PIXELS:
        raise VisualUnavailable("visual evidence must be PNG, at most 8 million pixels")
    # Preserve alpha: a transparency change is a pixel change too.
    return image.convert("RGBA")


def _profile(engine: Engine) -> dict[str, Any]:
    require_capabilities(engine, "visual comparison", Capability.VISUAL, Capability.JAVASCRIPT)
    if not getattr(engine, "capture_screenshots", False):
        raise VisualUnavailable("capture_policy.screenshots must be enabled explicitly")
    result = engine.eval_js(PROFILE_JS)
    if not isinstance(result, dict) or not result.get("width") or not result.get("height"):
        raise VisualUnavailable("browser visual profile unavailable")
    profile = {**result, "os": platform.system()}
    # Masked regions are part of what a baseline shows. Recording them makes a mask
    # change an incompatible profile instead of a pixel verdict; an unmasked profile
    # keeps its earlier shape, so existing baselines stay valid (ADR-0024).
    masks = getattr(engine, "screenshot_masks", ())
    if masks:
        profile["screenshot_masks"] = [target.describe() for target in masks]
    return profile


def _stable_capture(engine: Engine, first: Path, second: Path) -> None:
    # Two observations, never an interaction retry or a loop until green.
    engine.screenshot(str(first))
    engine.screenshot(str(second))
    a, b = _image(first), _image(second)
    if a.size != b.size or a.tobytes() != b.tobytes():
        raise VisualUnavailable("two consecutive viewport captures are unstable")


def capture_baseline(
    engine: Engine,
    directory: Path,
    *,
    provenance: str,
    channel_tolerance: int = 0,
    max_changed_pixels: int = 0,
) -> str:
    """Create a NEW candidate baseline; return its manifest digest for review/pinning.

    Call only in a separate authoring phase on a known healthy target. Existing
    directories are never replaced, including incomplete earlier captures.
    """
    if not provenance.strip():
        raise ValueError("baseline provenance is required")
    _limits(channel_tolerance, max_changed_pixels)
    profile = _profile(engine)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    _stable_capture(engine, directory / "baseline.png", directory / "stability.png")
    if _profile(engine) != profile:
        raise VisualUnavailable("visual profile changed during baseline capture")
    document = {
        "schema": "testence/visual-baseline/1",
        "profile": profile,
        "provenance": provenance,
        "image_digest": digest(directory / "baseline.png"),
        "channel_tolerance": channel_tolerance,
        "max_changed_pixels": max_changed_pixels,
    }
    manifest = directory / "baseline.json"
    manifest.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return digest(manifest)


def _limits(channel: Any, pixels: Any) -> None:
    if type(channel) is not int or not 0 <= channel < 255:
        raise ValueError("channel_tolerance must be an integer in 0..254")
    if type(pixels) is not int or not 0 <= pixels < MAX_PIXELS:
        raise ValueError("max_changed_pixels must be an integer below 8 million")


def compare_baseline(
    engine: Engine, baseline: Path, output: Path, *, baseline_digest: str
) -> dict[str, Any]:
    """Compare once and retain immutable expected/actual/diff files and their hashes.

    Raises for unavailable evidence; a completed comparison returns passed/failed.
    No masks, image resizing, automatic threshold tuning or baseline replacement.
    """
    _pillow()
    from PIL import ImageChops

    profile = _profile(engine)
    baseline, output = Path(baseline), Path(output)
    manifest = baseline / "baseline.json"
    manifest_bytes = _bytes(manifest)
    if "sha256:" + hashlib.sha256(manifest_bytes).hexdigest() != baseline_digest:
        raise VisualUnavailable("baseline manifest digest mismatch")
    document = json.loads(manifest_bytes)
    if document.get("schema") != "testence/visual-baseline/1":
        raise VisualUnavailable("unsupported visual baseline schema")
    if document.get("profile") != profile:
        raise VisualUnavailable("visual profile mismatch; use a reviewed baseline for this profile")
    baseline_bytes = _bytes(baseline / "baseline.png")
    if "sha256:" + hashlib.sha256(baseline_bytes).hexdigest() != document.get("image_digest"):
        raise VisualUnavailable("baseline image digest mismatch")
    _limits(document.get("channel_tolerance"), document.get("max_changed_pixels"))
    output.mkdir(parents=True, exist_ok=True)
    prefix = "visual-" + uuid.uuid4().hex
    paths = {
        name: output / f"{prefix}-{name}.png"
        for name in ("expected", "actual", "stability", "diff")
    }
    paths["expected"].write_bytes(baseline_bytes)
    _stable_capture(engine, paths["actual"], paths["stability"])
    if _profile(engine) != profile:
        raise VisualUnavailable("visual profile changed during comparison capture")
    expected, actual = _image(paths["expected"]), _image(paths["actual"])
    if expected.size != actual.size:
        raise VisualUnavailable("screenshot dimensions differ within the same declared profile")
    if document["max_changed_pixels"] >= expected.width * expected.height:
        raise VisualUnavailable("pixel allowance would ignore the entire viewport")
    channels = ImageChops.difference(expected, actual).split()
    maximum = channels[0]
    for channel in channels[1:]:
        maximum = ImageChops.lighter(maximum, channel)
    tolerance = document["channel_tolerance"]
    mask = maximum.point([255 if value > tolerance else 0 for value in range(256)])
    changed = mask.histogram()[255]
    overlay = actual.convert("RGB")
    overlay.paste((255, 0, 80), mask=mask)
    overlay.save(paths["diff"])
    result = {
        "schema": "testence/visual-comparison/1",
        "outcome": "passed" if changed <= document["max_changed_pixels"] else "failed",
        "baseline_digest": baseline_digest,
        "profile": profile,
        "channel_tolerance": tolerance,
        "max_changed_pixels": document["max_changed_pixels"],
        "changed_pixels": changed,
        "total_pixels": expected.width * expected.height,
        "changed_bbox": mask.getbbox(),
        "artifacts": {
            name: {"path": path.name, "digest": digest(path)} for name, path in paths.items()
        },
    }
    (output / f"{prefix}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
