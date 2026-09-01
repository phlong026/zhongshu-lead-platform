from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from xml.etree import ElementTree
from zipfile import ZipFile


_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def read_xlsx(source: Path | bytes | BinaryIO) -> dict[str, list[dict[str, str]]]:
    stream = BytesIO(source) if isinstance(source, bytes) else source
    with ZipFile(stream) as workbook:
        workbook_xml = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
        relationships_xml = ElementTree.fromstring(
            workbook.read("xl/_rels/workbook.xml.rels")
        )
        targets = {
            relationship.attrib["Id"]: relationship.attrib["Target"]
            for relationship in relationships_xml.findall(
                f"{{{_PACKAGE_REL_NS}}}Relationship"
            )
        }
        sheets: dict[str, list[dict[str, str]]] = {}
        for sheet in workbook_xml.findall(f".//{{{_MAIN_NS}}}sheet"):
            name = sheet.attrib["name"]
            target = targets[sheet.attrib[f"{{{_REL_NS}}}id"]]
            sheet_path = f"xl/{target.lstrip('/')}"
            sheet_xml = ElementTree.fromstring(workbook.read(sheet_path))
            values = [_row_values(row) for row in sheet_xml.findall(f".//{{{_MAIN_NS}}}row")]
            headers = values[0] if values else []
            sheets[name] = [
                {header: row[index] if index < len(row) else "" for index, header in enumerate(headers)}
                for row in values[1:]
            ]
        return sheets


def _row_values(row: ElementTree.Element) -> list[str]:
    result: list[str] = []
    for cell in row.findall(f"{{{_MAIN_NS}}}c"):
        column = _column_index(cell.attrib["r"])
        while len(result) < column - 1:
            result.append("")
        if cell.attrib.get("t") == "inlineStr":
            value = "".join(
                node.text or "" for node in cell.findall(f".//{{{_MAIN_NS}}}t")
            )
        else:
            node = cell.find(f"{{{_MAIN_NS}}}v")
            value = node.text if node is not None and node.text is not None else ""
        result.append(value)
    return result


def _column_index(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    index = 0
    for character in letters:
        index = index * 26 + ord(character.upper()) - ord("A") + 1
    return index
