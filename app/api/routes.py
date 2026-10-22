from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.config import settings
from app.models.domain import ManualOverview
from app.schemas.api_models import (
    DiffResponse,
    HealthResponse,
    ManualDetailResponse,
    ManualListResponse,
    QueryRequest,
    QueryResponse,
)
from app.services.diff_service import DiffService
from app.services.parser_service import ParserService
from app.services.rag_service import RAGService
from parser.hierarchy import build_hierarchy
from parser.models import DocumentSection, ErrorCodeItem, SpecificationParameter

router = APIRouter(prefix="/api/v1", tags=["CT-200"])
class SelectionRequest(BaseModel):
    version: str
    node_id: str


class QARequest(BaseModel):
    version: str
    node_id: str

# Global service references set during lifespan
parser_service: ParserService | None = None
diff_service: DiffService | None = None
rag_service: RAGService | None = None

def find_node(nodes, node_id: str):
    for node in nodes:
        if node.node_id == node_id:
            return node

        found = find_node(node.children, node_id)
        if found:
            return found

    return None

def get_parser_service() -> ParserService:
    if parser_service is None:
        raise HTTPException(status_code=503, detail="Parser service is not initialized")
    return parser_service


def get_diff_service() -> DiffService:
    if diff_service is None:
        raise HTTPException(status_code=503, detail="Diff service is not initialized")
    return diff_service


def get_rag_service() -> RAGService:
    if rag_service is None:
        raise HTTPException(status_code=503, detail="RAG service is not initialized")
    return rag_service

@router.get("/manuals/{version}/nodes/{node_id}")
def get_manual_node(
    version: str,
    node_id: str,
    ps: Annotated[ParserService, Depends(get_parser_service)],
):
    doc = ps.get_document(version)

    if not doc:
        raise HTTPException(
            status_code=404,
            detail=f"Manual version '{version}' not found",
        )

    tree = build_hierarchy(doc.sections)
    node = find_node(tree, node_id)

    if not node:
        raise HTTPException(
            status_code=404,
            detail=f"Node '{node_id}' not found in {version}",
        )

    content_hash = hashlib.sha256(
        node.body_text.encode("utf-8")
    ).hexdigest()

    return {
        "node_id": node.node_id,
        "version": version,
        "heading": node.heading,
        "body_text": node.body_text,
        "content_hash": content_hash,
        "page_number": node.page_number,
        "parent_id": node.parent_id,
        "children": [
            {
                "node_id": child.node_id,
                "heading": child.heading,
            }
            for child in node.children
        ],
    }

@router.get("/health", response_model=HealthResponse)
def health_check(ps: Annotated[ParserService, Depends(get_parser_service)]):
    return HealthResponse(
        status="ok",
        app="ct200-ai-engineering",
        environment=settings.app_env,
        v1_loaded=ps.doc_v1 is not None,
        v2_loaded=ps.doc_v2 is not None,
    )


@router.get("/manuals", response_model=ManualListResponse)
def list_manuals(ps: Annotated[ParserService, Depends(get_parser_service)]):
    overview_list = []
    if ps.doc_v1:
        overview_list.append(
            ManualOverview(
                version=ps.doc_v1.version,
                title=ps.doc_v1.title,
                total_pages=ps.doc_v1.total_pages,
                sections_count=len(ps.doc_v1.sections),
                parameters_count=len(ps.doc_v1.parameters),
                error_codes_count=len(ps.doc_v1.error_codes),
            )
        )
    if ps.doc_v2:
        overview_list.append(
            ManualOverview(
                version=ps.doc_v2.version,
                title=ps.doc_v2.title,
                total_pages=ps.doc_v2.total_pages,
                sections_count=len(ps.doc_v2.sections),
                parameters_count=len(ps.doc_v2.parameters),
                error_codes_count=len(ps.doc_v2.error_codes),
            )
        )
    return ManualListResponse(manuals=overview_list)


@router.get("/manuals/{version}", response_model=ManualDetailResponse)
def get_manual_detail(version: str, ps: Annotated[ParserService, Depends(get_parser_service)]):
    doc = ps.get_document(version)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Manual version '{version}' not found")
    return ManualDetailResponse(
        version=doc.version,
        title=doc.title,
        total_pages=doc.total_pages,
        sections=doc.sections,
        parameters=doc.parameters,
        error_codes=doc.error_codes,
    )


@router.get("/manuals/{version}/sections", response_model=list[DocumentSection])
def get_sections(version: str, ps: Annotated[ParserService, Depends(get_parser_service)]):
    doc = ps.get_document(version)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Manual version '{version}' not found")
    return doc.sections

@router.get("/manuals/{version}/tree")
def get_manual_tree(
    version: str,
    ps: Annotated[ParserService, Depends(get_parser_service)],
):
    doc = ps.get_document(version)

    if not doc:
        raise HTTPException(
            status_code=404,
            detail=f"Manual version '{version}' not found",
        )

    return build_hierarchy(doc.sections)

@router.get("/manuals/{version}/parameters", response_model=list[SpecificationParameter])
def get_parameters(version: str, ps: Annotated[ParserService, Depends(get_parser_service)]):
    doc = ps.get_document(version)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Manual version '{version}' not found")
    return doc.parameters


@router.get("/manuals/{version}/errors", response_model=list[ErrorCodeItem])
def get_error_codes(version: str, ps: Annotated[ParserService, Depends(get_parser_service)]):
    doc = ps.get_document(version)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Manual version '{version}' not found")
    return doc.error_codes


@router.get("/manuals/{node_id}/changes")
def get_node_changes(
    node_id: str,
    ps: Annotated[ParserService, Depends(get_parser_service)],
):
    if not ps.doc_v1 or not ps.doc_v2:
        raise HTTPException(
            status_code=404,
            detail="Both manual versions are required",
        )

    tree_v1 = build_hierarchy(ps.doc_v1.sections)
    tree_v2 = build_hierarchy(ps.doc_v2.sections)

    node_v1 = find_node(tree_v1, node_id)
    node_v2 = find_node(tree_v2, node_id)

    if not node_v1 and not node_v2:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")

    text_v1 = node_v1.body_text if node_v1 else ""
    text_v2 = node_v2.body_text if node_v2 else ""

    hash_v1 = hashlib.sha256(text_v1.encode()).hexdigest() if node_v1 else None
    hash_v2 = hashlib.sha256(text_v2.encode()).hexdigest() if node_v2 else None

    if not node_v1:
        status = "added"
    elif not node_v2:
        status = "removed"
    elif hash_v1 == hash_v2:
        status = "unchanged"
    else:
        status = "modified"

    return {
        "node_id": node_id,
        "status": status,
        "v1": {
            "heading": node_v1.heading if node_v1 else None,
            "content_hash": hash_v1,
            "body_text": text_v1,
        },
        "v2": {
            "heading": node_v2.heading if node_v2 else None,
            "content_hash": hash_v2,
            "body_text": text_v2,
        },
    }

    
@router.get("/diff", response_model=DiffResponse)
def get_version_diff(ds: Annotated[DiffService, Depends(get_diff_service)]):
    try:
        comparison = ds.get_diff()
        return DiffResponse(comparison=comparison)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
@router.post("/selections")
def select_node(
    req: SelectionRequest,
    ps: Annotated[ParserService, Depends(get_parser_service)],
):
    doc = ps.get_document(req.version)

    if not doc:
        raise HTTPException(
            status_code=404,
            detail=f"Manual version '{req.version}' not found",
        )

    tree = build_hierarchy(doc.sections)
    node = find_node(tree, req.node_id)

    if not node:
        raise HTTPException(
            status_code=404,
            detail=f"Node '{req.node_id}' not found in {req.version}",
        )

    content_hash = hashlib.sha256(
        node.body_text.encode("utf-8")
    ).hexdigest()

    return {
        "status": "selected",
        "node_id": node.node_id,
        "version": req.version,
        "heading": node.heading,
        "content": node.body_text,
        "content_hash": content_hash,
    }
@router.post("/generate-qa")
def generate_qa(
    req: QARequest,
    ps: Annotated[ParserService, Depends(get_parser_service)],
):
    doc = ps.get_document(req.version)

    if not doc:
        raise HTTPException(
            status_code=404,
            detail=f"Manual version '{req.version}' not found",
        )

    tree = build_hierarchy(doc.sections)
    node = find_node(tree, req.node_id)

    if not node:
        raise HTTPException(
            status_code=404,
            detail=f"Node '{req.node_id}' not found in {req.version}",
        )

    content_hash = hashlib.sha256(
        node.body_text.encode("utf-8")
    ).hexdigest()

    test_ideas = [
        f"Verify the normal device behavior described in '{node.heading}'.",
        f"Verify all limits and thresholds described in '{node.heading}'.",
        f"Verify the device handles the operating condition described in '{node.heading}'.",
        f"Verify invalid or unsafe conditions described in '{node.heading}'.",
    ]

    return {
        "node_id": node.node_id,
        "version": req.version,
        "content_hash": content_hash,
        "test_ideas": test_ideas,
    }

@router.post("/query", response_model=QueryResponse)
def query_manual(
    req: QueryRequest,
    rag: Annotated[RAGService, Depends(get_rag_service)],
):
    answer_obj = rag.answer_query(
        query=req.query,
        version=req.version,
        max_citations=req.max_citations,
    )
    return QueryResponse(
        query=answer_obj.query,
        target_version=answer_obj.target_version,
        answer=answer_obj.answer,
        citations=answer_obj.citations,
        confidence=answer_obj.confidence,
    )
