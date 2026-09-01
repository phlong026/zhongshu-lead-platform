from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from zipfile import ZIP_DEFLATED, ZipFile


_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_INVALID_XML = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
_INVALID_SHEET_NAME = re.compile(r"[\[\]:*?/\\]")
_MAX_CELL_CHARACTERS = 32_767


class XlsxSizeLimitError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WorksheetSpec:
    name: str
    fieldnames: list[str]
    rows: Iterable[Mapping[str, Any]]
    rows_per_sheet: int
    total_rows: int


@dataclass(slots=True)
class _ByteBudget:
    limit: int
    used: int = 0

    def consume(self, data: bytes) -> None:
        self.used += len(data)
        if self.used > self.limit:
            raise XlsxSizeLimitError("导出文件超过安全大小，请缩小筛选范围后分批导出")


@dataclass(frozen=True, slots=True)
class _WrittenSheet:
    name: str
    path: str


def write_xlsx(
    path: Path,
    worksheets: list[WorksheetSpec],
    *,
    heartbeat: Callable[[], None],
    heartbeat_row_interval: int,
    max_uncompressed_bytes: int,
) -> dict[str, int]:
    budget = _ByteBudget(max_uncompressed_bytes)
    written_sheets: list[_WrittenSheet] = []
    row_counts: dict[str, int] = {}
    with ZipFile(path, "w", compression=ZIP_DEFLATED, allowZip64=True) as workbook:
        for spec in worksheets:
            sheets, row_count = _write_worksheet_parts(
                workbook,
                spec,
                first_sheet_index=len(written_sheets) + 1,
                heartbeat=heartbeat,
                heartbeat_row_interval=heartbeat_row_interval,
                budget=budget,
            )
            written_sheets.extend(sheets)
            row_counts[spec.name] = row_count
            heartbeat()
        _write_workbook_parts(workbook, written_sheets)
    return row_counts


def _write_worksheet_parts(
    workbook: ZipFile,
    spec: WorksheetSpec,
    *,
    first_sheet_index: int,
    heartbeat: Callable[[], None],
    heartbeat_row_interval: int,
    budget: _ByteBudget,
) -> tuple[list[_WrittenSheet], int]:
    if spec.rows_per_sheet < 1:
        raise ValueError("每个工作表的最大行数必须大于零")
    iterator = iter(spec.rows)
    pending = next(iterator, None)
    part = 0
    total_count = 0
    written: list[_WrittenSheet] = []
    while pending is not None or part == 0:
        part += 1
        sheet_index = first_sheet_index + part - 1
        sheet_name = _part_sheet_name(
            spec.name,
            part,
            split=spec.total_rows > spec.rows_per_sheet,
        )
        sheet_path = f"xl/worksheets/sheet{sheet_index}.xml"
        with workbook.open(sheet_path, "w", force_zip64=True) as output:
            _write(
                output,
                (
                    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    f'<worksheet xmlns="{_MAIN_NS}">'
                    '<sheetViews><sheetView workbookViewId="0">'
                    '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
                    '</sheetView></sheetViews><sheetFormatPr defaultRowHeight="15"/>'
                    '<sheetData>'
                ),
                budget,
            )
            _write_row(output, 1, spec.fieldnames, header=True, budget=budget)
            sheet_row_count = 0
            while pending is not None and sheet_row_count < spec.rows_per_sheet:
                values = [pending.get(field) for field in spec.fieldnames]
                sheet_row_count += 1
                total_count += 1
                _write_row(
                    output,
                    sheet_row_count + 1,
                    values,
                    header=False,
                    budget=budget,
                )
                if total_count % heartbeat_row_interval == 0:
                    heartbeat()
                pending = next(iterator, None)
            last_column = _column_name(len(spec.fieldnames))
            _write(
                output,
                (
                    f'</sheetData><autoFilter ref="A1:{last_column}{sheet_row_count + 1}"/>'
                    '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" '
                    'header="0.3" footer="0.3"/></worksheet>'
                ),
                budget,
            )
        written.append(_WrittenSheet(name=sheet_name, path=sheet_path))
    return written, total_count


def _write_row(output, row_number: int, values: Iterable[Any], *, header: bool, budget: _ByteBudget) -> None:
    cells = []
    style = ' s="1"' if header else ""
    for column_index, value in enumerate(values, start=1):
        reference = f"{_column_name(column_index)}{row_number}"
        text = _cell_text(value)
        cells.append(
            f'<c r="{reference}" t="inlineStr"{style}><is>'
            f'<t xml:space="preserve">{escape(text, quote=False)}</t></is></c>'
        )
    _write(output, f'<row r="{row_number}">{"".join(cells)}</row>', budget)


def _write(output, value: str, budget: _ByteBudget) -> None:
    data = value.encode("utf-8")
    budget.consume(data)
    output.write(data)


def _cell_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return _INVALID_XML.sub("", text)[:_MAX_CELL_CHARACTERS]


def _part_sheet_name(base_name: str, part: int, *, split: bool) -> str:
    safe_base = _INVALID_SHEET_NAME.sub("_", base_name).strip("'") or "工作表"
    suffix = f"_{part:04d}" if split or part > 1 else ""
    return f"{safe_base[: 31 - len(suffix)]}{suffix}"


def _column_name(index: int) -> str:
    if index < 1:
        raise ValueError("工作表至少需要一列")
    result = []
    while index:
        index, remainder = divmod(index - 1, 26)
        result.append(chr(ord("A") + remainder))
    return "".join(reversed(result))


def _write_workbook_parts(workbook: ZipFile, sheets: list[_WrittenSheet]) -> None:
    if not sheets:
        raise ValueError("工作簿至少需要一个工作表")
    sheet_overrides = "".join(
        f'<Override PartName="/{sheet.path}" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for sheet in sheets
    )
    workbook.writestr(
        "[Content_Types].xml",
        (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Types xmlns="{_CONTENT_TYPES_NS}">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            f"{sheet_overrides}</Types>"
        ),
    )
    workbook.writestr(
        "_rels/.rels",
        (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{_PACKAGE_REL_NS}">'
            f'<Relationship Id="rId1" Type="{_REL_NS}/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>'
        ),
    )
    workbook.writestr(
        "xl/workbook.xml",
        (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<workbook xmlns="{_MAIN_NS}" xmlns:r="{_REL_NS}">'
            '<bookViews><workbookView/></bookViews><sheets>'
            + "".join(
                f'<sheet name="{_attribute(sheet.name)}" sheetId="{index}" r:id="rId{index}"/>'
                for index, sheet in enumerate(sheets, start=1)
            )
            + '</sheets><calcPr calcId="191029"/></workbook>'
        ),
    )
    workbook.writestr(
        "xl/_rels/workbook.xml.rels",
        (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{_PACKAGE_REL_NS}">'
            + "".join(
                f'<Relationship Id="rId{index}" Type="{_REL_NS}/worksheet" '
                f'Target="worksheets/sheet{index}.xml"/>'
                for index in range(1, len(sheets) + 1)
            )
            + f'<Relationship Id="rId{len(sheets) + 1}" Type="{_REL_NS}/styles" '
            'Target="styles.xml"/></Relationships>'
        ),
    )
    workbook.writestr("xl/styles.xml", _styles_xml())


def _attribute(value: str) -> str:
    return escape(value, quote=True)


def _styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<styleSheet xmlns="{_MAIN_NS}">'
        '<fonts count="2"><font><sz val="11"/><name val="等线"/></font>'
        '<font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="等线"/></font></fonts>'
        '<fills count="3"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/>'
        '<bgColor indexed="64"/></patternFill></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>'
    )
