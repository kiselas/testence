"""@xyflow/react (React Flow 12): nodes of a flow graph.

A node is ``.react-flow__node-<type>[data-id=<id>]`` (``role=group``,
``aria-roledescription=node``), with no accessible name, so it is addressed by the
id the product gave it. Traps carried here:

- **A node is drawn hidden first.** React Flow renders it with ``visibility: hidden``
  until it has measured it; a click before that lands on nothing. Every action here
  waits for the node to be visible first.
- **A single click only selects a node.** Products open a node's editor on
  ``onNodeDoubleClick``; :meth:`Node.open` double-clicks it (``ex.double_click``).
- **A node's menu is portalled and unnamed by the node.** The trigger is the node's
  button with ``aria-haspopup``; the open menu is the page's only ``role=menu``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from testence.engine import Target
from testence.kits import _support, react_aria


@dataclass(frozen=True)
class Node:
    ex: Any = field(repr=False, compare=False)
    id: str
    kind: str | None
    target: Target

    @property
    def _css(self) -> str:
        return self.target.value

    def wait_drawn(self) -> None:
        self.ex.expect_visible(self.target, intent=f"the node {self.id!r} is drawn")

    def click(self) -> None:
        self.wait_drawn()
        self.ex.click(self.target, intent=f"select the node {self.id!r}")

    def expect_selected(self, selected: bool = True) -> None:
        _support.wait_until(
            self.ex,
            f"the node {self.id!r} is {'selected' if selected else 'not selected'}",
            "(css, on) => { const n = document.querySelector(css); "
            "return !!n && n.classList.contains('selected') === on; }",
            self._css,
            selected,
            describe="(css) => { const n = document.querySelector(css); "
            "return n ? n.className : null; }",
            target=self.target,
        )

    def open(self) -> None:
        """Double-click the node (a single click only selects it)."""
        self.wait_drawn()
        self.ex.double_click(self.target, intent=f"double-click the node {self.id!r}")

    def menu(self, trigger_name: str | None = None) -> react_aria.Menu:
        """The node's menu: the button ``trigger_name``, or its ``aria-haspopup`` button."""
        if trigger_name:
            return react_aria.menu(self.ex, trigger_name, within=self.target)
        trigger = Target("css", '[aria-haspopup="true"]', nth=0, within=self.target)
        return react_aria.menu_of(self.ex, trigger, title=f"menu of the node {self.id!r}")

    def action(self, label: str, *, trigger_name: str | None = None) -> None:
        """Choose ``label`` in the node's menu."""
        self.wait_drawn()
        self.menu(trigger_name).choose(label)


def node(ex: Any, node_id: str, *, kind: str | None = None) -> Node:
    """The node ``node_id``; ``kind`` is its ``type`` (``.react-flow__node-<kind>``)."""
    cls = f".react-flow__node-{kind}" if kind else ".react-flow__node"
    return Node(ex, node_id, kind, Target("css", f"{cls}[data-id={_support.css_string(node_id)}]"))


def nodes(kind: str | None = None) -> Target:
    """Every node (of ``kind``), for ``ex.expect_count``."""
    return Target("css", f".react-flow__node-{kind}" if kind else ".react-flow__node")


__all__ = ["Node", "node", "nodes"]
