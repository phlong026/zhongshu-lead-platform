from __future__ import annotations

from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from zipfile import ZipFile


def read_xlsx(source: Path | bytes | BinaryIO) -> dict[str, list[dict[str, str]]]:
    stream = BytesIO(source) if isinstance(source, bytes) else source
    with ZipFile(stream) as workbook:
        workbook_parser = _WorkbookParser()
        workbook_parser.feed(workbook.read("xl/workbook.xml").decode("utf-8"))
        relationships_parser = _RelationshipsParser()
        relationships_parser.feed(
            workbook.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        )
        sheets: dict[str, list[dict[str, str]]] = {}
        for name, relationship_id in workbook_parser.sheets:
            target = relationships_parser.targets[relationship_id].lstrip("/")
            sheet_path = target if target.startswith("xl/") else f"xl/{target}"
            worksheet_parser = _WorksheetParser()
            worksheet_parser.feed(workbook.read(sheet_path).decode("utf-8"))
            values = worksheet_parser.rows
            headers = values[0] if values else []
            sheets[name] = [
                {header: row[index] if index < len(row) else "" for index, header in enumerate(headers)}
                for row in values[1:]
            ]
        return sheets


class _WorkbookParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sheets: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "sheet":
            return
        values = dict(attrs)
        name = values.get("name")
        relationship_id = values.get("r:id")
        if name is not None and relationship_id is not None:
            self.sheets.append((name, relationship_id))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


class _RelationshipsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.targets: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "relationship":
            return
        values = dict(attrs)
        relationship_id = values.get("id")
        target = values.get("target")
        if relationship_id is not None and target is not None:
            self.targets[relationship_id] = target

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


class _WorksheetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell_reference: str | None = None
        self._capture_tag: str | None = None
        self._cell_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "row":
            self._row = []
        elif tag == "c" and self._row is not None:
            self._cell_reference = values.get("r")
            self._cell_parts = []
        elif tag in {"t", "v"} and self._cell_reference is not None:
            self._capture_tag = tag

    def handle_endtag(self, tag: str) -> None:
        if tag in {"t", "v"}:
            self._capture_tag = None
        elif tag == "c" and self._row is not None and self._cell_reference is not None:
            column = _column_index(self._cell_reference)
            while len(self._row) < column - 1:
                self._row.append("")
            self._row.append("".join(self._cell_parts))
            self._cell_reference = None
            self._cell_parts = []
        elif tag == "row" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._capture_tag is not None and self._cell_reference is not None:
            self._cell_parts.append(data)


def _column_index(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    index = 0
    for character in letters:
        index = index * 26 + ord(character.upper()) - ord("A") + 1
    return index
