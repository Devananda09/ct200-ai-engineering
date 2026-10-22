from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
V1_PATH = DATA_DIR / "ct200_manual.pdf"


def test_health_endpoint():
    with TestClient(app) as client:
        res = client.get("/api/v1/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["app"] == "ct200-ai-engineering"


def test_list_manuals():
    with TestClient(app) as client:
        res = client.get("/api/v1/manuals")
        assert res.status_code == 200
        data = res.json()
        assert "manuals" in data
        assert len(data["manuals"]) >= 1


def test_get_diff():
    with TestClient(app) as client:
        res = client.get("/api/v1/diff")
        assert res.status_code == 200
        data = res.json()
        assert "comparison" in data
        assert "5.3" in data["comparison"]["sections_added"]


def test_query_rag():
    with TestClient(app) as client:
        res = client.post(
            "/api/v1/query",
            json={"query": "What is error code E3?", "version": "v2"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "answer" in data
        assert len(data["citations"]) > 0
