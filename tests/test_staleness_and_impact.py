import pytest
from fastapi.testclient import TestClient
from app.main import app


def test_selection_endpoint():
    with TestClient(app) as client:
        # Select section 2.1.1.1 from v1
        res = client.post(
            "/api/v1/selections",
            json={"version": "v1", "node_id": "2.1.1.1"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["version"] == "v1"
        assert data["node_id"] == "2.1.1.1"
        assert "300" in data["content"]
        assert len(data["content_hash"]) == 64

        hash_v1 = data["content_hash"]

        # Duplicate selection: same node & version
        res_dup = client.post(
            "/api/v1/selections",
            json={"version": "v1", "node_id": "2.1.1.1"},
        )
        assert res_dup.status_code == 200
        assert res_dup.json()["content_hash"] == hash_v1


def test_generate_qa_and_staleness_lifecycle():
    with TestClient(app) as client:
        # 1. Generate QA for 2.1.1.1 in v1
        gen_res = client.post(
            "/api/v1/generate-qa",
            json={"version": "v1", "node_id": "2.1.1.1"},
        )
        assert gen_res.status_code == 200
        qa_data = gen_res.json()
        assert qa_data["node_id"] == "2.1.1.1"
        assert qa_data["version"] == "v1"
        assert 3 <= len(qa_data["test_ideas"]) <= 5
        hash_v1 = qa_data["content_hash"]

        # 2. Check impact in v1 (should be current since hash matches v1 current content)
        imp_v1_res = client.get("/api/v1/manuals/v1/nodes/2.1.1.1/impact")
        assert imp_v1_res.status_code == 200
        imp_v1 = imp_v1_res.json()
        assert imp_v1["status"] == "current"
        assert imp_v1["review_required"] is False
        assert imp_v1["current_hash"] == hash_v1

        # 3. Check impact against v2 (where 2.1.1.1 battery spec was changed from 300 to 250)
        imp_v2_res = client.get("/api/v1/manuals/v2/nodes/2.1.1.1/impact")
        assert imp_v2_res.status_code == 200
        imp_v2 = imp_v2_res.json()
        assert imp_v2["status"] == "stale"
        assert imp_v2["review_required"] is True
        assert imp_v2["current_hash"] != imp_v2["generated_hash"]
        assert "mismatch" in imp_v2["reason"].lower()

        # 4. Check QA retrieval endpoints
        get_all_qa = client.get("/api/v1/qa")
        assert get_all_qa.status_code == 200
        qas = get_all_qa.json()
        assert len(qas) >= 1
        found = next((q for q in qas if q["node_id"] == "2.1.1.1"), None)
        assert found is not None
        assert 3 <= len(found["test_ideas"]) <= 5

        get_single_qa = client.get("/api/v1/qa/2.1.1.1?version=v1")
        assert get_single_qa.status_code == 200
        single_qa = get_single_qa.json()
        assert single_qa["node_id"] == "2.1.1.1"
        assert single_qa["status"] == "current"


def test_impact_on_removed_or_nonexistent_node():
    with TestClient(app) as client:
        # Check impact for non-existent node
        res = client.get("/api/v1/manuals/v2/nodes/99.99/impact")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "removed"
        assert data["review_required"] is True
        assert "not found" in data["reason"].lower()
