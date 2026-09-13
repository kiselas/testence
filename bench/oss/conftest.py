import pytest


@pytest.fixture(autouse=True)
def panel_capture(testence_settings):
    # Explicit consent for local, synthetic screenshot evidence in this corpus.
    testence_settings.extra["capture_policy"] = {"screenshots": True}
    testence_settings.timeout_ms = 2000
