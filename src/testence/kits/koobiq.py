"""Koobiq (``@koobiq/react-components``): what it renders on top of react-aria.

Checked against the package sources and the conformance stand
(``bench/sut/koobiq``) on 2026-11-04, for ``@koobiq/react-components`` 0.37.0 and
0.38.0. Koobiq is pre-1.0; :data:`SUPPORTED` is the range this kit is held to, and
:data:`VERIFIED` the versions the stand was built and passed with.

How addresses are chosen, most stable first:

1. role and accessible name (from :mod:`testence.kits.react_aria`);
2. Koobiq's ``data-*`` attributes (``data-slot``, ``data-transition``,
   ``data-status``, ``data-variant``), which are part of its rendered API;
3. a CSS-module class *prefix* such as ``kbq-dialog-header-``. Koobiq hashes its
   module classes (``kbq-dialog-header-f96b65``); the prefix is the component and
   part name, the suffix changes between releases. Nothing here matches a full
   hashed class.

Traps this module carries:

- **Koobiq translates its own labels.** Close buttons, "Select all", "Remove …" and
  the toast region read "Закрыть", "Выбрать все", "Удалить …" under a Russian
  locale. Nothing here addresses an element by such a label.
- **A required field's name ends in " *"** (``Name *``), and a hint placed in the
  label joins the name (``VLAN from 1 to 4094``). :func:`text_field` composes the
  exact name from ``required=`` and ``hint=`` instead of matching a substring.
- **A select's accessible name is "label value"**, and its label also names the open
  list, so the label alone matches two elements while the list is open.
  :class:`Select` reaches the trigger through the form field (``data-slot``).
- **Dialogs have no accessible name**: ``Dialog.Header`` is a ``div``, not a heading.
  :func:`dialog`, :func:`side_panel` and :func:`confirm` find a dialog by its title.
- **Overlays animate in and out for 300 ms** and stay mounted while leaving
  (``data-transition`` = entering, entered, exiting). ``wait_open`` waits for
  ``entered``; closing waits until the element is gone, not merely started leaving.
- **``ToastProvider`` is the toast region**, not a wrapper: it renders no children,
  and ``toast.add`` before it mounts shows nothing.
- **A toast is ``role=alertdialog``** named by its title, and the titles repeat.
  :meth:`Toasts.mark` remembers the toasts already shown so :meth:`Toasts.expect_new`
  waits for one that appeared after the mark.
- **``Tag`` alone renders nothing**: the exported ``Tag`` is ``TagGroup``'s item, and
  a tag group is a ``grid`` of ``row``\\ s, not a list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from testence.engine import Capability, Target, require_capabilities
from testence.kits import _support, react_aria
from testence.kits.react_aria import (
    checkbox,
    menu,
    search_field,
    switch,
    table,
    tabs,
    tooltip,
)

#: The ``@koobiq/react-components`` range this kit is held to.
SUPPORTED = ">=0.37,<1"
#: Versions the conformance stand was built with and passed against.
VERIFIED = ("0.37.0", "0.38.0")
#: When the roles, attributes and class prefixes were last checked against the sources.
CHECKED = "2026-11-04"


def _token(name: str) -> str:
    """XPath test: the element's class list starts a class with ``name``."""
    return f'contains(concat(" ", normalize-space(@class)), " {name}")'


def _label_name(label: str, *, required: bool = False, hint: str | None = None) -> str:
    """The accessible name Koobiq's ``FormField.Label`` gives a field."""
    parts = [label]
    if hint:
        parts.append(hint)
    if required:
        parts.append("*")
    return " ".join(parts)


# -- fields ----------------------------------------------------------------------


@dataclass(frozen=True)
class TextField:
    ex: Any = field(repr=False, compare=False)
    target: Target
    title: str

    def fill(self, value: str) -> None:
        self.ex.fill(self.target, value, intent=f"type into {self.title!r}")

    def expect_value(self, value: str) -> None:
        self.ex.expect_value(self.target, value, intent=f"{self.title!r} holds {value!r}")


def text_field(
    ex: Any,
    label: str,
    *,
    required: bool = False,
    hint: str | None = None,
    within: Target | None = None,
) -> TextField:
    """A Koobiq ``Input``/``Textarea``, by the exact name its label produces.

    ``required=True`` appends Koobiq's `` *``; ``hint`` is the text of a hint placed in
    the label (an icon's ``aria-label``), which joins the name before the asterisk.
    """
    name = _label_name(label, required=required, hint=hint)
    return TextField(ex, Target("role", "textbox", name=name, within=within), name)


def number_field(
    ex: Any,
    label: str,
    *,
    required: bool = False,
    hint: str | None = None,
    within: Target | None = None,
) -> react_aria.NumberField:
    """A Koobiq ``InputNumber``: commits on Tab (see :class:`react_aria.NumberField`)."""
    return react_aria.number_field(
        ex, _label_name(label, required=required, hint=hint), within=within
    )


def search(ex: Any, label: str, *, within: Target | None = None) -> react_aria.SearchField:
    """A Koobiq ``SearchInput``: ``role=searchbox``, submitted by Enter only."""
    return search_field(ex, label, within=within)


@dataclass(frozen=True)
class Select:
    """A Koobiq ``Select``: a ``div role=button`` and a portalled ``listbox``."""

    ex: Any = field(repr=False, compare=False)
    label: str
    name: str
    trigger: Target
    list: react_aria.Listbox

    def option(self, label: str) -> Target:
        return self.list.option(label)

    def shows(self, value: str) -> Target:
        """The trigger while it shows ``value``: its name is "label value"."""
        return Target("role", "button", name=f"{self.name} {value}")

    def open(self) -> None:
        self.ex.click(self.trigger, intent=f"open the select {self.label!r}")
        self.ex.expect_visible(self.list.target, intent=f"the options of {self.label!r} are shown")

    def choose(self, value: str) -> None:
        self.open()
        self.ex.click(self.option(value), intent=f"choose {value!r} in {self.label!r}")
        self.ex.expect_hidden(self.list.target, intent=f"the options of {self.label!r} closed")
        self.expect_value(value)

    def expect_value(self, value: str) -> None:
        self.ex.expect_visible(self.shows(value), intent=f"{self.label!r} shows {value!r}")


def select(ex: Any, label: str, *, required: bool = False) -> Select:
    """The Koobiq ``Select`` whose label reads ``label`` (without the " *")."""
    lit = _support.xpath_literal(label)
    # The label text, with the required asterisk and the non-breaking space before
    # it removed: translate() maps U+00A0 to a space and deletes "*".
    text = 'normalize-space(translate(., "\u00a0*", " "))'
    trigger = Target(
        "css",
        f'xpath=//*[@data-slot="form-field"][*[@data-slot="form-field-label"][{text}={lit}]]'
        '//*[@data-slot="select-value"]',
    )
    name = _label_name(label, required=required)
    return Select(ex, label, name, trigger, react_aria.listbox(ex, name))


# -- overlays --------------------------------------------------------------------

_HEADER = _token("kbq-dialog-header-")
_DIALOG_STATE = """(xpath) => {
    const found = document.evaluate(xpath, document, null,
        XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
    const dialogs = [];
    for (let i = 0; i < found.snapshotLength; i++) dialogs.push(found.snapshotItem(i));
    return dialogs.map(d => {
        const holder = d.closest('[data-transition]');
        return holder ? holder.getAttribute('data-transition') : 'no-transition';
    });
}"""
_DIALOG_ENTERED = f"""(xpath) => {{
    const states = ({_DIALOG_STATE})(xpath);
    return states.length === 1 && (states[0] === 'entered' || states[0] === 'no-transition');
}}"""


@dataclass(frozen=True)
class Dialog:
    """A Koobiq ``Modal`` or ``SidePanel`` dialog, found by its title."""

    ex: Any = field(repr=False, compare=False)
    title: str
    target: Target
    kind: str = "dialog"

    @property
    def _xpath(self) -> str:
        return self.target.value.removeprefix("xpath=")

    def button(self, name: str) -> Target:
        return react_aria.button(name, within=self.target)

    def field(self, label: str, *, required: bool = False, hint: str | None = None) -> TextField:
        return text_field(self.ex, label, required=required, hint=hint, within=self.target)

    def number_field(
        self, label: str, *, required: bool = False, hint: str | None = None
    ) -> react_aria.NumberField:
        return number_field(self.ex, label, required=required, hint=hint, within=self.target)

    @property
    def close_button(self) -> Target:
        """The header's close button. Its name is translated ("Close", "Закрыть")."""
        return Target("css", '[class*="kbq-dialog-closeButton-"] button', nth=0, within=self.target)

    def wait_open(self) -> None:
        """Wait until the dialog has finished its entrance (``data-transition=entered``).

        A side panel slides in for 300 ms: until then it is visible but moving, so a
        coordinate, a screenshot or a ``fast`` click taken during the slide is off.
        """
        self.ex.expect_visible(self.target, intent=f"the {self.kind} {self.title!r} is shown")
        _support.wait_until(
            self.ex,
            f"the {self.kind} {self.title!r} finished opening",
            _DIALOG_ENTERED,
            self._xpath,
            describe=_DIALOG_STATE,
            target=self.target,
        )

    def wait_closed(self) -> None:
        """Wait until the dialog is gone: it stays mounted while it animates out."""
        self.ex.expect_hidden(self.target, intent=f"the {self.kind} {self.title!r} is gone")

    def close(self) -> None:
        self.ex.click(self.close_button, intent=f"close the {self.kind} {self.title!r}")
        self.wait_closed()

    def press(self, name: str, *, closes: bool = True) -> None:
        """Press the button ``name`` in the dialog; by default it must then close."""
        self.ex.click(self.button(name), intent=f"press {name!r} in {self.title!r}")
        if closes:
            self.wait_closed()


def _dialog_xpath(title: str, container: str | None = None) -> str:
    header = f"[.//*[{_HEADER}][normalize-space(.)={_support.xpath_literal(title)}]]"
    if container:
        return f"xpath=//*[{_token(container)}]//*[@role='dialog']{header}"
    return f"xpath=//*[@role='dialog']{header}"


def dialog(ex: Any, title: str) -> Dialog:
    """Any Koobiq dialog (``Modal``, ``SidePanel``) whose header reads ``title``."""
    return Dialog(ex, title, Target("css", _dialog_xpath(title)))


def side_panel(ex: Any, title: str) -> Dialog:
    """A Koobiq ``SidePanel`` whose header reads ``title``."""
    return Dialog(ex, title, Target("css", _dialog_xpath(title, "kbq-sidepanel-")), "side panel")


@dataclass(frozen=True)
class Confirm:
    """A confirmation (a ``Modal`` with a title and action buttons)."""

    dialog: Dialog

    @property
    def target(self) -> Target:
        return self.dialog.target

    def accept(self, action: str) -> None:
        """Press the action (it carries the verb: "Delete", "Publish") and see it close."""
        self.dialog.ex.expect_visible(
            self.target, intent=f"the confirmation {self.dialog.title!r} is shown"
        )
        self.dialog.press(action)

    def cancel(self, name: str = "Cancel") -> None:
        self.dialog.press(name)


def confirm(ex: Any, title: str) -> Confirm:
    return Confirm(dialog(ex, title))


# -- toasts ----------------------------------------------------------------------

_TOASTS = """() => [...document.querySelectorAll('[role="alertdialog"]')].map(t => {
    const title = document.getElementById(t.getAttribute('aria-labelledby') || '');
    const caption = document.getElementById(t.getAttribute('aria-describedby') || '');
    return {id: t.getAttribute('aria-labelledby') || '',
            title: title ? title.textContent.trim() : '',
            caption: caption ? caption.textContent.trim() : '',
            status: t.getAttribute('data-status') || '',
            transition: t.getAttribute('data-transition') || ''};
})"""
_NEW_TOAST = f"""(seen, title, status) => ({_TOASTS})().some(t =>
    !seen.includes(t.id) && t.title === title && (!status || t.status === status)
    && t.transition !== 'exiting')"""
_NEW_TOAST_ID = f"""(seen, title, status) => {{
    const t = ({_TOASTS})().find(t => !seen.includes(t.id) && t.title === title
        && (!status || t.status === status) && t.transition !== 'exiting');
    if (!t) return null;
    const el = [...document.querySelectorAll('[role="alertdialog"]')]
        .find(e => e.getAttribute('aria-labelledby') === t.id);
    return {{id: t.id, caption: el.getAttribute('aria-describedby') || ''}};
}}"""
_ANY_NEW_TOAST = f"(seen) => ({_TOASTS})().some(t => !seen.includes(t.id))"


@dataclass(frozen=True)
class ToastMark:
    """The toasts on screen when the mark was taken (by their title element ids)."""

    seen: tuple[str, ...]


@dataclass(frozen=True)
class Toast:
    ex: Any = field(repr=False, compare=False)
    title: str
    target: Target
    #: The caption (``aria-describedby`` of the toast).
    caption: Target

    @property
    def close_button(self) -> Target:
        """The toast's close button. Its name is translated ("Close", "Закрыть")."""
        return Target("css", '[class*="kbq-toast-closeIcon-"]', within=self.target)

    def expect_caption(self, text: str) -> None:
        self.ex.expect_text(self.caption, text, intent=f"the toast {self.title!r} says {text!r}")

    def dismiss(self) -> None:
        """Close the toast and wait until it is gone (it animates out for 300 ms)."""
        self.ex.click(self.close_button, intent=f"dismiss the toast {self.title!r}")
        self.ex.expect_hidden(self.target, intent=f"the toast {self.title!r} is gone")


@dataclass(frozen=True)
class Toasts:
    ex: Any = field(repr=False, compare=False)

    def read(self) -> list[dict[str, str]]:
        """Every toast on screen: ``{id, title, caption, status, transition}``."""
        return list(_support.read(self.ex, "read the toasts on screen", _TOASTS))

    def mark(self) -> ToastMark:
        """Remember what is on screen now; take it *before* the action."""
        return ToastMark(tuple(toast["id"] for toast in self.read()))

    def expect_new(self, mark: ToastMark, title: str, *, status: str | None = None) -> Toast:
        """Wait for a toast titled ``title`` that appeared after ``mark``.

        ``status`` is Koobiq's ``data-status``: ``success``, ``error``, ``warning``,
        ``info``. A toast already on screen at the mark, or one leaving, never counts.
        """
        what = f"a new toast {title!r}" + (f" ({status})" if status else "")
        _support.wait_until(
            self.ex,
            f"{what} appears",
            _NEW_TOAST,
            list(mark.seen),
            title,
            status,
            describe=_TOASTS,
        )
        found = _support.read(
            self.ex, f"find {what}", _NEW_TOAST_ID, list(mark.seen), title, status
        )
        if not found:  # it left between the wait and the read: report, do not retry
            raise AssertionError(f"{what} appeared and was gone before it could be read")
        labelled = _support.css_string(str(found["id"]))
        target = Target("css", f'[role="alertdialog"][aria-labelledby={labelled}]')
        caption = Target("css", f"[id={_support.css_string(str(found['caption']))}]")
        return Toast(self.ex, title, target, caption)

    def expect_no_new(self, mark: ToastMark, *, within_ms: int = 1_500) -> None:
        """No toast appears for ``within_ms``. A negative costs its whole budget."""
        with self.ex.step(f"no new toast within {within_ms} ms", check=True):
            require_capabilities(self.ex.engine, "kit wait", Capability.JAVASCRIPT)
            if self.ex.engine.wait_for_predicate_js(
                _support.call(_ANY_NEW_TOAST, list(mark.seen)), within_ms
            ):
                shown = self.ex.engine.eval_js(_support.call(_TOASTS))
                raise AssertionError(f"a toast appeared: {shown}")


def toasts(ex: Any) -> Toasts:
    return Toasts(ex)


# -- badges and tags ---------------------------------------------------------------

_BADGE = """(xpath) => {
    const el = document.evaluate(xpath, document, null,
        XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
    return el ? {text: el.textContent.trim(), variant: el.getAttribute('data-variant'),
                 color: el.style.color, shown: getComputedStyle(el).color} : null;
}"""
_BADGE_COLOR = (
    f"(xpath, color) => {{ const b = ({_BADGE})(xpath); return !!b && b.color === color; }}"
)


@dataclass(frozen=True)
class Badge:
    ex: Any = field(repr=False, compare=False)
    text: str
    target: Target

    def read(self) -> dict[str, str] | None:
        """``{text, variant, color, shown}``: ``color`` is the inline style the product
        set, ``shown`` the computed colour."""
        result = _support.read(
            self.ex,
            f"read the badge {self.text!r}",
            _BADGE,
            self.target.value.removeprefix("xpath="),
        )
        return dict(result) if result else None

    def expect_variant(self, variant: str) -> None:
        self.ex.expect_attribute(
            self.target, "data-variant", variant, intent=f"the badge {self.text!r} is {variant}"
        )

    def expect_color(self, color: str) -> None:
        """The inline ``style.color`` (as the browser normalizes it: ``rgb(r, g, b)``)."""
        _support.wait_until(
            self.ex,
            f"the badge {self.text!r} is coloured {color}",
            _BADGE_COLOR,
            self.target.value.removeprefix("xpath="),
            color,
            describe=_BADGE,
            target=self.target,
        )


def badge(ex: Any, text: str) -> Badge:
    """A Koobiq ``Badge`` (``span[data-variant]``) reading ``text``; the first one."""
    xpath = (
        f"xpath=//*[{_token('kbq-badge-')}][@data-variant]"
        f"[normalize-space(.)={_support.xpath_literal(text)}]"
    )
    return Badge(ex, text, Target("css", xpath, nth=0))


@dataclass(frozen=True)
class TagGroup:
    ex: Any = field(repr=False, compare=False)
    target: Target
    title: str

    def tag(self, label: str) -> Target:
        return Target("role", "row", name=label, within=self.target)

    def remove(self, label: str) -> None:
        """Press the tag's remove button (its name is translated) and see it go."""
        remove = Target("role", "button", within=self.tag(label))
        self.ex.click(remove, intent=f"remove the tag {label!r} from {self.title!r}")
        self.ex.expect_hidden(self.tag(label), intent=f"the tag {label!r} is gone")

    def expect_tags(self, count: int) -> None:
        self.ex.expect_count(
            Target("role", "row", within=self.target),
            count,
            intent=f"{self.title!r} has {count} tags",
        )


def tag_group(ex: Any, name: str) -> TagGroup:
    """A Koobiq ``TagGroup``: a ``grid`` whose tags are ``row``\\ s."""
    return TagGroup(ex, Target("role", "grid", name=name), name)


__all__ = [
    "CHECKED",
    "SUPPORTED",
    "VERIFIED",
    "Badge",
    "Confirm",
    "Dialog",
    "Select",
    "TagGroup",
    "TextField",
    "Toast",
    "ToastMark",
    "Toasts",
    "badge",
    "checkbox",
    "confirm",
    "dialog",
    "menu",
    "number_field",
    "search",
    "select",
    "side_panel",
    "switch",
    "table",
    "tabs",
    "tag_group",
    "text_field",
    "toasts",
    "tooltip",
]
