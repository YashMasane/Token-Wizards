import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import init_db

@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c

def test_root_endpoint(client):
    res = client.get("/")
    assert res.status_code == 200

def test_documents_list_endpoint(client):
    res = client.get("/api/documents")
    assert res.status_code == 200
    docs = res.json()
    assert len(docs) >= 5

def test_chitchat_query(client):
    res = client.post("/api/query", json={
        "query": "Hi, how can you help me?",
        "thread_id": "test_session_1"
    })
    assert res.status_code == 200
    data = res.json()
    assert "Government Legal Intelligence Assistant" in data["markdown_output"]

def test_application_analysis_api(client):
    payload = {
        "form_data": {
            "project_name": "Nilambur Commercial Complex",
            "location": "50m east of Vembanad Lake boundary",
            "project_area_sqm": 5000,
            "environmental_clearance_status": "No",
            "local_body_noc_status": "Yes",
            "applicant_declaration": "All mandatory approvals are in place",
            "cited_orders": ["GO No. 22/2021/LSGD"]
        },
        "thread_id": "test_session_2"
    }
    res = client.post("/api/analyze-application", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "markdown_output" in data
    assert len(data["compliance_risk_flags"]) >= 2
    assert "Section 12(3)" in data["markdown_output"]
