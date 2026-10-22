from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from parser.hierarchy import build_hierarchy, find_node
from parser.models import (
    DocumentSection,
    ErrorCodeItem,
    ParsedDocument,
    SpecificationParameter,
)
from parser.pdf_parser import extract_pdf, extract_tables

logger = logging.getLogger(__name__)




def normalize_text(text: str) -> str:
    """Normalize unicode ligatures, non-breaking hyphens, and whitespace."""
    replacements = {
        "ﬁ": "fi",
        "ﬂ": "fl",
        "ﬀ": "ff",
        "ﬃ": "ffi",
        "ﬄ": "ffl",
        "‑": "-",
        "–": "-",
        "—": "-",
        "\u00a0": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


class ParserService:
    """Service to load, parse, and cache CT-200 technical manuals using extract_pdf."""

    SECTION_HEADER_RE = re.compile(
        r"^([0-9]+(?:\.[0-9]+)*)\.?\s+([A-Z][A-Za-z0-9\s,\-–—/()]+)$"
    )

    def __init__(self, v1_path: Path, v2_path: Path):
        self.v1_path = Path(v1_path)
        self.v2_path = Path(v2_path)
        self._doc_v1: Optional[ParsedDocument] = None
        self._doc_v2: Optional[ParsedDocument] = None

    def initialize(self) -> None:
        """Parse both manuals and cache them in memory."""
        if self.v1_path.exists():
            try:
                self._doc_v1 = self._parse_manual(self.v1_path, version="v1")
                logger.info(f"Loaded v1 manual: {len(self._doc_v1.sections)} sections")
            except Exception as e:
                logger.error(f"Failed to parse v1 manual at {self.v1_path}: {e}")
        else:
            logger.warning(f"v1 manual not found at {self.v1_path}")

        if self.v2_path.exists():
            try:
                self._doc_v2 = self._parse_manual(self.v2_path, version="v2")
                logger.info(f"Loaded v2 manual: {len(self._doc_v2.sections)} sections")
            except Exception as e:
                logger.error(f"Failed to parse v2 manual at {self.v2_path}: {e}")
        else:
            logger.warning(f"v2 manual not found at {self.v2_path}")

    @property
    def doc_v1(self) -> Optional[ParsedDocument]:
        return self._doc_v1

    @property
    def doc_v2(self) -> Optional[ParsedDocument]:
        return self._doc_v2

    def get_document(self, version: str) -> Optional[ParsedDocument]:
        clean = version.lower()
        if "1" in clean:
            return self._doc_v1
        if "2" in clean:
            return self._doc_v2
        return None

    def _parse_manual(self, pdf_path: Path, version: str) -> ParsedDocument:
        # Use user's extract_pdf
        pages = extract_pdf(pdf_path)
        total_pages = len(pages)

        page_texts: list[tuple[int, str]] = []
        raw_text_parts: list[str] = []

        for p in pages:
            p_num = p["page_number"]
            blocks_text = [normalize_text(b["text"]) for b in p.get("blocks", [])]
            page_content = "\n".join(blocks_text)
            page_texts.append((p_num, page_content))
            raw_text_parts.append(f"--- Page {p_num} ---\n{page_content}")

        raw_text = "\n\n".join(raw_text_parts)
        sections = self._extract_sections(page_texts)
        parameters = self._extract_parameters(sections)

        try:
            tables = extract_tables(pdf_path)
        except Exception as e:
            logger.warning(f"Failed to extract tables from {pdf_path}: {e}")
            tables = []

        error_codes = self._extract_error_codes(sections, tables=tables)
        tree = build_hierarchy(sections, tables=tables)

        return ParsedDocument(
            id=f"ct200_{version}",
            title="CardioTrack CT-200 Technical & User Manual",
            version=version,
            total_pages=total_pages,
            sections=sections,
            parameters=parameters,
            error_codes=error_codes,
            tables=tables,
            tree=tree,
            raw_text=raw_text,
        )



    def _extract_sections(self, page_texts: list[tuple[int, str]]) -> list[DocumentSection]:
        current_sec_num: str | None = None
        current_title: str | None = None
        current_start_page = 1
        current_lines: list[str] = []

        sections: list[DocumentSection] = []

        for page_num, text in page_texts:
            for line in text.split("\n"):
                clean = line.strip()
                match = self.SECTION_HEADER_RE.match(clean)
                if match:
                    if current_sec_num is not None:
                        sections.append(
                            DocumentSection(
                                section_number=current_sec_num,
                                title=current_title or "",
                                content="\n".join(current_lines).strip(),
                                page_start=current_start_page,
                                page_end=page_num,
                                level=len(current_sec_num.split(".")),
                            )
                        )
                        current_lines = []
                    current_sec_num = match.group(1)
                    current_title = match.group(2).strip()
                    current_start_page = page_num
                else:
                    if current_sec_num is not None:
                        current_lines.append(clean)

        if current_sec_num is not None:
            last_page = page_texts[-1][0] if page_texts else current_start_page
            sections.append(
                DocumentSection(
                    section_number=current_sec_num,
                    title=current_title or "",
                    content="\n".join(current_lines).strip(),
                    page_start=current_start_page,
                    page_end=last_page,
                    level=len(current_sec_num.split(".")),
                )
            )

        return sections

    def _extract_parameters(self, sections: list[DocumentSection]) -> list[SpecificationParameter]:
        params: list[SpecificationParameter] = []
        for sec in sections:
            if sec.section_number == "2.1":
                lines = [l.strip() for l in sec.content.split("\n") if l.strip()]
                for line in lines:
                    if line.startswith("Parameter") or line.startswith("2.1.1"):
                        continue
                    for known in [
                        "Measurement method",
                        "Pressure range",
                        "Pulse range",
                        "Accuracy (pressure)",
                        "Accuracy (pulse)",
                        "Power source",
                        "Display",
                    ]:
                        if line.startswith(known):
                            val = line[len(known):].strip()
                            params.append(
                                SpecificationParameter(
                                    parameter=known,
                                    value=val,
                                    section="2.1",
                                    page=sec.page_start,
                                )
                            )
            elif sec.section_number == "2.1.1.1":
                match = re.search(r"provide approximately (\d+)\s+measurement cycles", sec.content)
                if match:
                    params.append(
                        SpecificationParameter(
                            parameter="Battery life (cycles)",
                            value=f"{match.group(1)} cycles",
                            section="2.1.1.1",
                            page=sec.page_start,
                        )
                    )
        return params

    def _extract_error_codes(
        self,
        sections: list[DocumentSection],
        tables: list[dict] | None = None,
    ) -> list[ErrorCodeItem]:
        error_codes: list[ErrorCodeItem] = []

        # 1. Try extracting directly from structured PDF table
        if tables:
            for tab in tables:
                headers = tab.get("headers", [])
                if any("Code" in h for h in headers):
                    for row in tab.get("rows", []):
                        if len(row) >= 3 and re.match(r"^E\d+", row[0].strip()):
                            code = row[0].strip()
                            meaning = " ".join(row[1].split())
                            behavior = " ".join(row[2].split())
                            error_codes.append(
                                ErrorCodeItem(
                                    code=code,
                                    meaning=meaning,
                                    device_behavior=behavior,
                                    page=tab.get("page_number", 4),
                                )
                            )
            if error_codes:
                return error_codes

        # 2. Fallback to text parsing
        for sec in sections:
            if sec.section_number == "4.2":
                lines = [l.strip() for l in sec.content.split("\n") if l.strip()]
                code_pattern = re.compile(r"^(E[1-6])(?:\s+(.+))?$")
                curr_code: str | None = None
                curr_meaning: str = ""
                curr_behavior: str = ""

                for line in lines:
                    m = code_pattern.match(line)
                    if m:
                        if curr_code:
                            error_codes.append(
                                ErrorCodeItem(
                                    code=curr_code,
                                    meaning=curr_meaning.strip(),
                                    device_behavior=curr_behavior.strip(),
                                    page=sec.page_start,
                                )
                            )
                        curr_code = m.group(1)
                        curr_meaning = m.group(2) or ""
                        curr_behavior = ""
                    elif curr_code:
                        if not curr_meaning:
                            curr_meaning = line
                        elif not curr_behavior:
                            curr_behavior = line
                        else:
                            curr_behavior += " " + line

                if curr_code:
                    error_codes.append(
                        ErrorCodeItem(
                            code=curr_code,
                            meaning=curr_meaning.strip(),
                            device_behavior=curr_behavior.strip(),
                            page=sec.page_start,
                        )
                    )
        return error_codes


    def find_node_by_id(self, tree: list, node_id: str):
        from parser.hierarchy import find_node
        return find_node(tree, node_id)

