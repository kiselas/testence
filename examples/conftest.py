import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "demo_failure: deliberately failing pack demo")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("-m", default=""):
        return
    skip = pytest.mark.skip(reason="pack demo; run with -m demo_failure")
    for item in items:
        if "demo_failure" in item.keywords:
            item.add_marker(skip)
