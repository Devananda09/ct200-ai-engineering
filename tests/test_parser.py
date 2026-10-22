from pathlib import Path
import pytest

from app.services.diff_service import DocumentComparator
from app.services.parser_service import ParserService
from app.services.rag_service import DocumentChunker
from parser.pdf_parser import extract_pdf

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
V1_PATH = DATA_DIR / "ct200_manual.pdf"
V2_PATH = DATA_DIR / "ct200_manual_v2.pdf"


def test_extract_pdf_blocks():
    if not V1_PATH.exists():
        pytest.skip("data/ct200_manual.pdf not found")

    pages = extract_pdf(V1_PATH)
    assert len(pages) > 0
    assert "page_number" in pages[0]
    assert "blocks" in pages[0]
    assert len(pages[0]["blocks"]) > 0
    assert "bbox" in pages[0]["blocks"][0]
    assert "text" in pages[0]["blocks"][0]


def test_parser_service():
    if not V1_PATH.exists():
        pytest.skip("data/ct200_manual.pdf not found")

    ps = ParserService(v1_path=V1_PATH, v2_path=V2_PATH)
    ps.initialize()
    doc = ps.doc_v1
    assert doc is not None

    assert doc.id == "ct200_v1"
    assert doc.total_pages == 6
    assert len(doc.sections) > 0
    sec1 = next((s for s in doc.sections if s.section_number == "1"), None)
    assert sec1 is not None
    assert "Device Overview" in sec1.title


def test_chunker():
    if not V1_PATH.exists():
        pytest.skip("data/ct200_manual.pdf not found")

    ps = ParserService(v1_path=V1_PATH, v2_path=V2_PATH)
    ps.initialize()
    doc = ps.doc_v1
    assert doc is not None

    chunker = DocumentChunker(max_words_per_chunk=100, overlap_words=20)
    chunks = chunker.chunk_document(doc)

    assert len(chunks) > 0
    assert all(c.document_id == "ct200_v1" for c in chunks)


def test_version_comparator():
    if not V1_PATH.exists() or not V2_PATH.exists():
        pytest.skip("Manual PDFs not found")

    ps = ParserService(v1_path=V1_PATH, v2_path=V2_PATH)
    ps.initialize()
    doc_v1 = ps.doc_v1
    doc_v2 = ps.doc_v2
    assert doc_v1 is not None and doc_v2 is not None

    comp = DocumentComparator.compare(doc_v1, doc_v2)

    assert "5.3" in comp.sections_added  # Data Export added in v2
    assert len(comp.sections_modified) > 0
    assert len(comp.summary_points) > 0

