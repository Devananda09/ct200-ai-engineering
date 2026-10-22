from __future__ import annotations

import datetime
from pathlib import Path
from typing import Generator

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_FILE = Path(__file__).resolve().parent.parent / "ct200.db"
DATABASE_URL = f"sqlite:///{DATABASE_FILE}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class DocumentVersionRecord(Base):
    __tablename__ = "document_versions"

    id = Column(String(32), primary_key=True)  # e.g., 'v1', 'v2'
    title = Column(String(255), nullable=False)
    total_pages = Column(Integer, nullable=False)
    ingested_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    nodes = relationship("DocumentNodeRecord", back_populates="document_version", cascade="all, delete-orphan")


class DocumentNodeRecord(Base):
    __tablename__ = "document_nodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(32), ForeignKey("document_versions.id"), nullable=False, index=True)
    node_id = Column(String(64), nullable=False, index=True)
    heading = Column(String(255), nullable=False)
    level = Column(Integer, nullable=False)
    body_text = Column(Text, nullable=False)
    page_number = Column(Integer, nullable=True)
    parent_id = Column(String(64), nullable=True)
    content_hash = Column(String(64), nullable=False, index=True)
    tables_json = Column(Text, nullable=True)  # JSON-encoded extracted tables

    document_version = relationship("DocumentVersionRecord", back_populates="nodes")


class SelectionRecord(Base):
    """
    Persisted immutable node selection record.
    Duplicate selection policy:
    If (version, node_id, content_hash) is selected again, the existing record is reused.
    If the content_hash differs, a new selection record is created.
    """
    __tablename__ = "selections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(32), nullable=False, index=True)
    node_id = Column(String(64), nullable=False, index=True)
    content_hash = Column(String(64), nullable=False, index=True)
    heading = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    selected_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))


class GeneratedQARecord(Base):
    """
    Persisted structured QA test ideas generated for a node.
    Strictly tied to the exact content hash (generated_from_hash)
    used during generation to enable staleness and impact detection.
    """
    __tablename__ = "generated_qa"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_id = Column(String(64), nullable=False, index=True)
    version = Column(String(32), nullable=False, index=True)
    generated_from_hash = Column(String(64), nullable=False, index=True)
    test_ideas_json = Column(Text, nullable=False)  # JSON-encoded list of QAItem
    provider_used = Column(String(64), nullable=False)
    generated_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
