from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class ManualOverview(BaseModel):
    version: str
    title: str
    total_pages: int
    sections_count: int
    parameters_count: int
    error_codes_count: int


class Citation(BaseModel):
    document_id: str
    section_number: str
    section_title: str
    page_number: int
    snippet: str
    relevance_score: float


class QueryAnswer(BaseModel):
    query: str
    target_version: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = 1.0
