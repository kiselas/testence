from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from testence.distribution import DistributionError, compare_wheel_payloads, inspect_wheel


def _wheel(
    path: Path,
    *,
    metadata_name: str = "testence",
    record_content: str = "",
    package_content: str = "__version__ = '0.1.0.dev0'\n",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("testence/__init__.py", package_content)
        archive.writestr(
            "testence-0.1.0.dev0.dist-info/METADATA",
            f"Metadata-Version: 2.4\nName: {metadata_name}\nVersion: 0.1.0.dev0\n",
        )
        archive.writestr(
            "testence-0.1.0.dev0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr("testence-0.1.0.dev0.dist-info/RECORD", record_content)
    return path


def test_inspect_wheel_rejects_arbitrary_bytes(tmp_path):
    fake = tmp_path / "testence-0.1.0.dev0-py3-none-any.whl"
    fake.write_text("not a wheel", encoding="utf-8")

    with pytest.raises(DistributionError, match="not a wheel archive"):
        inspect_wheel(fake)


def test_inspect_wheel_binds_filename_metadata_and_package_payload(tmp_path):
    wheel = _wheel(tmp_path / "testence-0.1.0.dev0-py3-none-any.whl")

    result = inspect_wheel(wheel)

    assert result["name"] == "testence"
    assert result["version"] == "0.1.0.dev0"
    assert result["package_members"] == ["testence/__init__.py"]


def test_inspect_wheel_rejects_metadata_for_another_distribution(tmp_path):
    wheel = _wheel(
        tmp_path / "testence-0.1.0.dev0-py3-none-any.whl",
        metadata_name="different-project",
    )

    with pytest.raises(DistributionError, match="differs from METADATA"):
        inspect_wheel(wheel)


def test_wheel_payload_comparison_ignores_container_and_record_bytes(tmp_path):
    first = _wheel(tmp_path / "first" / "testence-0.1.0.dev0-py3-none-any.whl")
    second = _wheel(
        tmp_path / "second" / "testence-0.1.0.dev0-py3-none-any.whl",
        record_content="changed",
    )

    result = compare_wheel_payloads(first, second)

    assert result["normative_files"] == 3


def test_wheel_payload_comparison_rejects_changed_resource(tmp_path):
    first = _wheel(tmp_path / "first" / "testence-0.1.0.dev0-py3-none-any.whl")
    second = _wheel(
        tmp_path / "second" / "testence-0.1.0.dev0-py3-none-any.whl",
        package_content="__version__ = '9.9.9'\n",
    )

    with pytest.raises(DistributionError, match="payload differs"):
        compare_wheel_payloads(first, second)
