from pathlib import Path
from typing import Any

import fitz


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

    document = fitz.open(pdf_path)

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

    finally:
        document.close()

    return pages


def extract_all_text(pdf_path: str | Path) -> str:
    """
    Convenience function that returns the complete extracted text.
    """

    pages = extract_pdf(pdf_path)

    output: list[str] = []

    for page in pages:
        output.append(f"\n--- PAGE {page['page_number']} ---\n")

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
        print(f"========== PAGE {page['page_number']} ==========")

        for block in page["blocks"]:
            print(block["text"])
            print()