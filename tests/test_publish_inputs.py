from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def _module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "verify_publish_inputs.py"
    spec = importlib.util.spec_from_file_location("verify_publish_inputs", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ref(path: Path) -> dict:
    raw = path.read_bytes()
    return {"path": path.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def test_publish_verifier_binds_tag_build_manifest_and_bytes(tmp_path, monkeypatch):
    module = _module()
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / "testence-0.1.0.dev0-py3-none-any.whl"
    sdist = dist / "testence-0.1.0.dev0.tar.gz"
    wheel.write_bytes(b"wheel")
    sdist.write_bytes(b"sdist")
    observed = {
        path.name: {"bytes": path.stat().st_size, "sha256": module._sha(path)}
        for path in (wheel, sdist)
    }
    build = tmp_path / "build.json"
    build.write_text(
        json.dumps(
            {
                "schema": "testence/reproducible-build/1",
                "status": "passed",
                "matched": True,
                "dirty": False,
                "revision": "a" * 40,
                "artifacts": observed,
            }
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "candidate": {"rc_sha": "a" * 40, "tag": "v0.1.0.dev0", "version": "0.1.0.dev0"},
                "artifacts": [_ref(wheel), _ref(sdist)],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "_git", lambda *_args: "a" * 40)
    monkeypatch.setattr(
        module,
        "validate_release_manifest",
        lambda *_args, **_kwargs: {
            "status": "go",
            "ready_for_owner_decision": True,
            "payload_digest": "sha256:" + "b" * 64,
        },
    )

    result = module.verify_publish_inputs(tmp_path, dist, build, manifest, "a" * 40, "v0.1.0.dev0")

    assert result["status"] == "passed"

    wheel.write_bytes(b"changed")
    with pytest.raises(ValueError, match="differ from the reproducible build"):
        module.verify_publish_inputs(tmp_path, dist, build, manifest, "a" * 40, "v0.1.0.dev0")
