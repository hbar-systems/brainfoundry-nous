"""Office files as a page in the Files pane (cc_office, hbar 2026-11-22: "No preview for this type")."""
from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "cc"))
spec = importlib.util.spec_from_file_location("cc_office", ROOT / "scripts" / "cc" / "cc_office.py")
O = importlib.util.module_from_spec(spec); spec.loader.exec_module(O)

PML = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
RELS = 'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"'


def _pptx(p: Path):
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("ppt/presentation.xml", f'<p:presentation {PML}><p:sldSz cx="9144000" cy="5143500"/><p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst></p:presentation>')
        z.writestr("ppt/_rels/presentation.xml.rels", f'<Relationships {RELS}><Relationship Id="rId1" Target="slides/slide1.xml"/></Relationships>')
        z.writestr("ppt/slides/slide1.xml", f'<p:sld {PML}><p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr id="2" name="t"/><p:cNvSpPr/><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>'
                    f'<p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="9144000" cy="1000000"/></a:xfrm></p:spPr><p:txBody><a:bodyPr/><a:p><a:r><a:rPr b="1"/><a:t>Hello &lt;script&gt;</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>')


def test_pptx_slide_text_escaped(tmp_path):
    f = tmp_path / "deck.pptx"; _pptx(f)
    h = O.to_html(f).decode()
    assert "1 slides" in h and "Hello &lt;script&gt;" in h and "<script" not in h and "font-weight:700" in h


def test_docx_heading_and_list(tmp_path):
    f = tmp_path / "a.docx"
    W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("word/document.xml", f'<w:document {W}><w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Title</w:t></w:r></w:p>'
                    '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/></w:numPr></w:pPr><w:r><w:rPr><w:i/></w:rPr><w:t>item</w:t></w:r></w:p></w:body></w:document>')
    h = O.to_html(f).decode()
    assert "<h1>Title</h1>" in h and "<i>item</i>" in h and "&bull;" in h


def test_xlsx_cells(tmp_path):
    f = tmp_path / "b.xlsx"
    S = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {S}><sheets><sheet name="Money" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", f'<Relationships {RELS}><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", f'<sst {S}><si><t>Rent</t></si></sst>')
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet {S}><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>900</v></c></row></sheetData></worksheet>')
    h = O.to_html(f).decode()
    assert "Money" in h and "<td>Rent</td><td>900</td>" in h


def test_bad_and_legacy_files_say_so(tmp_path):
    bad = tmp_path / "x.pptx"; bad.write_text("not a zip")
    assert "could not be read" in O.to_html(bad).decode()
    old = tmp_path / "y.doc"; old.write_bytes(b"\xd0\xcf\x11\xe0")
    assert "older or non-Microsoft format" in O.to_html(old).decode()
