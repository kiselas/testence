"""CodeMirror 6 editors: a JSON schema, a template, any code a product edits in place.

An editor is ``.cm-editor`` with a ``contenteditable`` ``.cm-content`` (``role=textbox``)
inside; it has no ``<input>`` and no ``value``. Traps carried here:

- **What is drawn is not the document.** CodeMirror draws only the lines in view and
  may wrap them; reading the ``.cm-line`` elements of a long document misses lines.
  :meth:`Editor.text` reads the document from the editor's own view, which CodeMirror
  keeps on the content element (``cmTile`` since 6.4x, ``cmView`` before), and falls
  back to the drawn lines only when neither is there.
- **Typing is editing.** Each key goes through the editor's input handlers: an opening
  bracket gets its closing one, Enter indents. :meth:`Editor.set_text` replaces the
  whole document in one input (``fill``), as a paste would; :meth:`Editor.type`
  types key by key at the caret, for a case about what the editor does with keys.
- **There is no change event to wait for.** :meth:`Editor.expect_text` waits, frame by
  frame in the page, until the document equals the text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from testence.engine import Capability, Target, require_capabilities

#: The document of the editor ``element`` is in (``.cm-editor`` or inside it).
_DOC_JS = """(element) => {
  const editor = element.closest('.cm-editor') || element.querySelector('.cm-editor') || element;
  const content = editor.querySelector('.cm-content');
  const holder = content && (content.cmTile || content.cmView);
  const view = holder && holder.view;
  if (view && view.state && view.state.doc) return {text: view.state.doc.toString(), whole: true};
  const lines = [...editor.querySelectorAll('.cm-line')].map((line) => line.textContent);
  return {text: lines.join('\\n'), whole: false};
}"""

_EXPECT_JS = (
    """(element, [expected, timeout]) => new Promise((resolve) => {
  const read = %s;
  const started = performance.now();
  const frame = () => {
    const seen = read(element);
    if (seen.text === expected) return resolve({ok: true, ...seen});
    if (performance.now() - started > timeout) return resolve({ok: false, ...seen});
    requestAnimationFrame(frame);
  };
  frame();
})"""
    % _DOC_JS
)


@dataclass(frozen=True)
class Editor:
    ex: Any = field(repr=False, compare=False)
    name: str
    target: Target

    @property
    def content(self) -> Target:
        """The editable area, the target of typing and of ``fill``."""
        return Target("css", ".cm-content", within=self.target)

    def text(self) -> str:
        """The whole document (see the module's notes on what is drawn)."""
        seen = self.ex.read_js(f"read the document of {self.name}", _DOC_JS, target=self.target)
        return str(seen["text"])

    def set_text(self, text: str) -> None:
        """Replace the document with ``text`` in one input, then check it holds it."""
        self.ex.fill(self.content, text, intent=f"replace the document of {self.name}")
        self.expect_text(text)

    def type(self, text: str) -> None:
        """Type ``text`` key by key at the caret; the editor's input handlers apply."""
        self.ex.type(self.content, text, intent=f"type into {self.name}")

    def expect_text(self, text: str, *, timeout_ms: int | None = None) -> None:
        """The document is exactly ``text`` (no whitespace folding)."""
        budget = timeout_ms if timeout_ms is not None else self.ex.engine.timeout_ms
        with self.ex.step(
            f"the document of {self.name} is the expected text", self.target, check=True
        ):
            require_capabilities(self.ex.engine, "codemirror expect", Capability.JAVASCRIPT)
            seen = self.ex.engine.evaluate_on(self.target, _EXPECT_JS, [text, budget])
            if not seen.get("ok"):
                shown = str(seen.get("text", ""))
                raise AssertionError(
                    f"the document of {self.name} never became the expected text; "
                    f"it holds {shown[:300]!r}{'...' if len(shown) > 300 else ''}"
                )


def editor(
    ex: Any, *, within: Target | None = None, nth: int | None = None, name: str = "the editor"
) -> Editor:
    """The CodeMirror editor inside ``within`` (a panel, a form field); ``nth`` picks
    one of several. ``name`` is how steps call it ("the schema editor")."""
    return Editor(ex, name, Target("css", ".cm-editor", nth=nth, within=within))


__all__ = ["Editor", "editor"]
