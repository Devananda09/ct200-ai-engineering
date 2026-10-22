from pathlib import Path
from typing import Any
import logging

import pymupdf


logger = logging.getLogger("ct200_parser")


def extract_pdf(pdf_path: str | Path) -> list[dict[str, Any]]:
    """
    Extract text blocks from a PDF.

    Each block keeps:
    - page number
    - text
    - bounding box

    Bounding boxes are important because later we can use
    the position of text to help reconstruct document structure.
    """

    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    document = pymupdf.open(pdf_path)

    pages: list[dict[str, Any]] = []

    try:
        for page_number, page in enumerate(document, start=1):
            blocks = page.get_text("blocks")

            page_blocks = []

            for block in blocks:
                x0, y0, x1, y1, text, *_ = block

                text = text.strip()

                if not text:
                    continue

                page_blocks.append(
                    {
                        "text": text,
                        "bbox": [
                            round(x0, 2),
                            round(y0, 2),
                            round(x1, 2),
                            round(y1, 2),
                        ],
                    }
                )

            pages.append(
                {
                    "page_number": page_number,
                    "blocks": page_blocks,
                }
            )

        # Detect scanned / image-only PDFs.
        total_extracted_blocks = sum(
            len(page.get("blocks", []))
            for page in pages
        )

        if len(document) > 0 and total_extracted_blocks == 0:
            logger.warning(
                f"Document at {pdf_path} contains {len(document)} pages "
                "but 0 text blocks. The file appears to be a scanned "
                "image-only PDF requiring OCR pre-processing."
            )

    finally:
        document.close()

    return pages


def extract_tables(pdf_path: str | Path) -> list[dict[str, Any]]:
    """
    Extract structured tables from PDF using PyMuPDF table detection.

    Returns a list of dictionaries containing:
    - page_number
    - bbox
    - headers
    - rows
    """

    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    document = pymupdf.open(pdf_path)

    extracted: list[dict[str, Any]] = []

    try:
        for page_number, page in enumerate(document, start=1):
            tab_finder = page.find_tables()

            for tab in tab_finder.tables:
                raw_rows = tab.extract()

                if not raw_rows or len(raw_rows) < 2:
                    continue

                header = [
                    str(col).strip() if col is not None else ""
                    for col in raw_rows[0]
                ]

                rows = [
                    [
                        str(cell).strip() if cell is not None else ""
                        for cell in row
                    ]
                    for row in raw_rows[1:]
                ]

                extracted.append(
                    {
                        "page_number": page_number,
                        "bbox": [
                            round(coord, 2)
                            for coord in tab.bbox
                        ],
                        "headers": header,
                        "rows": rows,
                    }
                )

    finally:
        document.close()

    return extracted


def extract_all_text(pdf_path: str | Path) -> str:
    """
    Convenience function that returns the complete extracted text.
    """

    pages = extract_pdf(pdf_path)

    output: list[str] = []

    for page in pages:
        output.append(
            f"\n--- PAGE {page['page_number']} ---\n"
        )

        for block in page["blocks"]:
            output.append(block["text"])

    return "\n".join(output)


if __name__ == "__main__":
    pdf_file = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "ct200_manual.pdf"
    )

    pages = extract_pdf(pdf_file)

    print(f"\nExtracted {len(pages)} pages.\n")

    for page in pages:
        print(
            f"========== PAGE {page['page_number']} =========="
        )

        for block in page["blocks"]:
            print(block["text"])
            print()