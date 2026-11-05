"""Recognize kit components on a page, for ``testence explore`` and ``testence_snapshot``.

One read of the DOM finds the components the kits know by their signs (react-select's
``__control`` class, Koobiq's ``data-slot`` and ``kbq-`` class prefixes, ARIA roles,
``.react-flow__node``) and returns, for each, the line of kit code that addresses it:
``koobiq.select(ex, "Mode")``, ``react_select.multi(ex, "Targets")``. Recognition is
read-only and bounded; it is a hint for authoring, not proof of anything.
"""

from __future__ import annotations

import json
from typing import Any

#: The most components one snapshot lists, and the most of one kind: a page with a
#: hundred checkboxes must not crowd out its dialog.
LIMIT = 40
PER_KIND = 8

_SCRIPT = r"""(limit, perKind) => {
    const out = [], kinds = {};
    const squash = t => (t || '').replace(/\s+/g, ' ').trim().slice(0, 200);
    const shown = el => el.getClientRects().length > 0;
    const text = el => squash(el ? el.textContent : '');
    const byIds = ids => squash((ids || '').split(/\s+/).filter(Boolean)
        .map(id => document.getElementById(id)).filter(Boolean).map(e => e.textContent).join(' '));
    const accName = el => squash(el.getAttribute('aria-label')) || byIds(el.getAttribute('aria-labelledby'));
    const kbq = (el, part) => [...el.classList].some(c => c.startsWith('kbq-' + part + '-')
        || c === 'kbq-' + part);
    const add = item => {
        kinds[item.kind] = (kinds[item.kind] || 0) + 1;
        if (out.length < limit && kinds[item.kind] <= perKind) out.push(item);
    };
    // react-aria leaves these on what it renders; a bare ARIA role is not react-aria.
    const ARIA = '[data-rac],[data-collection],[data-react-aria-pressable],[id^="react-aria"]';
    const reactAria = el => el.matches(ARIA) || Boolean(el.querySelector(ARIA));
    // An unnamed component gets a Target by position: its index among all matches.
    const position = (el, css) => ({css, nth: [...document.querySelectorAll(css)].indexOf(el)});
    const fieldLabel = field => {
        const label = field.querySelector('[data-slot="form-field-label"]');
        if (!label) return null;
        const required = Boolean(label.querySelector('sup'));
        const clone = label.cloneNode(true);
        clone.querySelectorAll('sup').forEach(s => s.remove());
        const hint = [...clone.querySelectorAll('[aria-label]')].map(e => squash(e.getAttribute('aria-label')))
            .filter(Boolean).join(' ');
        clone.querySelectorAll('[aria-label]').forEach(e => e.remove());
        return {label: text(clone), required, hint: hint || null};
    };

    // react-select: a combobox input inside "<prefix>__control".
    for (const input of document.querySelectorAll('input[role="combobox"]')) {
        let control = input, prefix = null;
        while (control && control !== document.body) {
            const cls = [...control.classList].find(c => c.endsWith('__control'));
            if (cls) { prefix = cls.slice(0, -'__control'.length); break; }
            control = control.parentElement;
        }
        if (!prefix || !shown(control)) continue;
        const multi = Boolean(control.querySelector('.' + prefix + '__value-container--is-multi, .'
            + prefix + '__multi-value'));
        let name = accName(input);
        if (!name && input.labels && input.labels.length) name = text(input.labels[0]);
        add({kind: multi ? 'react_select.multi' : 'react_select.single', name,
             prefix, input_id: name ? null : (input.id || null),
             ...(name || input.id ? {} : position(control, '.' + prefix + '__control'))});
    }

    // Koobiq form fields: select, number, text; the label says required and hint.
    for (const field of document.querySelectorAll('[data-slot="form-field"]')) {
        if (!shown(field)) continue;
        const label = fieldLabel(field);
        if (!label || !label.label) continue;
        if (field.querySelector('[data-slot="select-value"]')) {
            add({kind: 'koobiq.select', name: label.label, required: label.required});
        } else if (field.querySelector('input[type="search"]')) {
            add({kind: 'koobiq.search', name: label.label});
        } else if (field.querySelector('input[inputmode="numeric"], input[inputmode="decimal"]')
                   && field.querySelector('[aria-controls]')) {
            add({kind: 'koobiq.number_field', name: label.label, required: label.required, hint: label.hint});
        } else if (field.querySelector('input:not([type="checkbox"]):not([type="radio"]), textarea')
                   && (label.required || label.hint)) {
            add({kind: 'koobiq.text_field', name: label.label, required: label.required, hint: label.hint});
        }
    }

    // Hidden-input checkboxes and switches (react-aria): the label is what to click.
    for (const input of document.querySelectorAll('label input[type="checkbox"]')) {
        const label = input.closest('label');
        if (!shown(label) || input.closest('[role="grid"], table')) continue;
        // Only a hidden input needs the kit: a plain, visible checkbox is clicked as is.
        let hidden = false;
        for (let el = input; el && el !== label; el = el.parentElement) {
            const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
            if (r.width <= 1 || r.height <= 1 || cs.opacity === '0'
                || (cs.clipPath && cs.clipPath !== 'none') || (cs.clip && cs.clip !== 'auto')) hidden = true;
        }
        if (!hidden) continue;
        const name = squash(label.textContent);
        if (!name) continue;
        const koobiq = kbq(label, 'checkbox') || kbq(label, 'toggle');
        if (!koobiq && !reactAria(label)) continue;
        const kind = input.getAttribute('role') === 'switch' ? 'switch' : 'checkbox';
        add({kind: (koobiq ? 'koobiq.' : 'react_aria.') + kind, name});
    }

    // Dialogs: named ones by role; Koobiq's unnamed ones by their header.
    for (const dialog of document.querySelectorAll('[role="dialog"], [role="alertdialog"]')) {
        if (dialog.getAttribute('role') === 'alertdialog' && kbq(dialog, 'toast')) continue;
        const name = accName(dialog);
        const header = dialog.querySelector('[class*="kbq-dialog-header-"]');
        const holder = dialog.closest('[data-transition]');
        const panel = holder && kbq(holder, 'sidepanel');
        if (header && text(header)) {
            add({kind: panel ? 'koobiq.side_panel' : 'koobiq.dialog', name: text(header),
                 transition: holder ? holder.getAttribute('data-transition') : null});
        } else {
            add({kind: 'dialog', name, role: dialog.getAttribute('role')});
        }
    }

    const toasts = [...document.querySelectorAll('[role="alertdialog"]')].filter(t => kbq(t, 'toast'));
    if (toasts.length) {
        add({kind: 'koobiq.toasts', name: '', titles: toasts.map(t =>
            byIds(t.getAttribute('aria-labelledby'))).slice(0, 10)});
    }

    // Grids: the table kits address role=grid, so a plain <table> is not one of them.
    // Koobiq tag groups are grids of rows too.
    for (const grid of document.querySelectorAll('[role="grid"]')) {
        if (!shown(grid) || grid.parentElement.closest('[role="grid"]')) continue;
        const name = accName(grid);
        const at = name ? {} : position(grid, '[role="grid"]');
        if (kbq(grid, 'taggroup')) { add({kind: 'koobiq.tag_group', name, ...at}); continue; }
        if (!kbq(grid, 'table') && !reactAria(grid)) continue;
        const rows = grid.querySelectorAll('[role="rowheader"]').length;
        add({kind: kbq(grid, 'table') ? 'koobiq.table' : 'react_aria.table', name, rows, ...at});
    }

    for (const tablist of document.querySelectorAll('[role="tablist"]')) {
        if (!shown(tablist)) continue;
        const koobiq = Boolean(tablist.closest('[class*="kbq-tabs"]'))
            || [...tablist.querySelectorAll('*')].some(e => kbq(e, 'tabs'));
        if (!koobiq && !reactAria(tablist)) continue;
        const name = accName(tablist);
        add({kind: koobiq ? 'koobiq.tabs' : 'react_aria.tabs', name,
             ...(name ? {} : position(tablist, '[role="tablist"]'))});
    }

    for (const menu of document.querySelectorAll('[role="menu"]')) {
        if (!shown(menu) || !reactAria(menu)) continue;
        const name = accName(menu);
        add({kind: 'react_aria.menu', name, ...(name ? {} : position(menu, '[role="menu"]'))});
    }

    // Open lists that are not react-select's own menu list.
    for (const list of document.querySelectorAll('[role="listbox"]')) {
        if (!shown(list) || [...list.classList].some(c => c.endsWith('__menu-list'))) continue;
        if (!reactAria(list)) continue;
        const name = accName(list);
        add({kind: 'react_aria.listbox', name, ...(name ? {} : position(list, '[role="listbox"]'))});
    }

    for (const node of document.querySelectorAll('.react-flow__node[data-id]')) {
        const type = [...node.classList].find(c => c.startsWith('react-flow__node-'));
        add({kind: 'xyflow.node', name: node.getAttribute('data-id'),
             node_kind: type ? type.slice('react-flow__node-'.length) : null,
             text: squash(node.innerText).slice(0, 80)});
    }
    return out;
}"""

_MODULES = {
    "koobiq": "from testence.kits import koobiq",
    "react_aria": "from testence.kits import react_aria",
    "react_select": "from testence.kits import react_select",
    "xyflow": "from testence.kits import xyflow",
}
_KINDS = frozenset(
    {
        "react_select.multi",
        "react_select.single",
        "koobiq.select",
        "koobiq.search",
        "koobiq.number_field",
        "koobiq.text_field",
        "koobiq.checkbox",
        "koobiq.switch",
        "react_aria.checkbox",
        "react_aria.switch",
        "koobiq.side_panel",
        "koobiq.dialog",
        "dialog",
        "koobiq.toasts",
        "koobiq.tag_group",
        "koobiq.table",
        "react_aria.table",
        "koobiq.tabs",
        "react_aria.tabs",
        "react_aria.menu",
        "react_aria.listbox",
        "xyflow.node",
    }
)


def script() -> str:
    """The recognizer, as an expression the engine evaluates."""
    return f"({_SCRIPT})({LIMIT}, {PER_KIND})"


def _literal(value: str) -> str:
    # A JSON string is a valid Python string literal; keep the page's own characters.
    return json.dumps(value, ensure_ascii=False)


def clean(raw: Any) -> list[dict[str, Any]]:
    """Keep only well-formed entries: the page, or a fake engine, decides nothing else."""
    if not isinstance(raw, list):
        return []
    found: list[dict[str, Any]] = []
    for item in raw[:LIMIT]:
        if not isinstance(item, dict) or item.get("kind") not in _KINDS:
            continue
        if not isinstance(item.get("name"), str):
            continue
        found.append({k: v for k, v in item.items() if isinstance(k, str)})
    return found


def python(item: dict[str, Any]) -> str:
    """The kit line that addresses a recognized component."""
    kind, name = item["kind"], item["name"]
    if kind == "dialog":
        role = item.get("role") or "dialog"
        if name:
            return f"Target('role', {role!r}, name={_literal(name)})"
        return f"Target('role', {role!r})"
    if kind == "koobiq.toasts":
        return "koobiq.toasts(ex)"
    if not name and isinstance(item.get("css"), str) and type(item.get("nth")) is int:
        # The kit factories take a name and this component has none: address it by
        # position, usable now, to be replaced once the product names it.
        return f"Target('css', {_literal(item['css'])}, nth={item['nth']})"
    if not name and not item.get("input_id"):
        raise ValueError(f"{kind} without a name or a position")
    args = [_literal(name)] if name else []
    if kind.startswith("react_select."):
        if not name and item.get("input_id"):
            args = [_literal(""), f"input_id={_literal(str(item['input_id']))}"]
        if item.get("prefix") and item["prefix"] != "react-select":
            args.append(f"prefix={_literal(str(item['prefix']))}")
    if kind in ("koobiq.select", "koobiq.text_field", "koobiq.number_field"):
        if item.get("hint") and kind != "koobiq.select":
            args.append(f"hint={_literal(str(item['hint']))}")
        if item.get("required"):
            args.append("required=True")
    if kind == "xyflow.node" and item.get("node_kind"):
        args.append(f"kind={_literal(str(item['node_kind']))}")
    return f"{kind}(ex{''.join(', ' + a for a in args)})"


def describe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add the kit line and the import it needs to each (already redacted) entry.

    An entry no runnable line can be written for (unnamed, without a position) is
    dropped rather than printed as a call that would raise.
    """
    kept: list[dict[str, Any]] = []
    for item in items:
        try:
            item["python"] = python(item)
        except ValueError:
            continue
        if item["python"].startswith("Target("):
            item["import"] = "from testence.engine import Target"
            if not item["name"] and item["kind"] != "dialog":
                item["note"] = "no accessible name: addressed by position; name it in the product"
        else:
            item["import"] = _MODULES[item["kind"].split(".", 1)[0]]
        kept.append(item)
    items[:] = kept
    return items


__all__ = ["LIMIT", "clean", "describe", "python", "script"]
