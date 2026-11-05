"""Structural masking of CSV, XML and HTML attachments (stage 6, T08).

Text rules find a secret by its spelling (``password=...``, a JWT, a known value). A
file whose structure names the secret does not spell it: a CSV column headed
``token``, ``<password>hunter2</password>``, ``<input type="password" value="...">``.
These functions find the secret by that structure and replace only it. Every byte
outside the replaced values is kept, so the file still parses and diffs like the
original. ``redact_document_text`` runs them first and the ordinary text pass second.

Each function returns ``None`` when the document cannot be read structurally (not
well-formed, an entity declaration, no sensitive header); the caller then relies on the
text pass alone.
"""

from __future__ import annotations

import csv
import html
import io
import re
from html.parser import HTMLParser
from xml.parsers import expat

from .sanitize import (
    _NAME_SLOTS,
    _VALUE_SLOTS,
    DEFAULT_POLICY,
    REDACTED,
    RedactionPolicy,
    is_sensitive_key,
)

#: How REDACTED is written inside markup: ``<`` and ``>`` are escaped.
_MARKUP_REDACTED = html.escape(REDACTED)

_HTML_SUFFIXES = frozenset({".html", ".htm", ".xhtml", ".xht"})
# ``.xsl`` is what ``mimetypes`` returns for ``application/xml``.
_XML_SUFFIXES = frozenset({".xml", ".xsl", ".svg"})
_CSV_SUFFIXES = frozenset({".csv", ".tsv"})
STRUCTURED_SUFFIXES = _HTML_SUFFIXES | _XML_SUFFIXES | _CSV_SUFFIXES

_SECRET_AUTOCOMPLETE = frozenset({"one-time-code", "current-password", "new-password"})
_SECRET_INPUT_TYPES = frozenset({"password", "hidden"})


def redact_structured(
    text: str, suffix: str, policy: RedactionPolicy = DEFAULT_POLICY
) -> str | None:
    """``text`` with the values its structure marks as secret replaced, or ``None``."""
    suffix = suffix.lower()
    if suffix in _HTML_SUFFIXES:
        return _redact_html(text, policy)
    if suffix in _XML_SUFFIXES:
        return _redact_xml(text, policy)
    if suffix in _CSV_SUFFIXES:
        return _redact_csv(text, policy, "\t" if suffix == ".tsv" else None)
    return None


def _apply(text: str, edits: list[tuple[int, int, str]]) -> str:
    """Replace the non-overlapping ``(start, end, replacement)`` spans, last first."""
    for start, end, replacement in sorted(edits, reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


# -- HTML ---------------------------------------------------------------------------


def _attribute_pattern(name: str) -> re.Pattern[str]:
    """``name="value"``, ``name='value'`` or ``name=value`` inside one tag's raw text.

    The lookbehind keeps ``value`` from matching inside ``data-value`` or ``xlink:value``.
    """
    return re.compile(
        rf"(?is)(?<![\w:.-])({re.escape(name)}\s*=\s*)(\"[^\"]*\"|'[^']*'|[^\s>\"'=`]+)"
    )


def _mask_attribute(tag: str, name: str) -> str:
    """The raw ``tag`` with a non-empty attribute ``name`` replaced; quotes are kept."""

    def replace(match: re.Match[str]) -> str:
        raw = match.group(2)
        quote = raw[0] if raw[:1] in ('"', "'") else ""
        inner = raw[1:-1] if quote else raw
        if not inner.strip() or inner == _MARKUP_REDACTED:
            return match.group(0)
        return f"{match.group(1)}{quote}{_MARKUP_REDACTED}{quote}"

    return _attribute_pattern(name).sub(replace, tag)


class _HtmlSecrets(HTMLParser):
    """Collects edits for secret form fields without rewriting anything else."""

    def __init__(self, text: str, policy: RedactionPolicy) -> None:
        super().__init__(convert_charrefs=False)
        self.text = text
        self.policy = policy
        self.edits: list[tuple[int, int, str]] = []
        self._line_starts = [0]
        for match in re.finditer("\n", text):
            self._line_starts.append(match.end())
        self._secret_textarea: int | None = None

    def _offset(self) -> int:
        line, column = self.getpos()
        return self._line_starts[line - 1] + column

    def _is_secret_field(self, attrs: dict[str, str]) -> bool:
        if attrs.get("type", "").strip().lower() in _SECRET_INPUT_TYPES:
            return True
        if attrs.get("autocomplete", "").strip().lower() in _SECRET_AUTOCOMPLETE:
            return True
        return any(
            is_sensitive_key(attrs[name], self.policy) for name in ("name", "id") if attrs.get(name)
        )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        raw = self.get_starttag_text() or ""
        start = self._offset()
        if not raw or self.text[start : start + len(raw)] != raw:
            return  # the parser and the text disagree: leave this tag to the text pass
        fields = {name.lower(): value or "" for name, value in attrs}
        masked = raw
        if tag == "input" and self._is_secret_field(fields):
            masked = _mask_attribute(raw, "value")
        elif tag == "meta" and is_sensitive_key(fields.get("name", ""), self.policy):
            # ``<meta name="csrf-token" content="...">``
            masked = _mask_attribute(raw, "content")
        elif tag == "textarea" and self._is_secret_field(fields):
            self._secret_textarea = start + len(raw)
        if masked != raw:
            self.edits.append((start, start + len(raw), masked))

    def handle_endtag(self, tag: str) -> None:
        if tag != "textarea" or self._secret_textarea is None:
            return
        begin, end = self._secret_textarea, self._offset()
        self._secret_textarea = None
        if end > begin and self.text[begin:end].strip():
            self.edits.append((begin, end, _MARKUP_REDACTED))


def _redact_html(text: str, policy: RedactionPolicy) -> str | None:
    parser = _HtmlSecrets(text, policy)
    try:
        parser.feed(text)
        parser.close()
    except Exception:  # noqa: BLE001 - a document the parser rejects gets the text pass
        return None
    return _apply(text, parser.edits) if parser.edits else text


# -- XML ----------------------------------------------------------------------------

_XML_START_TAG = re.compile(rb"<[^\s/>!?]+(?:\s+[^\s=/>]+\s*=\s*(?:\"[^\"]*\"|'[^']*'))*\s*/?>")


def _local_name(name: str) -> str:
    return name.rsplit(":", 1)[-1].rsplit("}", 1)[-1]


class _XmlSecrets:
    """Walks a document with expat and records byte spans of secret text and attributes."""

    def __init__(self, data: bytes, policy: RedactionPolicy) -> None:
        self.data = data
        self.policy = policy
        self.edits: list[tuple[int, int, bytes]] = []
        self._secret: list[bool] = []
        self._text_spans: dict[int, int] = {}  # span end -> earliest span start
        self._cdata_start: int | None = None
        self.parser = expat.ParserCreate("utf-8")
        self.parser.StartElementHandler = self._start
        self.parser.EndElementHandler = self._end
        self.parser.CharacterDataHandler = self._characters
        self.parser.StartCdataSectionHandler = self._cdata_begin
        self.parser.EndCdataSectionHandler = self._cdata_end

    def run(self) -> bool:
        if b"<!ENTITY" in self.data:
            return False  # internal entities can expand without bound: text pass only
        try:
            self.parser.Parse(self.data, True)
        except expat.ExpatError:
            return False
        for end, start in self._text_spans.items():
            if self.data[start:end].strip():
                self.edits.append((start, end, _MARKUP_REDACTED.encode()))
        return True

    def _start(self, name: str, attributes: dict[str, str]) -> None:
        index = self.parser.CurrentByteIndex
        inherited = bool(self._secret and self._secret[-1])
        own = is_sensitive_key(_local_name(name), self.policy) or any(
            _local_name(key).casefold() in _NAME_SLOTS and is_sensitive_key(value, self.policy)
            for key, value in attributes.items()
        )
        secret = inherited or own
        self._secret.append(secret)
        masked = [
            key
            for key in attributes
            if attributes[key].strip()
            and (
                is_sensitive_key(_local_name(key), self.policy)
                or (own and _local_name(key).casefold() in _VALUE_SLOTS)
            )
        ]
        if not masked:
            return
        match = _XML_START_TAG.match(self.data, index)
        if match is None:
            return
        raw = match.group(0)
        rewritten = raw
        for key in masked:
            rewritten = _mask_xml_attribute(rewritten, key)
        if rewritten != raw:
            self.edits.append((match.start(), match.end(), rewritten))

    def _end(self, _name: str) -> None:
        self._secret.pop()

    def _characters(self, _data: str) -> None:
        if self._cdata_start is not None or not self._secret or not self._secret[-1]:
            return
        start = self.parser.CurrentByteIndex
        end = self.data.find(b"<", start)
        end = len(self.data) if end == -1 else end
        self._text_spans[end] = min(start, self._text_spans.get(end, start))

    def _cdata_begin(self) -> None:
        self._cdata_start = self.parser.CurrentByteIndex

    def _cdata_end(self) -> None:
        start, self._cdata_start = self._cdata_start, None
        if start is None or not self._secret or not self._secret[-1]:
            return
        end = self.parser.CurrentByteIndex + len(b"]]>")
        body = self.data[start + len(b"<![CDATA[") : end - len(b"]]>")]
        if body.strip():
            self.edits.append((start, end, b"<![CDATA[" + REDACTED.encode() + b"]]>"))


def _mask_xml_attribute(tag: bytes, name: str) -> bytes:
    pattern = re.compile(
        rb"(?s)(?<![\w:.-])(" + re.escape(name.encode()) + rb"\s*=\s*)(\"[^\"]*\"|'[^']*')"
    )

    def replace(match: re.Match[bytes]) -> bytes:
        quote = match.group(2)[:1]
        return match.group(1) + quote + _MARKUP_REDACTED.encode() + quote

    return pattern.sub(replace, tag)


def _redact_xml(text: str, policy: RedactionPolicy) -> str | None:
    data = text.encode("utf-8")
    walker = _XmlSecrets(data, policy)
    if not walker.run():
        return None
    if not walker.edits:
        return text
    for start, end, replacement in sorted(walker.edits, reverse=True):
        data = data[:start] + replacement + data[end:]
    return data.decode("utf-8")


# -- CSV ----------------------------------------------------------------------------

_DELIMITERS = (",", ";", "\t", "|")


def _delimiter(header: str) -> str:
    counts = {candidate: header.count(candidate) for candidate in _DELIMITERS}
    best = max(counts, key=lambda candidate: counts[candidate])
    return best if counts[best] else ","


def _redact_csv(text: str, policy: RedactionPolicy, delimiter: str | None) -> str | None:
    lines = list(io.StringIO(text, newline=""))
    header_at = next((index for index, line in enumerate(lines) if line.strip()), None)
    if header_at is None:
        return None
    separator = delimiter or _delimiter(lines[header_at])
    try:
        header = next(csv.reader([lines[header_at]], delimiter=separator))
    except csv.Error:
        return None
    columns = {index for index, cell in enumerate(header) if is_sensitive_key(cell, policy)}
    if not columns:
        return None
    out = lines[: header_at + 1]
    reader = csv.reader(iter(lines[header_at + 1 :]), delimiter=separator)
    consumed = 0
    try:
        for row in reader:
            raw = "".join(lines[header_at + 1 + consumed : header_at + 1 + reader.line_num])
            consumed = reader.line_num
            changed = [
                REDACTED if index in columns and cell.strip() and cell != REDACTED else cell
                for index, cell in enumerate(row)
            ]
            if changed == row:
                out.append(raw)
                continue
            ending = re.search(r"(\r\n|\n|\r)$", raw)
            buffer = io.StringIO()
            csv.writer(
                buffer, delimiter=separator, lineterminator=ending.group(1) if ending else ""
            ).writerow(changed)
            out.append(buffer.getvalue())
    except csv.Error:
        return None
    out.extend(lines[header_at + 1 + consumed :])
    return "".join(out)
