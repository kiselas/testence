"""Component kits: addresses and actions for UI libraries, composed from ``ex`` steps.

``from testence.kits import koobiq`` and then ``koobiq.select(ex, "Mode").choose("Fast")``.
A kit knows what a component library renders (roles, names, attributes, the traps in
its behaviour); a project adapter knows its own routes, screens and data. See
``docs/en/kits.md``.

- :mod:`testence.kits.react_aria`: roles and behaviour shared by react-aria systems.
- :mod:`testence.kits.koobiq`: Koobiq (``@koobiq/react-components``).
- :mod:`testence.kits.react_select`: ``react-select``, single and ``isMulti``.
- :mod:`testence.kits.xyflow`: ``@xyflow/react`` (React Flow) nodes.
- :mod:`testence.kits.codemirror`: CodeMirror 6 editors.
"""

from __future__ import annotations

from testence.kits import codemirror, koobiq, react_aria, react_select, xyflow

__all__ = ["codemirror", "koobiq", "react_aria", "react_select", "xyflow"]
