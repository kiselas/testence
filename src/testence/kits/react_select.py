"""react-select (5.x), single and ``isMulti``.

react-select renders its parts with ``<prefix>__control``, ``__menu``, ``__option``,
``__multi-value`` … class names **only when the product sets** ``classNamePrefix``;
without it every class is a generated ``css-…`` hash and nothing here can find the
field. Pass ``prefix=`` when the product uses another prefix than ``react-select``.

The field is found by its combobox input: ``aria-label``, ``aria-labelledby`` or a
``<label for>`` naming it ``label``, or ``input_id=`` when the product sets
``inputId``. Traps carried here:

- **Escape closes more than the menu.** Inside a dialog or side panel, Escape also
  dismisses the overlay. :meth:`ReactSelect.close` takes focus away instead (react-
  select closes its menu on blur).
- **Backspace in an empty search removes the last chip.** :meth:`ReactSelect.search`
  fills the input (which replaces its text) and never sends Backspace.
- **A multi-select may keep its menu open after a pick, or close it**
  (``closeMenuOnSelect``). :meth:`ReactSelect.pick` reopens it only when it is closed.
- **A saved value the options no longer offer still renders a chip.** :meth:`state`
  reports each chip and whether the open menu offers it.
- **The menu, its groups and its "no options" notice** are read in one evaluation
  (:meth:`ReactSelect.state`), not one step per option.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from testence.engine import Target
from testence.kits import _support

_STATE = """(spec) => {
    const tok = (el, name) => el && (' ' + el.className + ' ').includes(' ' + name + ' ');
    const p = spec.prefix;
    const named = input => {
        if (spec.inputId) return input.id === spec.inputId;
        const text = el => (el ? el.textContent : '').replace(/\\s+/g, ' ').trim();
        if (input.getAttribute('aria-label')) return input.getAttribute('aria-label').trim() === spec.label;
        const ids = (input.getAttribute('aria-labelledby') || '').split(/\\s+/).filter(Boolean);
        if (ids.length) return ids.map(id => text(document.getElementById(id))).join(' ') === spec.label;
        return [...(input.labels || [])].some(l => text(l) === spec.label);
    };
    const inputs = [...document.querySelectorAll('input[role="combobox"]')].filter(named);
    if (inputs.length !== 1) return {found: inputs.length};
    const input = inputs[0];
    let control = input;
    while (control && !tok(control, p + '__control')) control = control.parentElement;
    if (!control) return {found: 0, prefix: false};
    const container = control.parentElement;
    const own = container.querySelector(':scope > .' + p + '__menu');
    const menu = own || (input.getAttribute('aria-expanded') === 'true'
        ? document.querySelector('.' + p + '__menu') : null);
    const chips = [...control.querySelectorAll('.' + p + '__multi-value')].map(chip => ({
        label: ((chip.querySelector('.' + p + '__multi-value__label') || chip).textContent || '').trim(),
        removable: Boolean(chip.querySelector('[role="button"]')),
    }));
    const single = control.querySelector('.' + p + '__single-value');
    const placeholder = control.querySelector('.' + p + '__placeholder');
    const state = {
        found: 1,
        chips: chips.map(c => c.label),
        single: single ? single.textContent.trim() : null,
        placeholder: placeholder ? placeholder.textContent.trim() : null,
        disabled: tok(control, p + '__control--is-disabled') || input.disabled,
        open: Boolean(menu),
        loading: Boolean(container.querySelector('.' + p + '__loading-indicator')),
        clearable: Boolean(control.querySelector('.' + p + '__clear-indicator')),
        search: input.value,
    };
    if (!menu) return state;
    const grouped = new Map();
    for (const group of menu.querySelectorAll('.' + p + '__group')) {
        const heading = group.querySelector('.' + p + '__group-heading');
        for (const option of group.querySelectorAll('.' + p + '__option')) {
            grouped.set(option, heading ? heading.textContent.trim() : '');
        }
    }
    state.options = [...menu.querySelectorAll('.' + p + '__option')].map(o => ({
        label: o.textContent.trim(),
        group: grouped.has(o) ? grouped.get(o) : null,
        selected: o.getAttribute('aria-selected') === 'true' || tok(o, p + '__option--is-selected'),
        disabled: o.getAttribute('aria-disabled') === 'true' || tok(o, p + '__option--is-disabled'),
        focused: tok(o, p + '__option--is-focused'),
    }));
    state.groups = [...menu.querySelectorAll('.' + p + '__group-heading')].map(h => h.textContent.trim());
    const notice = menu.querySelector('.' + p + '__menu-notice');
    state.notice = notice ? notice.textContent.trim() : null;
    const offered = new Set(state.options.map(o => o.label));
    state.unoffered = state.chips.filter(c => !offered.has(c));
    return state;
}"""
_IS_OPEN = (
    f"(spec, open) => {{ const s = ({_STATE})(spec); return s.found === 1 && s.open === open; }}"
)
_HAS_CHIPS = f"""(spec, chips) => {{ const s = ({_STATE})(spec);
    return s.found === 1 && JSON.stringify(s.chips) === JSON.stringify(chips); }}"""
_HAS_SINGLE = f"""(spec, value) => {{ const s = ({_STATE})(spec);
    return s.found === 1 && s.single === value; }}"""
_LOADED = f"(spec) => {{ const s = ({_STATE})(spec); return s.found === 1 && !s.loading; }}"
_BLUR = """(spec) => {
    const el = document.activeElement;
    if (el && el.getAttribute('role') === 'combobox') el.blur();
    return true;
}"""


def _cls(name: str) -> str:
    return f'contains(concat(" ", normalize-space(@class), " "), " {name} ")'


@dataclass(frozen=True)
class ReactSelect:
    ex: Any = field(repr=False, compare=False)
    label: str
    multi: bool
    prefix: str
    input_id: str | None
    #: The search input (``role=combobox``).
    input: Target
    #: The control box around chips, value and indicators.
    control: Target
    #: The open menu (inside the field, or portalled to ``<body>``).
    menu: Target

    @property
    def _spec(self) -> dict[str, Any]:
        return {"label": self.label, "inputId": self.input_id, "prefix": self.prefix}

    def option(self, label: str) -> Target:
        return Target("role", "option", name=label, within=self.menu)

    def chip(self, label: str) -> Target:
        p = self.prefix
        return Target(
            "css",
            f"{self.control.value}//*[{_cls(p + '__multi-value')}]"
            f"[*[{_cls(p + '__multi-value__label')}][normalize-space(.)="
            f"{_support.xpath_literal(label)}]]",
        )

    def chip_remove(self, label: str) -> Target:
        """The chip's remove button: ``[role=button]`` inside the chip, whatever its
        name ("Remove <label>" by default, often "Delete" in a design system)."""
        return Target("css", '[role="button"]', nth=0, within=self.chip(label))

    @property
    def clear_indicator(self) -> Target:
        return Target("css", f".{self.prefix}__clear-indicator", within=self.control)

    def state(self) -> dict[str, Any]:
        """The field in one read: chips, single value, placeholder, open, loading, and
        when open the options (label, group, selected, disabled, focused), group
        headings, the notice and the chips the menu does not offer."""
        result = _support.read(
            self.ex, f"read the field {self.label!r}", _STATE, self._spec, target=self.input
        )
        if not isinstance(result, dict) or result.get("found") != 1:
            found = result.get("found") if isinstance(result, dict) else result
            raise AssertionError(f"react-select {self.label!r}: {found} fields match")
        return result

    def open(self) -> None:
        self.ex.click(self.control, intent=f"open the options of {self.label!r}")
        self.expect_open(True)

    def expect_open(self, open_: bool = True) -> None:
        _support.wait_until(
            self.ex,
            f"the options of {self.label!r} are {'open' if open_ else 'closed'}",
            _IS_OPEN,
            self._spec,
            open_,
            describe=_STATE,
            target=self.input,
        )

    def close(self) -> None:
        """Close the menu by taking focus away (Escape would close a dialog too)."""
        _support.read(self.ex, f"take focus out of {self.label!r}", _BLUR, self._spec)
        self.expect_open(False)

    def wait_loaded(self) -> None:
        """Wait until the field shows no loading indicator (async options arrived)."""
        _support.wait_until(
            self.ex,
            f"the options of {self.label!r} are loaded",
            _LOADED,
            self._spec,
            describe=_STATE,
            target=self.input,
        )

    def search(self, text: str) -> None:
        """Type ``text`` into the search; fill replaces the text, it sends no Backspace."""
        self.ex.fill(self.input, text, intent=f"search {text!r} in {self.label!r}")

    def pick(self, *labels: str, keep_open: bool = False) -> None:
        """Choose options by label, in order; each must then show as a chip (multi)
        or as the value (single). The menu is reopened only when it closed."""
        for label in labels:
            if not self.state()["open"]:
                self.open()
            self.ex.click(self.option(label), intent=f"pick {label!r} in {self.label!r}")
            if self.multi:
                self.ex.expect_visible(self.chip(label), intent=f"{label!r} is a chip")
            else:
                self.expect_value(label)
        if not keep_open and self.state()["open"]:
            self.close()

    def remove(self, label: str) -> None:
        self.ex.click(self.chip_remove(label), intent=f"remove the chip {label!r}")
        self.ex.expect_hidden(self.chip(label), intent=f"the chip {label!r} is gone")

    def clear(self) -> None:
        self.ex.click(self.clear_indicator, intent=f"clear {self.label!r}")

    def expect_chips(self, labels: list[str]) -> None:
        _support.wait_until(
            self.ex,
            f"{self.label!r} holds the chips {labels}",
            _HAS_CHIPS,
            self._spec,
            list(labels),
            describe=_STATE,
            target=self.input,
        )

    def expect_value(self, value: str | None) -> None:
        """A single select shows ``value`` (``None``: nothing chosen)."""
        _support.wait_until(
            self.ex,
            f"{self.label!r} shows {value!r}",
            _HAS_SINGLE,
            self._spec,
            value,
            describe=_STATE,
            target=self.input,
        )


def _build(ex: Any, label: str, multi: bool, prefix: str, input_id: str | None) -> ReactSelect:
    lit = _support.xpath_literal(label)
    if input_id is not None:
        named = f"@id={_support.xpath_literal(input_id)}"
        field_input = Target("css", f"input[id={_support.css_string(input_id)}]")
    else:
        named = (
            f"@aria-label={lit} or @aria-labelledby=//*[normalize-space(.)={lit}]/@id"
            f" or @id=//label[normalize-space(.)={lit}]/@for"
        )
        field_input = Target("role", "combobox", name=label)
    control = f"xpath=//*[{_cls(prefix + '__control')}][.//input[@role='combobox'][{named}]]"
    # The menu is the control's sibling; a portalled menu (menuPortalTarget) is the
    # only one open, at the end of <body>.
    menu = Target(
        "css",
        f"{control}/following-sibling::*[{_cls(prefix + '__menu')}]"
        f" | //body/*[{_cls(prefix + '__menu-portal')}]//*[{_cls(prefix + '__menu')}]",
    )
    return ReactSelect(
        ex,
        label=label,
        multi=multi,
        prefix=prefix,
        input_id=input_id,
        input=field_input,
        control=Target("css", control),
        menu=menu,
    )


def single(
    ex: Any, label: str, *, prefix: str = "react-select", input_id: str | None = None
) -> ReactSelect:
    """A single-value react-select whose combobox is named ``label``."""
    return _build(ex, label, False, prefix, input_id)


def multi(
    ex: Any, label: str, *, prefix: str = "react-select", input_id: str | None = None
) -> ReactSelect:
    """An ``isMulti`` react-select whose combobox is named ``label``."""
    return _build(ex, label, True, prefix, input_id)


__all__ = ["ReactSelect", "multi", "single"]
