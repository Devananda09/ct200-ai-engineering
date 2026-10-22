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


def test_get_manual_detail():
    with TestClient(app) as client:
        res = client.get("/api/v1/manuals/v1")
        assert res.status_code == 200
        data = res.json()
        assert data["version"] == "v1"
        assert "sections" in data
        assert "parameters" in data
        assert "error_codes" in data


def test_get_sections():
    with TestClient(app) as client:
        res = client.get("/api/v1/manuals/v1/sections")
        assert res.status_code == 200
        data = res.json()
        assert len(data) > 0
        assert "section_number" in data[0]


def test_get_tree():
    with TestClient(app) as client:
        res = client.get("/api/v1/manuals/v1/tree")
        assert res.status_code == 200
        data = res.json()
        assert len(data) > 0
        first_node = data[0]
        assert "node_id" in first_node
        assert "content_hash" in first_node


def test_get_parameters_and_errors():
    with TestClient(app) as client:
        res_params = client.get("/api/v1/manuals/v1/parameters")
        assert res_params.status_code == 200
        assert len(res_params.json()) > 0

        res_errs = client.get("/api/v1/manuals/v1/errors")
        assert res_errs.status_code == 200
        assert len(res_errs.json()) > 0


def test_get_node_and_children():
    with TestClient(app) as client:
        # Node detail
        res = client.get("/api/v1/manuals/v1/nodes/2.1")
        assert res.status_code == 200
        data = res.json()
        assert data["node_id"] == "2.1"
        assert data["content_hash"] != ""

        # Node children
        res_child = client.get("/api/v1/manuals/v1/nodes/2.1/children")
        assert res_child.status_code == 200
        children = res_child.json()
        assert len(children) > 0


def test_get_node_changes():
    with TestClient(app) as client:
        # Battery specs changed between v1 and v2
        res = client.get("/api/v1/manuals/2.1.1.1/changes")
        assert res.status_code == 200
        data = res.json()
        assert data["node_id"] == "2.1.1.1"
        assert data["status"] == "modified"
        assert data["v1"]["content_hash"] != data["v2"]["content_hash"]



def test_search_nodes():
    with TestClient(app) as client:
        res = client.get("/api/v1/manuals/v2/search?q=Bluetooth")
        assert res.status_code == 200
        results = res.json()["results"]
        assert len(results) > 0
        assert any("Bluetooth" in r["title"] or "Bluetooth" in r["snippet"] for r in results)

