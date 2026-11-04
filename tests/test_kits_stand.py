"""The committed stand build matches its sources and the versions the kit claims."""

from __future__ import annotations

import hashlib
import json

from testence.kits import koobiq

from .kit_stand import STAND

STAMP = STAND / "dist" / "stand.json"


def _digest(path):
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_the_committed_build_was_made_from_these_sources():
    stamp = json.loads(STAMP.read_text(encoding="utf-8"))
    stale = [name for name, digest in stamp["sources"].items() if _digest(STAND / name) != digest]
    assert not stale, (
        f"bench/sut/koobiq/dist is older than {stale}: rebuild it with "
        "`npm ci --prefix bench/sut/koobiq && npm run build --prefix bench/sut/koobiq`"
    )


def test_the_stand_pins_exact_versions_and_the_kit_claims_them():
    package = json.loads((STAND / "package.json").read_text(encoding="utf-8"))
    pinned = {**package["dependencies"], **package["devDependencies"]}
    assert all(version[0].isdigit() for version in pinned.values()), pinned
    built = json.loads(STAMP.read_text(encoding="utf-8"))["packages"]
    assert built["@koobiq/react-components"] == pinned["@koobiq/react-components"]
    assert built["@koobiq/react-components"] in koobiq.VERIFIED
