from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import routes
from app.config import settings
from app.services.diff_service import DiffService
from app.services.parser_service import ParserService
from app.services.rag_service import RAGService

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("ct200_app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing CT-200 AI Engineering services...")
    ps = ParserService(
        v1_path=settings.docs_v1_path,
        v2_path=settings.docs_v2_path,
    )
    ps.initialize()

    ds = DiffService(doc_v1=ps.doc_v1, doc_v2=ps.doc_v2)
    rag = RAGService(doc_v1=ps.doc_v1, doc_v2=ps.doc_v2)

    routes.parser_service = ps
    routes.diff_service = ds
    routes.rag_service = rag

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
