"""``@allure.*`` and ``allure.dynamic.*`` without allure-pytest.

The ``allure`` package (allure-python-commons) turns its decorators into pytest
marks only through a helper that allure-pytest registers; with no helper, every
``@allure.feature`` silently does nothing. A suite that finished moving to Testence
and dropped allure-pytest therefore lost its labels, links, ids and titles with no
warning. Testence registers the same helper when allure-pytest is not active, so the
marks :mod:`testence.allure_compat` reads exist either way.

``allure.dynamic.*`` never creates marks: it reports to whoever listens while the
test runs. :class:`DynamicValues` listens for the current attempt, and the plugin
records what it heard on ``test.end`` (``allure_dynamic``).

Imported only when ``allure_commons`` is installed.
"""

from __future__ import annotations

from typing import Any

import allure_commons
import pytest
from allure_commons import hookimpl

from testence.allure_compat import label_text

#: The marks allure-pytest's helper creates (allure_pytest.utils).
MARKS = ("allure_label", "allure_link", "allure_description", "allure_description_html")


class Decorators:
    """What allure-pytest's ``AllureTitleHelper`` and ``AllureTestHelper`` do."""

    @hookimpl
    def decorate_as_title(self, test_title: str) -> Any:
        def decorator(func: Any) -> Any:
            # A fixture is wrapped; the title belongs on the function inside.
            if hasattr(func, "_get_wrapped_function"):  # pytest >= 8.4
                function = func._get_wrapped_function()
            elif hasattr(func, "__pytest_wrapped__"):
                function = func.__pytest_wrapped__.obj
            else:
                function = func
            function.__allure_display_name__ = test_title
            return func

        return decorator

    @hookimpl
    def decorate_as_description(self, test_description: str) -> Any:
        return pytest.mark.allure_description(test_description)

    @hookimpl
    def decorate_as_description_html(self, test_description_html: str) -> Any:
        return pytest.mark.allure_description_html(test_description_html)

    @hookimpl
    def decorate_as_label(self, label_type: str, labels: tuple[Any, ...]) -> Any:
        return pytest.mark.allure_label(*labels, label_type=label_type)

    @hookimpl
    def decorate_as_link(self, url: str, link_type: str, name: str | None) -> Any:
        return pytest.mark.allure_link(url, name=url if name is None else name, link_type=link_type)


class DynamicValues:
    """``allure.dynamic.*`` calls made during the current attempt."""

    def __init__(self) -> None:
        self._current: dict[str, Any] | None = None

    def begin(self) -> None:
        self._current = {}

    def take(self) -> dict[str, Any]:
        heard, self._current = self._current or {}, None
        return heard

    @hookimpl
    def add_title(self, test_title: str) -> None:
        if self._current is not None:
            self._current["title"] = str(test_title)

    @hookimpl
    def add_description(self, test_description: str) -> None:
        if self._current is not None:
            self._current["description"] = str(test_description)

    @hookimpl
    def add_description_html(self, test_description_html: str) -> None:
        if self._current is not None:
            self._current["description_html"] = str(test_description_html)

    @hookimpl
    def add_label(self, label_type: str, labels: tuple[Any, ...]) -> None:
        if self._current is not None:
            found = self._current.setdefault("labels", [])
            found.extend(
                {"name": label_text(label_type), "value": label_text(value)} for value in labels
            )

    @hookimpl
    def add_link(self, url: str, link_type: str, name: str | None) -> None:
        if self._current is not None:
            self._current.setdefault("links", []).append(
                {"type": label_text(link_type or "link"), "url": str(url), "name": str(name or url)}
            )


def install(config: pytest.Config) -> DynamicValues:
    """Register the listeners for this session; they leave with it."""
    manager = allure_commons.plugin_manager
    registered: list[Any] = []
    # By entry point (autoload) or by module (``-p allure_pytest.plugin``).
    allure_pytest = any(
        config.pluginmanager.has_plugin(name) for name in ("allure_pytest", "allure_pytest.plugin")
    )
    if not allure_pytest:
        decorators = Decorators()
        manager.register(decorators)
        registered.append(decorators)
        for mark in MARKS:
            config.addinivalue_line("markers", f"{mark}: allure-pytest compatible metadata")
    dynamic = DynamicValues()
    manager.register(dynamic)
    registered.append(dynamic)

    def uninstall() -> None:
        for plugin in registered:
            manager.unregister(plugin)

    config.add_cleanup(uninstall)
    return dynamic
