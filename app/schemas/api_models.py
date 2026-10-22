from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field

from app.models.domain import Citation, ManualOverview
from parser.models import (
    DocumentComparisonResult,
    DocumentSection,
    ErrorCodeItem,
    SpecificationParameter,
)


class HealthResponse(BaseModel):
    status: str = "ok"
    app: str = "ct200-ai-engineering"
    environment: str
    v1_loaded: bool
    v2_loaded: bool


class ManualListResponse(BaseModel):
    manuals: list[ManualOverview]


class ManualDetailResponse(BaseModel):
    version: str
    title: str
    total_pages: int
    sections: list[DocumentSection]
    parameters: list[SpecificationParameter]
    error_codes: list[ErrorCodeItem]


class DiffResponse(BaseModel):
    comparison: DocumentComparisonResult


class QueryRequest(BaseModel):
    query: str = Field(..., description="Technical question about CT-200 blood pressure monitor")
    version: str = Field(default="v2", description="Target manual version ('v1', 'v2', or 'both')")
    max_citations: int = Field(default=3, ge=1, le=10)


class QueryResponse(BaseModel):
    query: str
    target_version: str
    answer: str
    citations: list[Citation]
    confidence: float
