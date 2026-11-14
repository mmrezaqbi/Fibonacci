"""نویسنده‌ی ساده‌ی فایل Excel (.xlsx) فقط با کتابخانه‌ی استاندارد پایتون (بدون نیاز به نصب openpyxl).

هر شیت: عنوان، ردیف سرستون (پررنگ) و ردیف‌ها. عدد به‌صورت عدد و متن به‌صورت متن ذخیره می‌شود
(شماره موبایل و کدها صفر اول خود را حفظ می‌کنند) و شیت راست‌به‌چپ است.
"""
import io
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape

_BAD_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_BAD_SHEET = re.compile(r"[\[\]:*?/\\]")


def _col(n):
    """0 → A، 25 → Z، 26 → AA"""
    name = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        name = chr(65 + r) + name
    return name


def _text(value):
    return escape(_BAD_XML.sub("", str(value)))


def _cell(ref, value, style=0):
    s = f' s="{style}"' if style else ""
    if value is None or value == "":
        return f'<c r="{ref}"{s}/>'
    if isinstance(value, bool):
        return f'<c r="{ref}"{s} t="inlineStr"><is><t>{"بله" if value else "خیر"}</t></is></c>'
    if isinstance(value, (int, float, Decimal)):
        return f'<c r="{ref}"{s}><v>{value}</v></c>'
    if isinstance(value, (datetime, date)):
        value = value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    text = str(value)
    # جلوگیری از اجرای فرمول: متن‌ها همیشه به‌صورت رشته (inlineStr) ذخیره می‌شوند و فرمول نمی‌شوند
    return f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">{_text(text)}</t></is></c>'


def _sheet_xml(header, rows):
    widths = [len(str(h)) for h in header]
    body = []
    head_cells = "".join(_cell(f"{_col(i)}1", h, 1) for i, h in enumerate(header))
    body.append(f'<row r="1">{head_cells}</row>')
    for r, row in enumerate(rows, start=2):
        cells = []
        for i, v in enumerate(row):
            cells.append(_cell(f"{_col(i)}{r}", v))
            if i < len(widths):
                widths[i] = max(widths[i], min(len(str(v)) if v is not None else 0, 50))
        body.append(f'<row r="{r}">{"".join(cells)}</row>')
    cols = "".join(
        f'<col min="{i + 1}" max="{i + 1}" width="{min(max(w + 3, 9), 55)}" customWidth="1"/>'
        for i, w in enumerate(widths)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView rightToLeft="1" workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        f'<cols>{cols}</cols><sheetData>{"".join(body)}</sheetData></worksheet>'
    )


def build_xlsx(sheets):
    """sheets: لیستی از (عنوان، سرستون‌ها، ردیف‌ها) ← بایت‌های فایل xlsx"""
    names, used = [], set()
    for title, _h, _r in sheets:
        name = _BAD_SHEET.sub(" ", str(title)).strip()[:31] or "Sheet"
        base, n = name, 2
        while name.lower() in used:
            name = f"{base[:28]} {n}"
            n += 1
        used.add(name.lower())
        names.append(name)

    count = len(sheets)
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        + "".join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, count + 1)
        )
        + "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
        + "".join(
            f'<sheet name="{escape(n, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>'
            for i, n in enumerate(names, start=1)
        )
        + "</sheets></workbook>"
    )
    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, count + 1)
        )
        + f'<Relationship Id="rId{count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="11"/><name val="Tahoma"/></font>'
        '<font><b/><sz val="11"/><name val="Tahoma"/></font></fonts>'
        '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFE8ECF8"/><bgColor indexed="64"/></patternFill></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/styles.xml", styles)
        for i, (_t, header, rows) in enumerate(sheets, start=1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", _sheet_xml(header, rows))
    return buf.getvalue()
