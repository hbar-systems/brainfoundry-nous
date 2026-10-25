#!/usr/bin/env python3
"""make-sample-pptx.py [out.pptx]: writes a minimal PPTX (stdlib zipfile only) with 2 slides and one notes slide,
to test make-deck.py's pptx reader without python-pptx. Created 2026-10-25. It is a bare OOXML package, enough
for the zipfile/XML reader and for LibreOffice; PowerPoint may repair it on open."""
import sys, zipfile

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


def sp(sid, name, ptype, paras):
    ph = '<p:ph type="%s"/>' % ptype if ptype else ""
    body = "".join('<a:p><a:r><a:rPr lang="ru-RU"/><a:t>%s</a:t></a:r></a:p>' % t for t in paras)
    return ('<p:sp><p:nvSpPr><p:cNvPr id="%d" name="%s"/><p:cNvSpPr/><p:nvPr>%s</p:nvPr></p:nvSpPr>'
            '<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>%s</p:txBody></p:sp>' % (sid, name, ph, body))


def slide(shapes):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sld xmlns:a="%s" xmlns:r="%s" xmlns:p="%s">'
            '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr/>%s</p:spTree></p:cSld></p:sld>' % (A, R, P, "".join(shapes)))


def notes(shapes):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:notes xmlns:a="%s" xmlns:r="%s" xmlns:p="%s">'
            '<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr/>%s</p:spTree></p:cSld></p:notes>' % (A, R, P, "".join(shapes)))


out = sys.argv[1] if len(sys.argv) > 1 else "sample.pptx"
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("[Content_Types].xml",
               '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
               '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
               '<Default Extension="xml" ContentType="application/xml"/>'
               '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
               '<Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
               '<Override PartName="/ppt/slides/slide2.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
               '<Override PartName="/ppt/notesSlides/notesSlide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>'
               '</Types>')
    z.writestr("_rels/.rels",
               '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="%s">'
               '<Relationship Id="rId1" Type="%s/officeDocument" Target="ppt/presentation.xml"/></Relationships>' % (PKG, R))
    z.writestr("ppt/presentation.xml",
               '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:presentation xmlns:a="%s" xmlns:r="%s" xmlns:p="%s">'
               '<p:sldIdLst><p:sldId id="256" r:id="rId1"/><p:sldId id="257" r:id="rId2"/></p:sldIdLst>'
               '<p:sldSz cx="12192000" cy="6858000"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>' % (A, R, P))
    z.writestr("ppt/_rels/presentation.xml.rels",
               '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="%s">'
               '<Relationship Id="rId1" Type="%s/slide" Target="slides/slide1.xml"/>'
               '<Relationship Id="rId2" Type="%s/slide" Target="slides/slide2.xml"/></Relationships>' % (PKG, R, R))
    z.writestr("ppt/slides/slide1.xml", slide([
        sp(2, "Title 1", "ctrTitle", ["Социология города"]),
        sp(3, "Subtitle 2", "subTitle", ["Лекция 3: Чикагская школа"]),
    ]))
    z.writestr("ppt/slides/_rels/slide1.xml.rels",
               '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="%s">'
               '<Relationship Id="rId2" Type="%s/notesSlide" Target="../notesSlides/notesSlide1.xml"/></Relationships>' % (PKG, R))
    z.writestr("ppt/notesSlides/notesSlide1.xml", notes([
        sp(2, "Notes Placeholder", "body", ["Начать с вопроса: кто из вас вырос в городе?"]),
        sp(3, "Slide Number", "sldNum", ["1"]),
    ]))
    z.writestr("ppt/slides/slide2.xml", slide([
        sp(2, "Title 1", "title", ["Концентрические зоны Берджесса"]),
        sp(3, "Content 2", "body", ["Центральный деловой район", "Переходная зона", "Зона рабочих кварталов",
                                    "Жилая зона", "Зона пригородов", "Модель 1925 года, Чикаго",
                                    "Критика: Лос-Анджелесская школа, 1990-е"]),
    ]))
print(out)
