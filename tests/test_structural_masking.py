"""CSV, XML and HTML attachments are masked by structure (stage 6, T08).

The canaries are not configured and carry no recognizable spelling: only the column
header, element name or field type says they are secret.
"""

from __future__ import annotations

import csv
import io
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

import pytest

from testence.evidence.sanitize import REDACTED, redact_document_text, sanitize_text
from testence.export import export_run
from tests.test_auto_env_masking import run_project, tree_text

CANARY = "cnry-struct-8d41"
KEEP = "Lisbon"

_HTML = f"""<!doctype html>
<html><body>
<form action="/login" method="post">
  <input type="text" name="city" value="{KEEP}">
  <input type="password" name="pw" value="{CANARY}-pw">
  <input type='hidden' name='next' value='{CANARY}-hidden'>
  <input name="otp" autocomplete="one-time-code" value={CANARY}-otp>
  <input VALUE="{CANARY}-upper" TYPE="PASSWORD">
  <input type="text" data-value="{KEEP}-data" value="{KEEP}-shown">
  <textarea name="api_token">
{CANARY}-area
</textarea>
</form>
<meta name="csrf-token" content="{CANARY}-meta">
<p>Visit {KEEP}</p>
</body></html>
"""

_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- keep this comment -->
<config xmlns:x="urn:x">
  <city>{KEEP}</city>
  <password>{CANARY}-text</password>
  <db host="db.local" password="{CANARY}-attr" port="5432">
    <user>bob</user>
  </db>
  <credentials>
    <login>{CANARY}-nested</login>
    <note><![CDATA[{CANARY}-cdata]]></note>
  </credentials>
  <param name="api_key" value="{CANARY}-slot"/>
  <param name="region" value="{KEEP}-eu"/>
  <x:secret>{CANARY}-ns &amp; more</x:secret>
</config>
"""

_CSV = (
    "id,name,API Token,note\r\n"
    f'1,ann,{CANARY}-a,"hello, {KEEP}"\r\n'
    f'2,bob,"{CANARY},with comma",multi\r\n'
    "3,cy,,empty\r\n"
    f'4,"multi\nline",{CANARY}-d,{KEEP}\r\n'
)


def _html_events(text: str) -> list[tuple[str, str]]:
    class Tags(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=False)
            self.events: list[tuple[str, str]] = []

        def handle_starttag(self, tag, attrs):
            self.events.append(("start", tag + ":" + ",".join(sorted(name for name, _ in attrs))))

        def handle_endtag(self, tag):
            self.events.append(("end", tag))

    parser = Tags()
    parser.feed(text)
    parser.close()
    return parser.events


def test_html_masks_secret_fields_and_keeps_the_markup():
    cleaned = redact_document_text(_HTML, suffix=".html")
    assert CANARY not in cleaned
    assert KEEP in cleaned and f"{KEEP}-shown" in cleaned and f"{KEEP}-data" in cleaned
    assert _html_events(cleaned) == _html_events(_HTML)
    assert cleaned.count("&lt;redacted&gt;") == 6
    assert 'type="text" name="city"' in cleaned


def test_xml_masks_text_and_attributes_and_keeps_the_document():
    cleaned = redact_document_text(_XML, suffix=".xml")
    assert CANARY not in cleaned
    assert "<!-- keep this comment -->" in cleaned
    assert f"<city>{KEEP}</city>" in cleaned and f'value="{KEEP}-eu"' in cleaned
    assert "<user>bob</user>" in cleaned and 'host="db.local"' in cleaned

    def shape(text: str) -> list[tuple[str, tuple[str, ...]]]:
        return [(el.tag, tuple(sorted(el.attrib))) for el in ET.fromstring(text).iter()]

    assert shape(cleaned) == shape(_XML)
    assert ET.fromstring(cleaned).find("password").text == REDACTED  # type: ignore[union-attr]


def test_csv_masks_cells_of_secret_headers_and_keeps_the_file():
    cleaned = redact_document_text(_CSV, suffix=".csv")
    assert CANARY not in cleaned
    before = list(csv.reader(io.StringIO(_CSV, newline="")))
    after = list(csv.reader(io.StringIO(cleaned, newline="")))
    assert len(after) == len(before) and after[0] == before[0]
    token = before[0].index("API Token")
    for old, new in zip(before[1:], after[1:], strict=True):
        assert [cell for i, cell in enumerate(new) if i != token] == [
            cell for i, cell in enumerate(old) if i != token
        ]
        assert new[token] == (REDACTED if old[token] else "")
    assert cleaned.count("\r\n") == _CSV.count("\r\n")
    # A row with nothing to mask is byte for byte what it was.
    assert "3,cy,,empty\r\n" in cleaned


def test_tab_separated_files_and_other_delimiters():
    tsv = f"user\tpassword\tcity\nann\t{CANARY}\t{KEEP}\n"
    assert (
        redact_document_text(tsv, suffix=".tsv")
        == f"user\tpassword\tcity\nann\t{REDACTED}\t{KEEP}\n"
    )
    semicolons = f"user;secret;city\nann;{CANARY};{KEEP}\n"
    assert CANARY not in redact_document_text(semicolons, suffix=".csv")


@pytest.mark.parametrize("suffix", [".csv", ".xml", ".html"])
def test_masking_is_idempotent(suffix):
    source = {".csv": _CSV, ".xml": _XML, ".html": _HTML}[suffix]
    once = redact_document_text(source, suffix=suffix)
    assert redact_document_text(once, suffix=suffix) == once


def test_the_text_pass_still_runs_after_the_structural_one():
    text = f"<log>\n<line>token={CANARY}</line>\n<line>city={KEEP}</line>\n</log>\n"
    cleaned = redact_document_text(text, suffix=".xml")
    assert CANARY not in cleaned and KEEP in cleaned
    known = redact_document_text(
        f"<p>{CANARY}-known</p>", suffix=".html", secrets=[f"{CANARY}-known"]
    )
    assert CANARY not in known


@pytest.mark.parametrize(
    ("suffix", "text"),
    [
        (".xml", f"<a><password>{CANARY}"),  # not well-formed
        (".xml", f'<!DOCTYPE a [<!ENTITY e "{CANARY}">]><a><password>&e;</password></a>'),
        (".csv", f"a,b\n1,{CANARY}\n"),  # no secret header
        (".html", f"<p>{CANARY}</p>"),
    ],
)
def test_documents_without_structure_fall_back_to_the_text_rules(suffix, text):
    assert redact_document_text(text, suffix=suffix) == sanitize_text(text)


def test_an_unchanged_document_keeps_its_bytes():
    text = f"<city>{KEEP}</city>" + chr(10)
    assert redact_document_text(text, suffix=".xml") == text


_ATTACH_TEST = f"""
def test_attaches_tables(testence_writer, request):
    nodeid = request.node.nodeid
    testence_writer.attach(nodeid, "rows.csv", {_CSV!r}, "text/csv")
    testence_writer.attach(nodeid, "page.html", {_HTML!r}, "text/html")
    testence_writer.attach(nodeid, "doc.xml", {_XML!r}, "text/xml")
    testence_writer.attach(nodeid, "other.xml", {_XML!r}, "application/xml")
"""


def test_a_canary_in_each_format_reaches_no_artifact(tmp_path):
    project = tmp_path / "project"
    run_dir = run_project(project, {"test_attach.py": _ATTACH_TEST}, {}, {}, returncode=0)
    export_run(run_dir, "allure", tmp_path / "allure")
    export_run(run_dir, "ctrf", tmp_path / "ctrf")
    for root in (run_dir, tmp_path / "allure", tmp_path / "ctrf"):
        assert CANARY not in tree_text(root), root
    assert len(list(run_dir.rglob("attachments/*"))) == 4
    assert KEEP in tree_text(run_dir)
