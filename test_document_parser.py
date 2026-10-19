"""Unit tests for document_parser.py."""

import io
import zipfile
import pytest

from document_parser import (
    parse_document_content,
    validate_file_signature,
    check_zip_bomb,
    DocumentSecurityException,
)
from models import ExtractionStatus


def test_validate_file_signature_pdf():
    valid_pdf = b"%PDF-1.4\n%test content\n"
    assert validate_file_signature(valid_pdf, "pdf") is True
    assert validate_file_signature(b"NOT_A_PDF", "pdf") is False


def test_validate_file_signature_zip_formats():
    valid_zip_prefix = b"PK\x03\x04" + b"\x00" * 20
    assert validate_file_signature(valid_zip_prefix, "docx") is True
    assert validate_file_signature(valid_zip_prefix, "xlsx") is True
    assert validate_file_signature(valid_zip_prefix, "pptx") is True
    assert validate_file_signature(b"INVALID_HEADER", "docx") is False


def test_validate_file_signature_csv():
    valid_csv = b"Col1,Col2,Col3\nVal1,Val2,Val3\n"
    assert validate_file_signature(valid_csv, "csv") is True


def test_parse_csv_content():
    csv_bytes = b"Company,Tool,Status\nMicro Labs,Anaplan,Active\nSpotify,Jedox,Evaluating\n"
    res = parse_document_content(csv_bytes, "test.csv", "text/csv")
    assert res["status"] == ExtractionStatus.SUCCESS.value
    assert "Micro Labs" in res["extracted_text"]
    assert "Spotify" in res["extracted_text"]
    assert len(res["sections"]) == 1


def test_parse_excel_content():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Clients"
    ws.append(["Company Name", "Software", "Spend"])
    ws.append(["Acme Corp", "Jedox", 50000])
    buf = io.BytesIO()
    wb.save(buf)
    excel_bytes = buf.getvalue()

    res = parse_document_content(excel_bytes, "clients.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert res["status"] == ExtractionStatus.SUCCESS.value
    assert "Acme Corp" in res["extracted_text"]
    assert "Jedox" in res["extracted_text"]
    assert any("Clients" in s["location"] for s in res["sections"])


def test_parse_docx_content():
    import docx
    doc = docx.Document()
    doc.add_heading("Customer Case Study", level=1)
    doc.add_paragraph("Global Retailer deployed Jedox for automated workforce planning.")
    table = doc.add_table(rows=1, cols=2)
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = "Metric"
    hdr_cells[1].text = "Value"
    row_cells = table.add_row().cells
    row_cells[0].text = "Efficiency Gain"
    row_cells[1].text = "45%"

    buf = io.BytesIO()
    doc.save(buf)
    docx_bytes = buf.getvalue()

    res = parse_document_content(docx_bytes, "case_study.docx")
    assert res["status"] == ExtractionStatus.SUCCESS.value
    assert "Customer Case Study" in res["extracted_text"]
    assert "Global Retailer" in res["extracted_text"]
    assert "Efficiency Gain" in res["extracted_text"]


def test_parse_pptx_content():
    import pptx
    prs = pptx.Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    title = slide.shapes.title
    title.text = "Enterprise Planning with Jedox"
    subtitle = slide.placeholders[1]
    subtitle.text = "Presented for Client Showcase"

    buf = io.BytesIO()
    prs.save(buf)
    pptx_bytes = buf.getvalue()

    res = parse_document_content(pptx_bytes, "presentation.pptx")
    assert res["status"] == ExtractionStatus.SUCCESS.value
    assert "Enterprise Planning with Jedox" in res["extracted_text"]
    assert "Client Showcase" in res["extracted_text"]


def test_parse_pdf_content():
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Case Study: Micro Labs GmbH implemented Anaplan enterprise solutions.")
    pdf_bytes = doc.tobytes()
    doc.close()

    res = parse_document_content(pdf_bytes, "microlabs.pdf")
    assert res["status"] == ExtractionStatus.SUCCESS.value
    assert "Micro Labs GmbH" in res["extracted_text"]
    assert any("Page 1" in s["location"] for s in res["sections"])


def test_zip_bomb_protection():
    # Construct a high compression ratio zip (e.g. 20MB of zeros compressing to <10KB)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("huge_file.txt", b"\x00" * (60 * 1024 * 1024))
    bomb_bytes = buf.getvalue()

    with pytest.raises(DocumentSecurityException):
        check_zip_bomb(bomb_bytes)


def test_oversized_document_rejected():
    oversized = b"0" * (26 * 1024 * 1024)
    res = parse_document_content(oversized, "huge.pdf")
    assert res["status"] == ExtractionStatus.FAILED.value
    assert "exceeds maximum limit" in res["error_message"]


def test_unsupported_legacy_format():
    res = parse_document_content(b"fake doc binary", "legacy.doc")
    assert res["status"] == ExtractionStatus.UNSUPPORTED.value
    assert "Legacy binary format" in res["error_message"]
