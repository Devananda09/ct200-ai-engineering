from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TextBlock:
    page_number: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class DocumentSection:
    section_number: str
    title: str
    content: str = ""
    page_start: int = 1
    page_end: int = 1
    level: int = 1
    parent_section: Optional[str] = None
    children: list[str] = field(default_factory=list)


@dataclass
class SpecificationParameter:
    parameter: str
    value: str
    section: str = ""
    page: Optional[int] = None


@dataclass
class ErrorCodeItem:
    code: str
    meaning: str
    device_behavior: str
    page: Optional[int] = None


@dataclass
class Section:
    section_number: str
    title: str
    content: str = ""
    level: int = 1
    page_number: Optional[int] = None
    parent_section: Optional[str] = None
    children: list[str] = field(default_factory=list)


@dataclass
class ParameterDiff:
    parameter: str
    status: str
    v1_value: Optional[str]
    v2_value: Optional[str]
    details: str


@dataclass
class SectionDiff:
    section_number: str
    title: str
    status: str
    v1_content: Optional[str]
    v2_content: Optional[str]
    changes_summary: list[str] = field(default_factory=list)


@dataclass
class ParsedDocument:
    id: str
    version: str

    title: str = ""
    total_pages: int = 0

    sections: list[DocumentSection] = field(default_factory=list)

    parameters: list[SpecificationParameter] = field(
        default_factory=list
    )

    error_codes: list[ErrorCodeItem] = field(
        default_factory=list
    )

    raw_text: str = ""


@dataclass
class DocumentComparisonResult:
    doc_v1_id: str
    doc_v2_id: str

    sections_added: list[str] = field(default_factory=list)
    sections_removed: list[str] = field(default_factory=list)
    sections_modified: list[str] = field(default_factory=list)

    section_diffs: list[SectionDiff] = field(
        default_factory=list
    )

    parameter_diffs: list[ParameterDiff] = field(
        default_factory=list
    )

    summary_points: list[str] = field(
        default_factory=list
    )


@dataclass
class DocumentNode:
    """
    Hierarchical document node.

    Used by the hierarchy parser and later retrieval APIs.
    """

    node_id: str
    heading: str
    level: int

    body_text: str = ""

    page_number: Optional[int] = None
    parent_id: Optional[str] = None

    children: list["DocumentNode"] = field(
        default_factory=list
    )


@dataclass
class DocumentChunk:
    chunk_id: str
    document_id: str
    section_number: str
    section_title: str
    page_number: int
    text: str
    token_count: int