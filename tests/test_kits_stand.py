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


def test_every_verified_version_has_evidence_from_the_current_stand():
    """A version is verified by the committed build or by a receipt whose stand had the
    same page sources as today's; a receipt older than the sources must be redone."""
    built = json.loads(STAMP.read_text(encoding="utf-8"))
    page = {k: v for k, v in built["sources"].items() if not k.startswith("package")}
    for version in koobiq.VERIFIED:
        if version == built["packages"]["@koobiq/react-components"]:
            continue
        receipt_path = STAND / "receipts" / f"koobiq-{version}.json"
        assert receipt_path.is_file(), f"{version} is claimed verified without a receipt"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert receipt["stand"]["packages"]["@koobiq/react-components"] == version
        sources = receipt["stand"]["sources"]
        assert {k: v for k, v in sources.items() if not k.startswith("package")} == page, (
            f"the {version} receipt was made from other stand sources: re-run it"
        )
        assert receipt["runs"] and all(" passed" in run["result"] for run in receipt["runs"])
        assert not any("failed" in run["result"] for run in receipt["runs"])


def test_supported_range_ends_at_the_next_unverified_minor():
    newest = max(tuple(int(part) for part in v.split(".")) for v in koobiq.VERIFIED)
    assert koobiq.SUPPORTED == f">=0.37,<0.{newest[1] + 1}"
