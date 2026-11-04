"""react-aria primitives: the roles and behaviour every react-aria design system shares.

Koobiq, React Spectrum and react-aria-components render these the same way, because
the ARIA wiring and the interaction model come from ``@react-aria/*`` hooks, not from
the design system. Everything here is addressed by role and accessible name and
nothing depends on a design system's CSS classes (those live in
:mod:`testence.kits.koobiq`).

Each factory takes ``ex`` and returns a small object: its ``target`` (and sub-targets)
are plain :class:`~testence.engine.Target` values, its methods are ordinary ``ex``
steps with an intent. Traps carried here so a test does not have to:

- **A checkbox or switch input is visually hidden.** The ``<input>`` is clipped to one
  pixel inside a ``<label>``; clicking or ``check``-ing it waits on a hit test the label
  always wins. :class:`Checkbox` clicks the label and reads the input's state.
- **A NumberField commits on blur.** Typing changes the text, not the value: the
  field's ``onChange`` fires when focus leaves or Enter is pressed.
  :meth:`NumberField.set` fills, then presses Tab.
- **Menus and lists are portalled.** They render at the end of ``<body>``, not inside
  their trigger, so ``within=`` the trigger finds nothing. A menu is named after its
  trigger (``aria-labelledby``); a select's list after the field's label.
- **Tooltips open on hover after a delay**, or at once on focus. :class:`Tooltip`
  hovers and waits for ``role=tooltip``; it never sleeps.
- **A table is a ``grid``.** Rows are ``role=row`` named by their row header; the
  selection checkboxes carry translated names ("Select …"), so a row's checkbox is
  addressed by structure.
- **A mouse click on a row's selection checkbox is browser-dependent.** The row
  selects on ``pointerdown``; on Chromium 131 the check icon that appears under the
  pointer takes the ``pointerup``, and the label's native click then toggles the box
  back, so the row ends unselected. :meth:`Table.select_row` uses react-aria's keyboard
  selection instead (Space on the focused row header), which holds on every engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from testence.engine import Target


def button(name: str, *, within: Target | None = None, exact: bool = True) -> Target:
    return Target("role", "button", name=name, exact=exact, within=within)


@dataclass(frozen=True)
class Menu:
    """A menu opened by a trigger button (``MenuTrigger`` + ``Menu``)."""

    ex: Any = field(repr=False, compare=False)
    trigger: Target
    #: The open menu. react-aria labels it with its trigger.
    target: Target
    title: str

    def item(self, label: str) -> Target:
        return Target("role", "menuitem", name=label, within=self.target)

    def open(self) -> None:
        self.ex.click(self.trigger, intent=f"open the menu {self.title!r}")
        self.ex.expect_visible(self.target, intent=f"the menu {self.title!r} is open")

    def choose(self, label: str, *, closes: bool = True) -> None:
        """Open the menu and choose ``label``; by default the menu must close after it."""
        self.open()
        self.ex.click(self.item(label), intent=f"choose {label!r} in the menu {self.title!r}")
        if closes:
            self.ex.expect_hidden(
                self.target, intent=f"the menu {self.title!r} closed after {label!r}"
            )


def menu(ex: Any, trigger_name: str, *, within: Target | None = None) -> Menu:
    """The menu of the button named ``trigger_name`` (``within`` scopes the button only)."""
    return Menu(
        ex,
        trigger=button(trigger_name, within=within),
        target=Target("role", "menu", name=trigger_name),
        title=trigger_name,
    )


def menu_of(ex: Any, trigger: Target, *, title: str = "menu") -> Menu:
    """The menu of an unnamed trigger. Only one menu can be open; it is ``role=menu``."""
    return Menu(ex, trigger=trigger, target=Target("role", "menu"), title=title)


@dataclass(frozen=True)
class Listbox:
    """A list of options: a select's popover or a standalone ``ListBox``."""

    ex: Any = field(repr=False, compare=False)
    target: Target

    def option(self, label: str) -> Target:
        return Target("role", "option", name=label, within=self.target)

    def expect_selected(self, label: str, selected: bool = True) -> None:
        self.ex.expect_attribute(
            self.option(label),
            "aria-selected",
            "true" if selected else "false",
            intent=f"{label!r} is {'selected' if selected else 'not selected'} in the list",
        )


def listbox(ex: Any, name: str) -> Listbox:
    """The list named ``name``. A select's list is named after the field's label."""
    return Listbox(ex, Target("role", "listbox", name=name))


@dataclass(frozen=True)
class Checkbox:
    """A checkbox (or a switch) whose ``<input>`` is hidden inside a ``<label>``.

    ``target`` reads the state; ``clickable`` is what people click. ``check`` and
    ``uncheck`` assert the starting state first, so an already checked box fails
    loudly instead of being toggled off.
    """

    ex: Any = field(repr=False, compare=False)
    target: Target
    clickable: Target
    title: str
    role: str = "checkbox"

    def toggle(self, intent: str | None = None) -> None:
        self.ex.click(self.clickable, intent=intent or f"toggle the {self.role} {self.title!r}")

    def check(self) -> None:
        self._set(True)

    def uncheck(self) -> None:
        self._set(False)

    def expect_checked(self, checked: bool = True) -> None:
        state = "checked" if checked else "unchecked"
        self.ex.expect_checked(
            self.target, intent=f"the {self.role} {self.title!r} is {state}", checked=checked
        )

    def _set(self, checked: bool) -> None:
        state = "checked" if checked else "unchecked"
        self.ex.expect_checked(
            self.target,
            intent=f"the {self.role} {self.title!r} is not {state} yet",
            checked=not checked,
        )
        self.toggle(intent=f"{'check' if checked else 'uncheck'} {self.title!r}")
        self.expect_checked(checked)


def checkbox(ex: Any, label: str, *, within: Target | None = None) -> Checkbox:
    """A labelled checkbox; the click lands on its label text."""
    return Checkbox(
        ex,
        target=Target("role", "checkbox", name=label, within=within),
        clickable=Target("text", label, exact=True, within=within),
        title=label,
    )


def switch(ex: Any, label: str, *, within: Target | None = None) -> Checkbox:
    """A switch (``role=switch``): the same hidden input inside a label."""
    return Checkbox(
        ex,
        target=Target("role", "switch", name=label, within=within),
        clickable=Target("text", label, exact=True, within=within),
        title=label,
        role="switch",
    )


@dataclass(frozen=True)
class Tabs:
    ex: Any = field(repr=False, compare=False)
    target: Target

    def tab(self, label: str) -> Target:
        return Target("role", "tab", name=label, within=self.target)

    def panel(self, label: str) -> Target:
        """The panel of the tab ``label`` (react-aria names it after its tab)."""
        return Target("role", "tabpanel", name=label)

    def select(self, label: str) -> None:
        self.ex.click(self.tab(label), intent=f"open the tab {label!r}")
        self.ex.expect_attribute(
            self.tab(label), "aria-selected", "true", intent=f"the tab {label!r} is selected"
        )
        self.ex.expect_visible(self.panel(label), intent=f"the panel of {label!r} is shown")


def tabs(ex: Any, name: str, *, within: Target | None = None) -> Tabs:
    return Tabs(ex, Target("role", "tablist", name=name, within=within))


def dialog(name: str | None = None) -> Target:
    """A dialog with an accessible name. Koobiq's ``Dialog`` has none (its header is
    not a heading): address it by title with :func:`testence.kits.koobiq.dialog`."""
    return Target("role", "dialog", name=name)


@dataclass(frozen=True)
class Tooltip:
    ex: Any = field(repr=False, compare=False)
    trigger: Target
    target: Target = Target("role", "tooltip")

    def open(self) -> None:
        """Hover the trigger the way a moving mouse does, then wait for the tooltip.

        react-aria opens a tooltip on hover only when the interaction modality is
        already "pointer", which a ``pointermove`` on the document sets. A test's first
        pointer move enters the trigger before that listener has seen any pointer, so
        a single hover on an untouched page opens nothing. The pointer moves to the
        page corner first (one native step: the DSL has no bare mouse move).
        """
        with self.ex.native("move the pointer to the corner of the page") as page:
            page.mouse.move(0, 0)
        self.ex.hover(self.trigger, intent="hover the tooltip trigger")
        self.ex.expect_visible(self.target, intent="the tooltip is shown")

    def expect_text(self, text: str) -> None:
        self.open()
        self.ex.expect_text(self.target, text, intent=f"the tooltip reads {text!r}")


def tooltip(ex: Any, trigger: Target) -> Tooltip:
    return Tooltip(ex, trigger)


_ROW_CHECKBOX = 'label:has(input[type="checkbox"])'


@dataclass(frozen=True)
class Table:
    """A react-aria table: ``role=grid``, rows named by their row header."""

    ex: Any = field(repr=False, compare=False)
    target: Target
    title: str

    def row(self, name: str) -> Target:
        return Target("role", "row", name=name, within=self.target)

    def rowheader(self, name: str) -> Target:
        return Target("role", "rowheader", name=name, within=self.target)

    def cell(self, row: str, text: str) -> Target:
        return Target("role", "gridcell", name=text, within=self.row(row))

    def rows(self) -> Target:
        """Body rows, counted through their row headers (the header row has none)."""
        return Target("role", "rowheader", within=self.target)

    def row_checkbox(self, name: str) -> Target:
        """The selection box of a row: the ``<label>`` around its hidden input.

        Its accessible name ("Select router-one", "Выбрать router-one") starts with a
        translated word, so the address is structural: the row's first checkbox
        label, which is the selection column.
        """
        return Target("css", _ROW_CHECKBOX, nth=0, within=self.row(name))

    def select_all(self) -> Target:
        header = Target("role", "columnheader", nth=0, within=self.target)
        return Target("css", _ROW_CHECKBOX, nth=0, within=header)

    def select_row(self, name: str) -> None:
        """Select the row with the keyboard: Space on its focused row header.

        Space toggles selection in a react-aria grid whatever a row click does (a
        table with row actions opens the row on click). A mouse click on the selection
        checkbox (``row_checkbox``) toggles twice on Chromium 131; see the module notes.
        """
        self._toggle(name, True)

    def unselect_row(self, name: str) -> None:
        self._toggle(name, False)

    def _toggle(self, name: str, selected: bool) -> None:
        verb = "select" if selected else "unselect"
        self.expect_selected(name, not selected)
        self.ex.press("Space", self.rowheader(name), intent=f"{verb} the row {name!r}")
        self.expect_selected(name, selected)

    def expect_selected(self, name: str, selected: bool = True) -> None:
        self.ex.expect_attribute(
            self.row(name),
            "aria-selected",
            "true" if selected else "false",
            intent=f"the row {name!r} is {'selected' if selected else 'not selected'}",
        )

    def expect_rows(self, count: int) -> None:
        self.ex.expect_count(self.rows(), count, intent=f"{self.title!r} shows {count} rows")

    def row_menu(self, row: str, trigger_name: str) -> Menu:
        """The menu opened by the button ``trigger_name`` in ``row``."""
        return menu(self.ex, trigger_name, within=self.row(row))


def table(ex: Any, name: str) -> Table:
    return Table(ex, Target("role", "grid", name=name), name)


@dataclass(frozen=True)
class NumberField:
    ex: Any = field(repr=False, compare=False)
    target: Target
    title: str

    def set(self, value: int | float | str, *, shown: str | None = None) -> None:
        """Type ``value`` and commit it with Tab; then the field must show ``shown``.

        ``shown`` defaults to ``str(value)``. A locale that groups digits shows
        ``4 094`` or ``4,094``: pass what the field displays.
        """
        self.ex.click(self.target, intent=f"focus the number field {self.title!r}")
        self.ex.fill(self.target, str(value), intent=f"type {value!r} into {self.title!r}")
        self.ex.press("Tab", intent=f"commit {self.title!r} by leaving it")
        self.expect_value(shown if shown is not None else str(value))

    def expect_value(self, shown: str) -> None:
        self.ex.expect_value(self.target, shown, intent=f"{self.title!r} shows {shown!r}")


def number_field(
    ex: Any, label: str, *, within: Target | None = None, exact: bool = True
) -> NumberField:
    return NumberField(ex, Target("role", "textbox", name=label, exact=exact, within=within), label)


@dataclass(frozen=True)
class SearchField:
    ex: Any = field(repr=False, compare=False)
    target: Target
    title: str

    def submit(self, text: str) -> None:
        """Type ``text`` and submit it with Enter (the only submit a search field has)."""
        self.ex.fill(self.target, text, intent=f"type {text!r} into the search {self.title!r}")
        self.ex.press("Enter", self.target, intent=f"submit the search {self.title!r}")


def search_field(ex: Any, label: str, *, within: Target | None = None) -> SearchField:
    return SearchField(ex, Target("role", "searchbox", name=label, within=within), label)


__all__ = [
    "Checkbox",
    "Listbox",
    "Menu",
    "NumberField",
    "SearchField",
    "Table",
    "Tabs",
    "Tooltip",
    "button",
    "checkbox",
    "dialog",
    "listbox",
    "menu",
    "menu_of",
    "number_field",
    "search_field",
    "switch",
    "table",
    "tabs",
    "tooltip",
]
