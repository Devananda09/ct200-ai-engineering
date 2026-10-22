#!/usr/bin/env python3
"""
CLI script to ingest and parse CardioTrack CT-200 technical manuals (v1 & v2),
perform hierarchical extraction, calculate version diffs, and export structured JSON data.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from parser.comparator import DocumentComparator
from parser.reconstructor import HierarchyReconstructor


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

    print(f"Parsing v1 from: {v1_path}")
    doc_v1 = HierarchyReconstructor(v1_path, "v1").build_document()
    print(f" -> Extracted {len(doc_v1.sections)} sections, {len(doc_v1.parameters)} parameters, {len(doc_v1.error_codes)} error codes across {doc_v1.total_pages} pages.")

    print(f"\nParsing v2 from: {v2_path}")
    doc_v2 = HierarchyReconstructor(v2_path, "v2").build_document()
    print(f" -> Extracted {len(doc_v2.sections)} sections, {len(doc_v2.parameters)} parameters, {len(doc_v2.error_codes)} error codes across {doc_v2.total_pages} pages.")

    print("\nComputing Version Differences...")
    comparison = DocumentComparator.compare(doc_v1, doc_v2)

    print(f"\nKey Changes Summary ({len(comparison.summary_points)} items):")
    for pt in comparison.summary_points:
        print(f" - {pt}")

    # Export structured JSON
    v1_out = out_dir / "parsed_v1.json"
    v2_out = out_dir / "parsed_v2.json"
    diff_out = out_dir / "version_diff.json"

    with open(v1_out, "w", encoding="utf-8") as f:
        json.dump(doc_v1.model_dump(), f, indent=2)
    with open(v2_out, "w", encoding="utf-8") as f:
        json.dump(doc_v2.model_dump(), f, indent=2)
    with open(diff_out, "w", encoding="utf-8") as f:
        json.dump(comparison.model_dump(), f, indent=2)

    print(f"\nSaved structured outputs to {out_dir}:")
    print(f" - {v1_out.name}")
    print(f" - {v2_out.name}")
    print(f" - {diff_out.name}")
    print("\nIngestion complete!")


if __name__ == "__main__":
    main()
