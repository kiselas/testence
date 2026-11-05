"""Secrets that sat outside a value: parameter ids, traceback text, fingerprints (T07).

Every canary is synthetic. Masking changes what is shown; the identity of a test (case,
variant, Allure history) is computed from the original value and must not move.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from testence import allure_compat
from testence.export import export_run
from testence.fingerprints import FingerprintStore
from testence.report import render_report
from tests.test_auto_env_masking import run_project, tree_text

# Accented and Cyrillic letters: pytest writes them into a parameter id escaped, in a
# spelling that is neither the secret itself nor its JSON or repr() form.
CANARY = "sécret-ключ-7f3a9"
SETTINGS = {"evidence": {"redact": {"env": ["SYNTH_ID_SECRET"]}}}
ENV = {"SYNTH_ID_SECRET": CANARY}

_PARAM_TEST = (
    """
import pytest

@pytest.mark.parametrize("user", ["%s", "plain"])
def test_login(user):
    assert user == "plain"
"""
    % CANARY
)


def _leaks(text: str) -> list[str]:
    forms = {CANARY, CANARY.encode("unicode_escape").decode("ascii")}
    return sorted(form for form in forms if form in text)


def _export_everything(run_dir: Path, out: Path) -> None:
    export_run(run_dir, "allure", out / "allure")
    export_run(run_dir, "ctrf", out / "ctrf")
    export_run(run_dir, "junit", out / "junit")
    render_report(run_dir, out / "report.html")


def test_a_secret_in_a_parameter_id_reaches_no_artifact(tmp_path):
    run_dir = run_project(tmp_path / "project", {"test_ids.py": _PARAM_TEST}, SETTINGS, ENV)
    _export_everything(run_dir, tmp_path / "exports")
    assert _leaks(tree_text(run_dir)) == []
    assert _leaks(tree_text(tmp_path / "exports")) == []
    assert "test_login[plain]" in (run_dir / "run.jsonl").read_text(encoding="utf-8")


def _allure_identities(directory: Path) -> dict[str, list[tuple[str, str]]]:
    found: dict[str, list[tuple[str, str]]] = {}
    for path in directory.glob("*-result.json"):
        result = json.loads(path.read_text(encoding="utf-8"))
        found.setdefault(result["name"], []).append((result["testCaseId"], result["historyId"]))
    return found


def test_allure_history_does_not_move_when_the_id_is_masked(tmp_path):
    """Two runs agree, and the history id is the one allure-pytest computes from the
    original values: masking the shown id must not feed back into identity."""
    files = {"test_ids.py": _PARAM_TEST}
    first = run_project(tmp_path / "one", files, SETTINGS, ENV)
    second = run_project(tmp_path / "two", files, SETTINGS, ENV)
    export_run(first, "allure", tmp_path / "allure-one")
    export_run(second, "allure", tmp_path / "allure-two")
    one = _allure_identities(tmp_path / "allure-one")
    assert one == _allure_identities(tmp_path / "allure-two")
    assert set(one) == {"test_login[<redacted>]", "test_login[plain]"}
    name = "test_ids#test_login"
    assert one["test_login[<redacted>]"] == [
        (allure_compat.md5(name), allure_compat.history_id(name, {"user": CANARY}))
    ]


def test_two_secret_variants_stay_two_cases_after_masking(tmp_path):
    other = "second-" + CANARY
    source = f"""
import pytest

@pytest.mark.parametrize("user", ["{CANARY}", "{other}"])
def test_login(user):
    assert False
"""
    settings = {"evidence": {"redact": {"env": ["SYNTH_ID_SECRET", "SYNTH_ID_OTHER"]}}}
    env = {**ENV, "SYNTH_ID_OTHER": other}
    run_dir = run_project(tmp_path / "project", {"test_ids.py": source}, settings, env)
    export_run(run_dir, "allure", tmp_path / "allure")
    (identities,) = _allure_identities(tmp_path / "allure").values()
    # Both are shown as test_login[<redacted>], and the results still differ in history.
    assert len({history for _, history in identities}) == 2
    results = list((tmp_path / "allure").glob("*-result.json"))
    assert len(results) == 2
    assert _leaks(tree_text(run_dir) + tree_text(tmp_path / "allure")) == []
    events = [
        json.loads(line)
        for line in (run_dir / "run.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    variants = {e["variant_id"] for e in events if e["kind"] == "test.start"}
    assert len(variants) == 2


_CLIP_TEST = (
    """
import pytest

SECRET = "%s"

@pytest.mark.parametrize("padding", range(7940, 8010, 2))
def test_long_message(padding):
    raise AssertionError(SECRET + "z" * padding)
"""
    % "SYNTH-TAIL-0123456789abcdef"
)


def test_a_secret_cut_by_the_traceback_clip_leaves_no_fragment(tmp_path):
    """The traceback keeps its last 8000 characters. Clipped before masking, a secret
    on the boundary was split and its remaining half matched nothing."""
    secret = "SYNTH-TAIL-0123456789abcdef"
    settings = {"evidence": {"redact": {"env": ["SYNTH_TAIL"]}}}
    run_dir = run_project(
        tmp_path / "project", {"test_clip.py": _CLIP_TEST}, settings, {"SYNTH_TAIL": secret}
    )
    ledger = (run_dir / "run.jsonl").read_text(encoding="utf-8")
    fragments = [secret[i : i + 8] for i in range(len(secret) - 7)]
    assert [piece for piece in fragments if piece in ledger] == []


_FINGERPRINT_TEST = """
def test_login_learns_a_token(testence_writer, testence_fingerprints, request):
    late = "SYNTH-LATE-token-5d2e81"
    testence_writer.remember_secret(late)  # what a login produces, after the fixture
    testence_fingerprints.record(
        request.node.nodeid,
        "click the copy button",
        f"role=button name='Copy {late}'",
        {"tag": "button", "text": f"Copy {late}", "ariaLabel": "copy"},
    )
"""


def test_a_secret_learned_after_the_store_exists_is_masked_in_fingerprints(tmp_path):
    project = tmp_path / "project"
    run_project(project, {"test_fp.py": _FINGERPRINT_TEST}, {}, {}, returncode=0)
    stored = (project / ".testence" / "fingerprints.json").read_text(encoding="utf-8")
    assert "SYNTH-LATE" not in stored
    assert "Copy <redacted>" in stored


def test_masked_ids_keep_their_own_fingerprint_entry(tmp_path):
    first, second = "variant-secret-aaaa1111", "variant-secret-bbbb2222"
    store = FingerprintStore(tmp_path / "fp.json", worker="", redact_values=[first, second])
    fingerprint = {"tag": "button", "text": "Pay"}
    store.record(f"test_pay[{first}]", "click pay", "role=button", {**fingerprint, "id": "a"})
    store.record(f"test_pay[{second}]", "click pay", "role=button", {**fingerprint, "id": "b"})
    store.flush()
    stored = (tmp_path / "fp.json").read_text(encoding="utf-8")
    assert first not in stored and second not in stored
    assert len(json.loads(stored)) == 2
    reloaded = FingerprintStore(tmp_path / "fp.json", worker="", redact_values=[first, second])
    assert reloaded.get(f"test_pay[{first}]", "click pay")["id"] == "a"
    assert reloaded.get(f"test_pay[{second}]", "click pay")["id"] == "b"


def test_an_unmasked_id_keeps_the_key_it_always_had(tmp_path):
    store = FingerprintStore(tmp_path / "fp.json", worker="", redact_values=["unrelated-secret"])
    store.record("test_pay[plain]", "click pay", "role=button", {"tag": "button"})
    store.flush()
    assert list(json.loads((tmp_path / "fp.json").read_text(encoding="utf-8"))) == [
        "test_pay[plain]::click pay"
    ]


@pytest.mark.parametrize("secret", [CANARY, "plain-ascii-secret-91"])
def test_pytest_id_escapes_are_a_known_form(secret):
    from testence.evidence.sanitize import sanitize_text

    escaped = f"test_x[{secret.encode('unicode_escape').decode('ascii')}]"
    assert secret not in sanitize_text(escaped, secrets=[secret])
    assert "7f3a9" not in sanitize_text(escaped, secrets=[CANARY])
