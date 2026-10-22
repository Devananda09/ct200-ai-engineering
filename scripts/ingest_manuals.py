#!/usr/bin/env python3
"""
CLI script to ingest and parse CardioTrack CT-200 technical manuals (v1 & v2),
perform hierarchical extraction, calculate version diffs, persist records to SQLite database,
and export structured summary statistics.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from app.db import (
    DocumentNodeRecord,
    DocumentVersionRecord,
    SessionLocal,
    init_db,
)
from app.services.diff_service import DocumentComparator
from app.services.parser_service import ParserService
from parser.hierarchy import build_hierarchy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ingest_manuals")


def persist_manual_to_db(db, version: str, title: str, total_pages: int, tree_nodes):
    """Upsert DocumentVersionRecord and DocumentNodeRecord into SQLite."""
    # Check if version record exists
    ver_rec = db.query(DocumentVersionRecord).filter_by(id=version).first()
    if not ver_rec:
        ver_rec = DocumentVersionRecord(
            id=version,
            title=title,
            total_pages=total_pages,
        )
        db.add(ver_rec)
        db.commit()
    else:
        ver_rec.title = title
        ver_rec.total_pages = total_pages
        db.commit()

    # Remove previous nodes for clean re-ingestion without duplicate keys
    db.query(DocumentNodeRecord).filter_by(version=version).delete()
    db.commit()

    def _persist_nodes(nodes, parent_id: str | None = None):
        for node in nodes:
            node_rec = DocumentNodeRecord(
                version=version,
                node_id=node.node_id,
                heading=node.heading,
                level=node.level,
                body_text=node.body_text,
                page_number=node.page_number,
                parent_id=parent_id or node.parent_id,
                content_hash=node.content_hash,
                tables_json=json.dumps(node.tables) if node.tables else None,
            )
            db.add(node_rec)
            if node.children:
                _persist_nodes(node.children, parent_id=node.node_id)

    _persist_nodes(tree_nodes)
    db.commit()


def main():
    parser = argparse.ArgumentParser(description="Ingest and parse CT-200 PDF manuals.")
    parser.add_argument("--v1", default="data/ct200_manual.pdf", help="Path to CT-200 manual v1 PDF")
    parser.add_argument("--v2", default="data/ct200_manual_v2.pdf", help="Path to CT-200 manual v2 PDF")
    parser.add_argument("--output-dir", default="data", help="Output directory for structured JSON")
    args = parser.parse_args()

    v1_path = Path(args.v1)
    v2_path = Path(args.v2)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("==================================================")
    print("      CardioTrack CT-200 Manual Ingestion")
    print("==================================================")

    if not v1_path.exists():
        print(f"[Error] v1 PDF not found: {v1_path}")
        return
    if not v2_path.exists():
        print(f"[Error] v2 PDF not found: {v2_path}")
        return

    # Initialize database
    init_db()
    db = SessionLocal()

    try:
        ps = ParserService(v1_path=v1_path, v2_path=v2_path)
        ps.initialize()

        doc_v1 = ps.doc_v1
        doc_v2 = ps.doc_v2

        if not doc_v1 or not doc_v2:
            print("[Error] Failed to parse one or both manuals.")
            return

        print(f"\n[v1 Ingestion]")
        print(f"  Source: {v1_path}")
        print(f"  Total Pages: {doc_v1.total_pages}")
        print(f"  Sections Extracted: {len(doc_v1.sections)}")
        print(f"  Tables Extracted: {len(doc_v1.tables)}")
        tree_v1 = build_hierarchy(doc_v1.sections, tables=doc_v1.tables)
        persist_manual_to_db(db, "v1", doc_v1.title, doc_v1.total_pages, tree_v1)
        print(f"  Persisted v1 to database successfully.")

        print(f"\n[v2 Ingestion]")
        print(f"  Source: {v2_path}")
        print(f"  Total Pages: {doc_v2.total_pages}")
        print(f"  Sections Extracted: {len(doc_v2.sections)}")
        print(f"  Tables Extracted: {len(doc_v2.tables)}")
        tree_v2 = build_hierarchy(doc_v2.sections, tables=doc_v2.tables)
        persist_manual_to_db(db, "v2", doc_v2.title, doc_v2.total_pages, tree_v2)
        print(f"  Persisted v2 to database successfully.")

        print("\n[Version Diff Analysis]")
        comparison = DocumentComparator.compare(doc_v1, doc_v2)
        print(f"  Sections Added: {len(comparison.sections_added)} -> {comparison.sections_added}")
        print(f"  Sections Removed: {len(comparison.sections_removed)} -> {comparison.sections_removed}")
        print(f"  Sections Modified: {len(comparison.sections_modified)} -> {comparison.sections_modified}")
        print(f"  Key Change Summaries ({len(comparison.summary_points)}):")
        for pt in comparison.summary_points[:8]:
            print(f"   • {pt}")
        if len(comparison.summary_points) > 8:
            print(f"   • ... and {len(comparison.summary_points) - 8} more changes.")

        # Export structured JSON summaries
        v1_out = out_dir / "parsed_v1.json"
        v2_out = out_dir / "parsed_v2.json"
        diff_out = out_dir / "version_diff.json"

        with open(v1_out, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "id": doc_v1.id,
                    "title": doc_v1.title,
                    "version": doc_v1.version,
                    "total_pages": doc_v1.total_pages,
                    "sections_count": len(doc_v1.sections),
                    "parameters_count": len(doc_v1.parameters),
                    "error_codes_count": len(doc_v1.error_codes),
                    "tables_count": len(doc_v1.tables),
                },
                f,
                indent=2,
            )

        with open(v2_out, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "id": doc_v2.id,
                    "title": doc_v2.title,
                    "version": doc_v2.version,
                    "total_pages": doc_v2.total_pages,
                    "sections_count": len(doc_v2.sections),
                    "parameters_count": len(doc_v2.parameters),
                    "error_codes_count": len(doc_v2.error_codes),
                    "tables_count": len(doc_v2.tables),
                },
                f,
                indent=2,
            )

        with open(diff_out, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "doc_v1_id": comparison.doc_v1_id,
                    "doc_v2_id": comparison.doc_v2_id,
                    "sections_added": comparison.sections_added,
                    "sections_removed": comparison.sections_removed,
                    "sections_modified": comparison.sections_modified,
                    "summary_points": comparison.summary_points,
                },
                f,
                indent=2,
            )

        print(f"\nStructured summary JSON files exported to: {out_dir}")
        print("Ingestion pipeline completed successfully.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
