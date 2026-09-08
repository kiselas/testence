from testence.fingerprints import FingerprintStore

FP = {
    "tag": "button",
    "role": "button",
    "ariaLabel": "save",
    "testid": None,
    "text": "Save",
    "id": "save",
    "classes": ["btn"],
}


def test_records_and_reads_back_by_intent(tmp_path):
    store = FingerprintStore(tmp_path / "fp.json", worker="")
    store.record("test_save", "click the save button", "role=button name='Save'", FP)
    store.flush()

    reloaded = FingerprintStore(tmp_path / "fp.json", worker="")
    assert reloaded.get("test_save", "click the save button") == FP
    assert reloaded.get("test_save", "some other step") is None


def test_full_nodeid_can_read_a_legacy_short_name_entry(tmp_path):
    store = FingerprintStore(tmp_path / "fp.json", worker="")
    store.record("test_save", "click the save button", "role=button name='Save'", FP)
    store.flush()

    reloaded = FingerprintStore(tmp_path / "fp.json", worker="")

    assert reloaded.get("tests/test_save.py::TestForm::test_save", "click the save button") == FP


def test_empty_fingerprint_is_not_recorded(tmp_path):
    store = FingerprintStore(tmp_path / "fp.json", worker="")
    store.record("t", "intent", "target", {})
    store.flush()
    assert not (tmp_path / "fp.json").exists()


def test_corrupt_store_never_fails_a_run(tmp_path):
    path = tmp_path / "fp.json"
    path.write_text("{not json", encoding="utf-8")
    store = FingerprintStore(path, worker="")
    assert store.get("t", "i") is None  # degrades to "no memory", not a crash


def test_flush_is_idempotent(tmp_path):
    store = FingerprintStore(tmp_path / "fp.json", worker="")
    store.record("t", "i", "target", FP)
    store.flush()
    mtime = (tmp_path / "fp.json").stat().st_mtime_ns
    store.flush()  # nothing dirty — no rewrite
    assert (tmp_path / "fp.json").stat().st_mtime_ns == mtime
