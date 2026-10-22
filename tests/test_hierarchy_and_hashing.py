from pathlib import Path
import pytest
from parser.hierarchy import build_hierarchy
from parser.models import DocumentSection, DocumentNode
from parser.pdf_parser import extract_pdf, extract_tables
from app.services.parser_service import ParserService

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
V1_PATH = DATA_DIR / "ct200_manual.pdf"
V2_PATH = DATA_DIR / "ct200_manual_v2.pdf"


def test_table_extraction():
    if not V1_PATH.exists():
        pytest.skip("PDF not found")
    tables = extract_tables(V1_PATH)
    assert len(tables) >= 2  # Specs table on p2, Error codes table on p4
    table_headers = [t["headers"] for t in tables]
    assert any("Parameter" in h for h in table_headers)
    assert any("Code" in h for h in table_headers)


def test_missing_parent_hierarchy_building():
    """
    Test that structural irregularities (such as 2.1.1.1 without a 2.1.1 parent)
    are handled gracefully by falling back to the nearest existing ancestor (2.1).
    """
    sections = [
        DocumentSection(section_number="2", title="Specifications", page_start=2, page_end=2),
        DocumentSection(section_number="2.1", title="Electrical Specifications", page_start=2, page_end=2),
        DocumentSection(
            section_number="2.1.1.1",
            title="Battery Requirements",
            page_start=2,
            page_end=2,
            content="Operates on 4x AA batteries. Minimum 300 cycles.",
        ),
    ]


    tree = build_hierarchy(sections)
    assert len(tree) == 1
    root = tree[0]
    assert root.node_id == "2"
    assert len(root.children) == 1

    child_2_1 = root.children[0]
    assert child_2_1.node_id == "2.1"
    # 2.1.1.1 should safely attach to 2.1 even though 2.1.1 was missing
    assert len(child_2_1.children) == 1
    child_2_1_1_1 = child_2_1.children[0]
    assert child_2_1_1_1.node_id == "2.1.1.1"
    assert child_2_1_1_1.parent_id == "2.1"
    assert child_2_1_1_1.content_hash != ""


def test_content_hashing_determinism():
    """
    Verify that node content hash is deterministic and changes when text changes.
    """
    sec_a = DocumentSection(section_number="1.0", title="Intro", content="Sample body text")
    sec_b = DocumentSection(section_number="1.0", title="Intro", content="Sample body text")
    sec_c = DocumentSection(section_number="1.0", title="Intro", content="Modified body text")

    tree_a = build_hierarchy([sec_a])
    tree_b = build_hierarchy([sec_b])
    tree_c = build_hierarchy([sec_c])

    assert tree_a[0].content_hash == tree_b[0].content_hash
    assert tree_a[0].content_hash != tree_c[0].content_hash


def test_v1_v2_node_hash_comparisons():
    if not V1_PATH.exists() or not V2_PATH.exists():
        pytest.skip("PDF files not found")

    ps = ParserService(v1_path=V1_PATH, v2_path=V2_PATH)
    ps.initialize()

    # Section 1 (Overview) should have the exact same hash (unchanged)
    node1_v1 = ps.find_node_by_id(ps.doc_v1.tree, "1")
    node1_v2 = ps.find_node_by_id(ps.doc_v2.tree, "1")
    assert node1_v1 is not None and node1_v2 is not None
    assert node1_v1.content_hash == node1_v2.content_hash


    # Section 2.1.1.1 (Battery specs changed from 300 to 250 cycles) should have different hashes
    node_bat_v1 = ps.find_node_by_id(ps.doc_v1.tree, "2.1.1.1")
    node_bat_v2 = ps.find_node_by_id(ps.doc_v2.tree, "2.1.1.1")
    assert node_bat_v1 is not None and node_bat_v2 is not None
    assert node_bat_v1.content_hash != node_bat_v2.content_hash

    # Section 5.3 (Data Export) was added in v2 only
    assert ps.find_node_by_id(ps.doc_v1.tree, "5.3") is None
    assert ps.find_node_by_id(ps.doc_v2.tree, "5.3") is not None
