import pytest
from app.services.compliance_engine import run_deterministic_compliance_checks

def test_missing_approval_detector():
    parsed_form = {
        "project_name": "Nilambur Commercial Complex",
        "location": "50m east of Vembanad Lake boundary",
        "project_area_sqm": 5000.0,
        "environmental_clearance_status": "No",
        "local_body_noc_status": "Yes",
        "cited_orders": ["GO No. 22/2021/LSGD"]
    }
    
    risks = run_deterministic_compliance_checks(parsed_form, query_text="Is environmental clearance mandatory?")
    assert len(risks) >= 2
    
    types = [r["check_type"] for r in risks]
    assert "missing_approval" in types
    assert "precedent_risk" in types
    assert "outdated_reference" in types
