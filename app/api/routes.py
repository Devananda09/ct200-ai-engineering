from __future__ import annotations

import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db import GeneratedQARecord, SelectionRecord, get_db
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
from app.services.llm_provider import LLMGenerationError, LLMGenerationService
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
llm_service: LLMGenerationService | None = None


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


def get_llm_service() -> LLMGenerationService:
    if llm_service is None:
        raise HTTPException(status_code=503, detail="LLM generation service is not initialized")
    return llm_service


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
        
@router.get("/manuals/{version}/nodes/{node_id}/children")
def get_node_children(
    version: str,
    node_id: str,
    ps: Annotated[ParserService, Depends(get_parser_service)],
):
    doc = ps.get_document(version)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Manual version '{version}' not found")

    tree = build_hierarchy(doc.sections, tables=doc.tables)
    node = find_node(tree, node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found in {version}")

    return [
        {
            "node_id": child.node_id,
            "heading": child.heading,
            "level": child.level,
            "page_number": child.page_number,
            "content_hash": child.content_hash,
        }
        for child in node.children
    ]


@router.get("/manuals/{version}/search")
def search_manual(
    version: str,
    q: Annotated[str, Query(..., description="Search query string")],
    rag: Annotated[RAGService, Depends(get_rag_service)],
):
    answer_obj = rag.answer_query(query=q, version=version)
    results = [
        {
            "node_id": c.section_number,
            "section": c.section_number,
            "title": c.section_title,
            "snippet": c.snippet,
            "page_number": c.page_number,
            "relevance_score": c.relevance_score,
        }
        for c in answer_obj.citations
    ]
    return {
        "query": q,
        "version": version,
        "results": results,
        "answer": answer_obj.answer,
        "citations": answer_obj.citations,
        "confidence": answer_obj.confidence,
    }



@router.post("/selections")
def select_node(
    req: SelectionRequest,
    ps: Annotated[ParserService, Depends(get_parser_service)],
    db: Annotated[Session, Depends(get_db)],
):
    doc = ps.get_document(req.version)
    if not doc:
        raise HTTPException(
            status_code=404,
            detail=f"Manual version '{req.version}' not found",
        )

    tree = build_hierarchy(doc.sections, tables=doc.tables)
    node = find_node(tree, req.node_id)
    if not node:
        raise HTTPException(
            status_code=404,
            detail=f"Node '{req.node_id}' not found in {req.version}",
        )

    content_hash = node.content_hash or hashlib.sha256(node.body_text.encode("utf-8")).hexdigest()

    # Duplicate selection policy:
    # If the exact (version, node_id, content_hash) already exists, reuse the immutable selection record.
    existing = (
        db.query(SelectionRecord)
        .filter_by(version=req.version, node_id=req.node_id, content_hash=content_hash)
        .first()
    )
    if not existing:
        sel_rec = SelectionRecord(
            version=req.version,
            node_id=req.node_id,
            content_hash=content_hash,
            heading=node.heading,
            content=node.body_text,
        )
        db.add(sel_rec)
        db.commit()

    return {
        "status": "selected",
        "node_id": node.node_id,
        "version": req.version,
        "heading": node.heading,
        "content": node.body_text,
        "content_hash": content_hash,
        "tables": node.tables,
    }


@router.post("/generate-qa")
def generate_qa(
    req: QARequest,
    ps: Annotated[ParserService, Depends(get_parser_service)],
    llm: Annotated[LLMGenerationService, Depends(get_llm_service)],
    db: Annotated[Session, Depends(get_db)],
):
    doc = ps.get_document(req.version)
    if not doc:
        raise HTTPException(
            status_code=404,
            detail=f"Manual version '{req.version}' not found",
        )

    tree = build_hierarchy(doc.sections, tables=doc.tables)
    node = find_node(tree, req.node_id)
    if not node:
        raise HTTPException(
            status_code=404,
            detail=f"Node '{req.node_id}' not found in {req.version}",
        )

    content_hash = node.content_hash or hashlib.sha256(node.body_text.encode("utf-8")).hexdigest()

    try:
        qa_result = llm.generate_qa(
            node_id=node.node_id,
            version=req.version,
            heading=node.heading,
            content=node.body_text,
            content_hash=content_hash,
        )
    except LLMGenerationError as ex:
        raise HTTPException(
            status_code=502,
            detail=f"Structured QA generation failed: {ex}",
        )

    # Persist validated generated QA tied to exact content hash
    qa_record = GeneratedQARecord(
        node_id=req.node_id,
        version=req.version,
        generated_from_hash=content_hash,
        test_ideas_json=json.dumps([idea.model_dump() for idea in qa_result.test_ideas]),
        provider_used=qa_result.provider,
    )
    db.add(qa_record)
    db.commit()

    return qa_result.model_dump()


@router.get("/manuals/{version}/nodes/{node_id}/impact")
def check_node_impact(
    version: str,
    node_id: str,
    ps: Annotated[ParserService, Depends(get_parser_service)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Check whether previously generated QA for this node has become stale
    against the target manual version.
    """
    qa_record = (
        db.query(GeneratedQARecord)
        .filter_by(node_id=node_id)
        .order_by(GeneratedQARecord.id.desc())
        .first()
    )

    target_doc = ps.get_document(version)
    if not target_doc:
        raise HTTPException(status_code=404, detail=f"Manual version '{version}' not found")

    target_tree = build_hierarchy(target_doc.sections, tables=target_doc.tables)
    target_node = find_node(target_tree, node_id)

    if not qa_record:
        if not target_node:
            return {
                "node_id": node_id,
                "version": version,
                "target_version": version,
                "status": "removed",
                "is_stale": True,
                "review_required": True,
                "requires_regeneration": True,
                "generated_hash": None,
                "generated_from_hash": None,
                "current_hash": None,
                "reason": f"Node '{node_id}' not found in version '{version}' and has no generated QA.",
            }
        current_hash = target_node.content_hash or hashlib.sha256(target_node.body_text.encode("utf-8")).hexdigest()
        return {
            "node_id": node_id,
            "version": version,
            "target_version": version,
            "status": "untracked",
            "is_stale": False,
            "review_required": False,
            "requires_regeneration": True,
            "generated_hash": None,
            "generated_from_hash": None,
            "current_hash": current_hash,
            "reason": f"Node '{node_id}' exists in {version} but no QA ideas have been generated yet.",
        }

    generated_hash = qa_record.generated_from_hash

    if not target_node:
        return {
            "node_id": node_id,
            "version": version,
            "target_version": version,
            "status": "removed",
            "is_stale": True,
            "review_required": True,
            "requires_regeneration": True,
            "generated_from_version": qa_record.version,
            "generated_hash": generated_hash,
            "generated_from_hash": generated_hash,
            "current_hash": None,
            "reason": f"Node '{node_id}' was removed in version '{version}'. QA ideas are impacted.",
        }

    current_hash = target_node.content_hash or hashlib.sha256(target_node.body_text.encode("utf-8")).hexdigest()

    if current_hash == generated_hash:
        return {
            "node_id": node_id,
            "version": version,
            "target_version": version,
            "status": "current",
            "is_stale": False,
            "review_required": False,
            "requires_regeneration": False,
            "generated_from_version": qa_record.version,
            "generated_hash": generated_hash,
            "generated_from_hash": generated_hash,
            "current_hash": current_hash,
            "reason": "Content hash matches source generation content. QA ideas remain valid.",
        }
    else:
        return {
            "node_id": node_id,
            "version": version,
            "target_version": version,
            "status": "stale",
            "is_stale": True,
            "review_required": True,
            "requires_regeneration": True,
            "generated_from_version": qa_record.version,
            "generated_hash": generated_hash,
            "generated_from_hash": generated_hash,
            "current_hash": current_hash,
            "reason": (
                f"Content hash mismatch / changed ({generated_hash[:8]}... -> {current_hash[:8]}...). "
                f"Section was modified between {qa_record.version} and {version}."
            ),

        }


@router.get("/qa")
def list_generated_qa(
    ps: Annotated[ParserService, Depends(get_parser_service)],
    db: Annotated[Session, Depends(get_db)],
):
    """List all persisted QA records and their staleness status against latest manual (v2)."""
    records = db.query(GeneratedQARecord).order_by(GeneratedQARecord.id.desc()).all()
    results = []
    v2_doc = ps.get_document("v2")
    v2_tree = build_hierarchy(v2_doc.sections, tables=v2_doc.tables) if v2_doc else []

    for r in records:
        node_in_v2 = find_node(v2_tree, r.node_id)
        current_v2_hash = (
            node_in_v2.content_hash
            if node_in_v2
            else None
        )
        is_stale = (current_v2_hash != r.generated_from_hash)

        results.append(
            {
                "id": r.id,
                "node_id": r.node_id,
                "version": r.version,
                "generated_from_hash": r.generated_from_hash,
                "current_v2_hash": current_v2_hash,
                "is_stale": is_stale,
                "status": "stale" if is_stale else "current",
                "provider_used": r.provider_used,
                "generated_at": r.generated_at.isoformat() if r.generated_at else None,
                "test_ideas": json.loads(r.test_ideas_json),
            }
        )
    return results



@router.get("/qa/{node_id}")
def get_node_qa(
    node_id: str,
    ps: Annotated[ParserService, Depends(get_parser_service)],
    db: Annotated[Session, Depends(get_db)],
    version: str | None = None,
):

    """Get the latest persisted QA for a node and its current staleness status."""
    r = (
        db.query(GeneratedQARecord)
        .filter_by(node_id=node_id)
        .order_by(GeneratedQARecord.id.desc())
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail=f"No generated QA found for node '{node_id}'")

    cmp_version = version or "v2"
    cmp_doc = ps.get_document(cmp_version)
    cmp_tree = build_hierarchy(cmp_doc.sections, tables=cmp_doc.tables) if cmp_doc else []
    node_in_doc = find_node(cmp_tree, r.node_id)
    current_hash = node_in_doc.content_hash if node_in_doc else None
    is_stale = (current_hash != r.generated_from_hash)

    return {
        "id": r.id,
        "node_id": r.node_id,
        "version": r.version,
        "target_version": cmp_version,
        "generated_from_hash": r.generated_from_hash,
        "current_hash": current_hash,
        "current_v2_hash": current_hash,
        "is_stale": is_stale,
        "status": "stale" if is_stale else "current",
        "provider_used": r.provider_used,
        "generated_at": r.generated_at.isoformat() if r.generated_at else None,
        "test_ideas": json.loads(r.test_ideas_json),
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

