from zipfile import ZipFile

from apps.api.src.services.xlsx_writer import WorksheetSpec, write_xlsx
from apps.api.tests.xlsx_reader import read_xlsx


def test_xlsx_writer_keeps_formula_prefixes_as_plain_text(tmp_path) -> None:
    output = tmp_path / "formula-safe.xlsx"
    dangerous_value = '=HYPERLINK("https://example.invalid","点击")'

    counts = write_xlsx(
        output,
        [
            WorksheetSpec(
                name="客资明细",
                fieldnames=["客户姓名"],
                rows=[{"客户姓名": dangerous_value}],
                rows_per_sheet=10,
                total_rows=1,
            )
        ],
        heartbeat=lambda: None,
        heartbeat_row_interval=1_000,
        max_uncompressed_bytes=1024 * 1024,
    )

    assert counts == {"客资明细": 1}
    assert read_xlsx(output)["客资明细"] == [{"客户姓名": dangerous_value}]
    with ZipFile(output) as workbook:
        sheet_xml = workbook.read("xl/worksheets/sheet1.xml")
    assert b"<f>" not in sheet_xml
    assert b't="inlineStr"' in sheet_xml


def test_xlsx_writer_heartbeats_after_each_worksheet(tmp_path) -> None:
    output = tmp_path / "heartbeat.xlsx"
    heartbeats = []

    write_xlsx(
        output,
        [
            WorksheetSpec(
                name="客资明细",
                fieldnames=["客户姓名"],
                rows=[{"客户姓名": "客户甲"}],
                rows_per_sheet=10,
                total_rows=1,
            ),
            WorksheetSpec(
                name="跟进记录",
                fieldnames=["跟进内容"],
                rows=[{"跟进内容": "已联系"}],
                rows_per_sheet=10,
                total_rows=1,
            ),
        ],
        heartbeat=lambda: heartbeats.append("beat"),
        heartbeat_row_interval=1_000,
        max_uncompressed_bytes=1024 * 1024,
    )

    assert heartbeats == ["beat", "beat"]
