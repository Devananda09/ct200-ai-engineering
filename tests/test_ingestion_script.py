from pathlib import Path
import pytest
from app.db import DocumentNodeRecord, DocumentVersionRecord, SessionLocal
from scripts.ingest_manuals import main

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
V1_PATH = DATA_DIR / "ct200_manual.pdf"
V2_PATH = DATA_DIR / "ct200_manual_v2.pdf"


def test_cli_ingestion_script(monkeypatch, tmp_path):
    if not V1_PATH.exists() or not V2_PATH.exists():
        pytest.skip("PDF manuals not found")

    out_dir = tmp_path / "output"

    # Mock sys.argv to run main() with custom output directory
    monkeypatch.setattr(
        "sys.argv",
        [
            "ingest_manuals.py",
            "--v1",
            str(V1_PATH),
            "--v2",
            str(V2_PATH),
            "--output-dir",
            str(out_dir),
        ],
    )

    main()

    # Verify JSON summaries were exported
    assert (out_dir / "parsed_v1.json").exists()
    assert (out_dir / "parsed_v2.json").exists()
    assert (out_dir / "version_diff.json").exists()

    # Verify database persistence
    db = SessionLocal()
    try:
        v1_ver = db.query(DocumentVersionRecord).filter_by(id="v1").first()
        v2_ver = db.query(DocumentVersionRecord).filter_by(id="v2").first()
        assert v1_ver is not None
        assert v2_ver is not None
        assert v1_ver.total_pages == 6

        v1_nodes = db.query(DocumentNodeRecord).filter_by(version="v1").all()
        v2_nodes = db.query(DocumentNodeRecord).filter_by(version="v2").all()
        assert len(v1_nodes) > 0
        assert len(v2_nodes) > 0

        # Section 5.3 should exist in v2 nodes, but not in v1
        v1_ids = [n.node_id for n in v1_nodes]
        v2_ids = [n.node_id for n in v2_nodes]
        assert "5.3" not in v1_ids
        assert "5.3" in v2_ids
    finally:
        db.close()
