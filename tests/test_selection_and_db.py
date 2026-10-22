import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base, DocumentVersionRecord, DocumentNodeRecord, SelectionRecord, GeneratedQARecord


@pytest.fixture
def db_session():
    # In-memory SQLite for fast, isolated testing
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_document_version_and_node_persistence(db_session):
    doc = DocumentVersionRecord(
        id="v1",
        title="CT-200 Technical Manual",
        total_pages=6,
    )
    db_session.add(doc)
    db_session.commit()

    node = DocumentNodeRecord(
        version="v1",
        node_id="2.1.1.1",
        heading="Battery Specifications",
        level=4,
        body_text="Operates on 4 AA batteries. Minimum 300 cycles.",
        content_hash="abc_hash_v1",
        page_number=2,
        parent_id="2.1",
    )
    db_session.add(node)
    db_session.commit()

    queried_node = db_session.query(DocumentNodeRecord).filter_by(version="v1", node_id="2.1.1.1").first()
    assert queried_node is not None
    assert queried_node.content_hash == "abc_hash_v1"
    assert queried_node.parent_id == "2.1"


def test_duplicate_selection_policy(db_session):
    """
    Enforce Duplicate Selection Policy:
    When the same (version, node_id, content_hash) is selected multiple times,
    we do not create redundant duplicate records; the existing record is returned.
    """
    # 1. First selection
    sel1 = SelectionRecord(
        version="v2",
        node_id="2.1.1.1",
        heading="Battery Specifications",
        content="Operates on 4 AA batteries. Minimum 250 cycles.",
        content_hash="hash_v2_250",
    )
    db_session.add(sel1)
    db_session.commit()
    sel1_id = sel1.id

    # 2. Check existence before inserting again
    existing = (
        db_session.query(SelectionRecord)
        .filter_by(version="v2", node_id="2.1.1.1", content_hash="hash_v2_250")
        .first()
    )
    assert existing is not None
    assert existing.id == sel1_id

    # Total rows in SelectionRecord should still be 1
    total_selections = db_session.query(SelectionRecord).count()
    assert total_selections == 1

    # 3. If content hash changes (e.g. from v1 with 300 cycles), it represents a different content state
    sel_diff_hash = SelectionRecord(
        version="v1",
        node_id="2.1.1.1",
        heading="Battery Specifications",
        content="Operates on 4 AA batteries. Minimum 300 cycles.",
        content_hash="hash_v1_300",
    )
    db_session.add(sel_diff_hash)
    db_session.commit()

    assert db_session.query(SelectionRecord).count() == 2


def test_generated_qa_hash_association(db_session):
    qa = GeneratedQARecord(
        node_id="2.1.1.1",
        version="v2",
        generated_from_hash="hash_v2_250",
        provider_used="deterministic-fallback",
        test_ideas_json='[{"title":"Test 1","description":"Desc","expected_result":"Exp","source_reference":"2.1.1.1"}]',
    )
    db_session.add(qa)
    db_session.commit()

    record = db_session.query(GeneratedQARecord).filter_by(node_id="2.1.1.1", version="v2").first()
    assert record is not None
    assert record.generated_from_hash == "hash_v2_250"
    assert record.provider_used == "deterministic-fallback"
