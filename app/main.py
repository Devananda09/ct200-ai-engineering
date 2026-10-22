from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import routes
from app.config import settings
from app.db import (
    DocumentNodeRecord,
    DocumentVersionRecord,
    SessionLocal,
    init_db,
)
from app.services.diff_service import DiffService
from app.services.llm_provider import LLMGenerationService
from app.services.parser_service import ParserService
from app.services.rag_service import RAGService
from parser.hierarchy import build_hierarchy

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("ct200_app")


def _sync_documents_to_db(ps: ParserService):
    """Sync parsed manuals and nodes to SQLite database."""
    db = SessionLocal()
    try:
        for version, doc in [("v1", ps.doc_v1), ("v2", ps.doc_v2)]:
            if not doc:
                continue
            existing = db.query(DocumentVersionRecord).filter_by(id=version).first()
            if not existing:
                ver_rec = DocumentVersionRecord(
                    id=version,
                    title=doc.title,
                    total_pages=doc.total_pages,
                )
                db.add(ver_rec)
                db.commit()

                # Build hierarchy tree to get parent-child relationships and content hashes
                tree = build_hierarchy(doc.sections, tables=doc.tables)
                _persist_tree_nodes(db, version, tree)
                db.commit()
    except Exception as e:
        logger.error(f"Error syncing documents to database: {e}")
        db.rollback()
    finally:
        db.close()


def _persist_tree_nodes(db, version: str, nodes, parent_id: str | None = None):
    import json
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
            _persist_tree_nodes(db, version, node.children, parent_id=node.node_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing CT-200 AI Engineering services...")
    init_db()

    ps = ParserService(
        v1_path=settings.docs_v1_path,
        v2_path=settings.docs_v2_path,
    )
    ps.initialize()

    ds = DiffService(doc_v1=ps.doc_v1, doc_v2=ps.doc_v2)
    rag = RAGService(doc_v1=ps.doc_v1, doc_v2=ps.doc_v2)
    llm = LLMGenerationService(
        gemini_api_key=settings.gemini_api_key,
        gemini_model=settings.gemini_model,
    )

    routes.parser_service = ps
    routes.diff_service = ds
    routes.rag_service = rag
    routes.llm_service = llm

    _sync_documents_to_db(ps)

    logger.info("CT-200 services initialized successfully.")
    yield
    logger.info("CT-200 services shutting down.")



app = FastAPI(
    title="CardioTrack CT-200 AI Engineering API",
    description="Technical specification parsing, hierarchical chunking, version comparison, and grounded Q&A for CT-200 Blood Pressure Monitor manuals.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router)


@app.get("/")
def root():
    return JSONResponse(
        {
            "name": "CardioTrack CT-200 AI Engineering API",
            "version": "1.0.0",
            "docs": "/docs",
            "endpoints": [
                "/api/v1/health",
                "/api/v1/manuals",
                "/api/v1/manuals/{version}",
                "/api/v1/diff",
                "/api/v1/query",
            ],
        }
    )
