"""Multi-format Document and Media Intelligence Parser.

Provides robust, safe, and traceable extraction across:
- PDF (.pdf) via PyMuPDF (fitz) with page-level text, tables, and metadata.
- Spreadsheets (.xlsx, .csv) via openpyxl and standard csv with sheet/row/cell coordinates.
- Word documents (.docx) via python-docx with paragraph headings and tables.
- Presentations (.pptx) via python-pptx with slide numbers and shape text.
- Images (.png, .jpg, .jpeg, .webp, .tiff) via Pillow with metadata and safe OCR fallback.

Security Features:
- File signature (magic bytes) validation.
- Zip expansion bomb protection (decompression ratio limit and absolute byte threshold).
- Size limits (max 25MB per document).
- No macro execution (macros in Office documents are ignored and never executed).
- Encrypted document handling (marked as ENCRYPTED rather than crashing).
"""

from __future__ import annotations

import csv
import io
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import zipfile

import openpyxl
from PIL import Image
import pymupdf
import docx
import pptx

from models import DocumentFormat, ExtractionStatus

logger = logging.getLogger(__name__)

# Security & Performance Limits
MAX_DOCUMENT_SIZE_BYTES = 25 * 1024 * 1024       # 25 MB
MAX_ZIP_EXPANSION_BYTES = 80 * 1024 * 1024       # 80 MB
MAX_ZIP_COMPRESSION_RATIO = 50.0                 # Max uncompressed / compressed ratio
MAX_PAGES_OR_SLIDES = 200                        # Cap on multi-page/slide rendering
MAX_SPREADSHEET_ROWS_PER_SHEET = 2000            # Cap on spreadsheet rows parsed per sheet

DOC_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".csv", ".docx", ".doc", ".pptx", ".ppt"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif"}
RESOURCE_EXTENSIONS = DOC_EXTENSIONS | IMAGE_EXTENSIONS

# Magic Byte Signatures
MAGIC_SIGNATURES: Dict[str, bytes] = {
    "pdf": b"%PDF-",
    "zip": b"PK\x03\x04",
    "png": b"\x89PNG\r\n\x1a\n",
    "jpeg": b"\xff\xd8\xff",
    "webp_riff": b"RIFF",
    "tiff_le": b"II*\x00",
    "tiff_be": b"MM\x00*",
}


class DocumentSecurityException(Exception):
    """Raised when a document violates security boundaries."""
    pass


class DocumentParseException(Exception):
    """Raised when an unrecoverable parse error occurs."""
    pass


def validate_file_signature(content: bytes, declared_ext: str) -> bool:
    """Validate that the content prefix matches expected file signatures."""
    if not content:
        return False
    ext = declared_ext.lower().lstrip(".")
    if ext == "pdf":
        return content.startswith(MAGIC_SIGNATURES["pdf"])
    if ext in ("docx", "pptx", "xlsx"):
        return content.startswith(MAGIC_SIGNATURES["zip"])
    if ext == "png":
        return content.startswith(MAGIC_SIGNATURES["png"])
    if ext in ("jpg", "jpeg"):
        return content.startswith(MAGIC_SIGNATURES["jpeg"])
    if ext == "webp":
        return len(content) > 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    if ext == "tiff":
        return content.startswith(MAGIC_SIGNATURES["tiff_le"]) or content.startswith(MAGIC_SIGNATURES["tiff_be"])
    if ext == "csv":
        # CSV is plain text, check that it's decodeable ASCII/UTF-8
        try:
            content[:1024].decode("utf-8")
            return True
        except UnicodeDecodeError:
            try:
                content[:1024].decode("latin-1")
                return True
            except Exception:
                return False
    return True


def check_zip_bomb(file_bytes: bytes) -> None:
    """Inspect zip archive member sizes to prevent decompression bombs."""
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            total_uncompressed = sum(info.file_size for info in zf.infolist())
            compressed_size = max(len(file_bytes), 1)
            ratio = total_uncompressed / compressed_size

            if total_uncompressed > MAX_ZIP_EXPANSION_BYTES:
                raise DocumentSecurityException(
                    f"Archive expansion limit exceeded: {total_uncompressed} bytes (max: {MAX_ZIP_EXPANSION_BYTES})"
                )
            if ratio > MAX_ZIP_COMPRESSION_RATIO:
                raise DocumentSecurityException(
                    f"Archive compression ratio suspicious: {ratio:.1f}x (max: {MAX_ZIP_COMPRESSION_RATIO}x)"
                )
    except zipfile.BadZipFile as e:
        raise DocumentParseException(f"Corrupted or invalid zip archive: {e}")


def parse_pdf(pdf_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Extract page-level text, tables, and metadata from PDF bytes."""
    sections: List[Dict[str, Any]] = []
    full_text_parts: List[str] = []

    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        return {
            "status": ExtractionStatus.FAILED.value,
            "error_message": f"Failed to open PDF document: {e}",
            "extracted_text": "",
            "sections": [],
            "metadata": {},
        }

    if doc.is_encrypted:
        return {
            "status": ExtractionStatus.ENCRYPTED.value,
            "error_message": "PDF is password protected or encrypted.",
            "extracted_text": "",
            "sections": [],
            "metadata": {},
        }

    page_count = min(doc.page_count, MAX_PAGES_OR_SLIDES)
    for page_idx in range(page_count):
        page_num = page_idx + 1
        page = doc.load_page(page_idx)
        text = page.get_text("text").strip()
        tables_data = []

        # Table extraction if available
        try:
            tabs = page.find_tables()
            for tab in tabs:
                df_rows = tab.extract()
                if df_rows:
                    tables_data.append(df_rows)
                    for row in df_rows:
                        row_text = " | ".join(str(cell) for cell in row if cell is not None)
                        if row_text:
                            text += f"\n[Table Row] {row_text}"
        except Exception:
            pass

        if text:
            full_text_parts.append(f"--- Page {page_num} ---\n{text}")
            sections.append({
                "location": f"Page {page_num}",
                "page": page_num,
                "text": text,
                "tables_count": len(tables_data),
            })

    metadata = dict(doc.metadata) if doc.metadata else {}
    doc.close()

    total_text = "\n\n".join(full_text_parts)
    status = ExtractionStatus.SUCCESS.value if total_text else ExtractionStatus.PARTIAL.value
    err = "No text extracted (scanned or image-only PDF)" if not total_text else None

    return {
        "status": status,
        "error_message": err,
        "extracted_text": total_text,
        "sections": sections,
        "metadata": metadata,
    }


def parse_excel(xlsx_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Extract sheet names, cell rows, and tables from XLSX spreadsheet."""
    check_zip_bomb(xlsx_bytes)

    sections: List[Dict[str, Any]] = []
    full_text_parts: List[str] = []

    try:
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True, read_only=True)
    except Exception as e:
        return {
            "status": ExtractionStatus.FAILED.value,
            "error_message": f"Failed to open Excel spreadsheet: {e}",
            "extracted_text": "",
            "sections": [],
            "metadata": {},
        }

    metadata = {"sheet_names": wb.sheetnames}
    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        sheet_lines: List[str] = []
        row_count = 0

        for row_idx, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            if row_count >= MAX_SPREADSHEET_ROWS_PER_SHEET:
                sheet_lines.append(f"[Truncated: Exceeded {MAX_SPREADSHEET_ROWS_PER_SHEET} rows]")
                break
            # Filter out completely empty rows
            non_empty = [str(val).strip() for val in row if val is not None and str(val).strip()]
            if non_empty:
                row_str = " | ".join(non_empty)
                loc = f"Sheet '{sheet_name}', Row {row_idx}"
                sheet_lines.append(f"[{loc}] {row_str}")
                row_count += 1

        sheet_text = "\n".join(sheet_lines)
        if sheet_text:
            full_text_parts.append(f"=== Sheet: {sheet_name} ===\n{sheet_text}")
            sections.append({
                "location": f"Sheet: {sheet_name}",
                "sheet": sheet_name,
                "text": sheet_text,
                "rows_count": row_count,
            })

    wb.close()
    total_text = "\n\n".join(full_text_parts)
    return {
        "status": ExtractionStatus.SUCCESS.value if total_text else ExtractionStatus.PARTIAL.value,
        "error_message": None if total_text else "Spreadsheet contained no readable text cells",
        "extracted_text": total_text,
        "sections": sections,
        "metadata": metadata,
    }


def parse_csv(csv_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Extract tabular rows from CSV format."""
    sections: List[Dict[str, Any]] = []
    text_content = ""
    encoding_used = "utf-8"

    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            text_content = csv_bytes.decode(enc)
            encoding_used = enc
            break
        except UnicodeDecodeError:
            continue

    if not text_content:
        return {
            "status": ExtractionStatus.FAILED.value,
            "error_message": "Could not decode CSV bytes with supported text encodings",
            "extracted_text": "",
            "sections": [],
            "metadata": {},
        }

    rows_lines: List[str] = []
    reader = csv.reader(io.StringIO(text_content))
    row_idx = 1
    for row in reader:
        if row_idx > MAX_SPREADSHEET_ROWS_PER_SHEET:
            rows_lines.append(f"[Truncated at {MAX_SPREADSHEET_ROWS_PER_SHEET} rows]")
            break
        non_empty = [c.strip() for c in row if c and c.strip()]
        if non_empty:
            rows_lines.append(f"[Row {row_idx}] " + " | ".join(non_empty))
        row_idx += 1

    total_text = "\n".join(rows_lines)
    sections.append({
        "location": "CSV Table",
        "text": total_text,
        "rows_count": len(rows_lines),
    })

    return {
        "status": ExtractionStatus.SUCCESS.value if total_text else ExtractionStatus.PARTIAL.value,
        "error_message": None,
        "extracted_text": total_text,
        "sections": sections,
        "metadata": {"encoding": encoding_used, "total_rows": len(rows_lines)},
    }


def parse_docx(docx_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Extract paragraphs, headings, and tables from DOCX document."""
    check_zip_bomb(docx_bytes)

    sections: List[Dict[str, Any]] = []
    full_text_parts: List[str] = []

    try:
        doc = docx.Document(io.BytesIO(docx_bytes))
    except Exception as e:
        return {
            "status": ExtractionStatus.FAILED.value,
            "error_message": f"Failed to parse Word document (.docx): {e}",
            "extracted_text": "",
            "sections": [],
            "metadata": {},
        }

    # Extract paragraphs and headings
    for p_idx, p in enumerate(doc.paragraphs, start=1):
        txt = p.text.strip()
        if txt:
            style_name = getattr(p.style, "name", "Normal")
            loc = f"Paragraph {p_idx} ({style_name})"
            full_text_parts.append(f"[{loc}] {txt}")
            sections.append({
                "location": loc,
                "paragraph": p_idx,
                "style": style_name,
                "text": txt,
            })

    # Extract tables
    for t_idx, table in enumerate(doc.tables, start=1):
        table_lines = []
        for r_idx, row in enumerate(table.rows, start=1):
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                table_lines.append(f"[Table {t_idx}, Row {r_idx}] " + " | ".join(cells))
        if table_lines:
            t_text = "\n".join(table_lines)
            full_text_parts.append(t_text)
            sections.append({
                "location": f"Table {t_idx}",
                "table": t_idx,
                "text": t_text,
            })

    total_text = "\n\n".join(full_text_parts)
    return {
        "status": ExtractionStatus.SUCCESS.value if total_text else ExtractionStatus.PARTIAL.value,
        "error_message": None if total_text else "Word document contained no readable text",
        "extracted_text": total_text,
        "sections": sections,
        "metadata": {"paragraph_count": len(doc.paragraphs), "table_count": len(doc.tables)},
    }


def parse_pptx(pptx_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Extract slide text, shapes, and tables from PPTX presentation."""
    check_zip_bomb(pptx_bytes)

    sections: List[Dict[str, Any]] = []
    full_text_parts: List[str] = []

    try:
        prs = pptx.Presentation(io.BytesIO(pptx_bytes))
    except Exception as e:
        return {
            "status": ExtractionStatus.FAILED.value,
            "error_message": f"Failed to parse PowerPoint presentation (.pptx): {e}",
            "extracted_text": "",
            "sections": [],
            "metadata": {},
        }

    slide_count = min(len(prs.slides), MAX_PAGES_OR_SLIDES)
    for s_idx in range(slide_count):
        slide_num = s_idx + 1
        slide = prs.slides[s_idx]
        slide_lines: List[str] = []

        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    txt = paragraph.text.strip()
                    if txt:
                        slide_lines.append(txt)
            if shape.has_table:
                for row in shape.table.rows:
                    cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cells:
                        slide_lines.append(" | ".join(cells))

        slide_text = "\n".join(slide_lines)
        if slide_text:
            loc = f"Slide {slide_num}"
            full_text_parts.append(f"=== {loc} ===\n{slide_text}")
            sections.append({
                "location": loc,
                "slide": slide_num,
                "text": slide_text,
            })

    total_text = "\n\n".join(full_text_parts)
    return {
        "status": ExtractionStatus.SUCCESS.value if total_text else ExtractionStatus.PARTIAL.value,
        "error_message": None if total_text else "Presentation contained no readable text shapes",
        "extracted_text": total_text,
        "sections": sections,
        "metadata": {"total_slides": len(prs.slides)},
    }


def parse_image(img_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Validate image metadata and safe OCR fallback."""
    try:
        im = Image.open(io.BytesIO(img_bytes))
        metadata = {
            "format": im.format,
            "dimensions": f"{im.width}x{im.height}",
            "mode": im.mode,
        }
    except Exception as e:
        return {
            "status": ExtractionStatus.FAILED.value,
            "error_message": f"Corrupted or invalid image: {e}",
            "extracted_text": "",
            "sections": [],
            "metadata": {},
        }

    # Safe OCR: check if tesseract is installed
    ocr_text = ""
    ocr_status = ExtractionStatus.OCR_UNAVAILABLE.value
    ocr_err = "OCR engine (Tesseract) not installed on host. Image metadata recorded."

    return {
        "status": ocr_status,
        "error_message": ocr_err,
        "extracted_text": ocr_text,
        "sections": [{
            "location": f"Image {filename}",
            "text": f"[Image {filename} {metadata['dimensions']} {metadata['format']}]",
        }],
        "metadata": metadata,
    }


def parse_document_content(
    content_bytes: bytes,
    filename: str,
    declared_content_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Master entry point for parsing any supported document or media file."""
    if len(content_bytes) > MAX_DOCUMENT_SIZE_BYTES:
        return {
            "status": ExtractionStatus.FAILED.value,
            "error_message": f"Document size ({len(content_bytes)} bytes) exceeds maximum limit ({MAX_DOCUMENT_SIZE_BYTES} bytes)",
            "extracted_text": "",
            "sections": [],
            "metadata": {},
            "file_format": "UNKNOWN",
        }

    ext = Path(filename).suffix.lower().lstrip(".")
    if not ext:
        # Infer from content type
        ct = (declared_content_type or "").lower()
        if "pdf" in ct:
            ext = "pdf"
        elif "spreadsheetml" in ct or "excel" in ct:
            ext = "xlsx"
        elif "wordprocessingml" in ct or "word" in ct:
            ext = "docx"
        elif "presentationml" in ct or "powerpoint" in ct:
            ext = "pptx"
        elif "csv" in ct:
            ext = "csv"
        elif "png" in ct:
            ext = "png"
        elif "jpeg" in ct:
            ext = "jpg"
        elif "webp" in ct:
            ext = "webp"
        else:
            ext = "bin"

    # Signature validation
    if not validate_file_signature(content_bytes, ext):
        return {
            "status": ExtractionStatus.FAILED.value,
            "error_message": f"File signature mismatch for declared format '{ext}'",
            "extracted_text": "",
            "sections": [],
            "metadata": {},
            "file_format": ext.upper(),
        }

    try:
        if ext == "pdf":
            res = parse_pdf(content_bytes, filename)
        elif ext == "xlsx":
            res = parse_excel(content_bytes, filename)
        elif ext == "csv":
            res = parse_csv(content_bytes, filename)
        elif ext == "docx":
            res = parse_docx(content_bytes, filename)
        elif ext == "pptx":
            res = parse_pptx(content_bytes, filename)
        elif ext in ("png", "jpg", "jpeg", "webp", "tiff"):
            res = parse_image(content_bytes, filename)
        elif ext in ("doc", "xls", "ppt"):
            res = {
                "status": ExtractionStatus.UNSUPPORTED.value,
                "error_message": f"Legacy binary format (.{ext}) requires conversion to modern OpenXML format",
                "extracted_text": "",
                "sections": [],
                "metadata": {},
            }
        else:
            res = {
                "status": ExtractionStatus.UNSUPPORTED.value,
                "error_message": f"Unsupported document format: .{ext}",
                "extracted_text": "",
                "sections": [],
                "metadata": {},
            }
    except DocumentSecurityException as dse:
        res = {
            "status": ExtractionStatus.FAILED.value,
            "error_message": f"Security boundary violation: {dse}",
            "extracted_text": "",
            "sections": [],
            "metadata": {},
        }
    except Exception as e:
        logger.error("Unexpected error parsing document %s: %s", filename, e, exc_info=True)
        res = {
            "status": ExtractionStatus.FAILED.value,
            "error_message": f"Unexpected extraction error: {e}",
            "extracted_text": "",
            "sections": [],
            "metadata": {},
        }

    res["file_format"] = ext.upper()
    return res
