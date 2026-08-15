from typing import List, Dict, Any

def run_deterministic_compliance_checks(parsed_form: Dict[str, Any], query_text: str = "") -> List[Dict[str, Any]]:
    """
    Executes rule-based compliance & risk detectors specified in problem statement:
    1. Missing Mandatory Approval Detector (SEIAA Environmental Clearance)
    2. Outdated Reference Detector (GO No. 22/2021/LSGD supersession)
    3. Judicial Precedent Risk Warning (High Court WP(C) 1234/2023)
    """
    risks = []
    
    project_area = parsed_form.get("project_area_sqm", 0.0)
    ec_status = str(parsed_form.get("environmental_clearance_status", "")).lower()
    location = str(parsed_form.get("location", "")).lower()
    cited_orders = parsed_form.get("cited_orders", [])
    
    combined_text = (query_text + " " + location + " " + " ".join(cited_orders)).lower()

    # CHECK 1: Missing Mandatory Approval (SEIAA Environmental Clearance)
    # Trigger: project_area > 3000 AND (location in ESZ or near lake/river) AND EC == No
    is_esz = any(term in combined_text for term in ["vembanad", "lake", "river", "esz", "ecologically sensitive", "50m", "100m", "200m", "500m", "coastal"])
    
    if project_area > 3000 and (is_esz or "vembanad" in location) and (ec_status in ["no", "not obtained", "false", "none"]):
        risks.append({
            "check_type": "missing_approval",
            "severity": "high",
            "message": "⚠️ Missing Mandatory Approval: Environmental clearance not obtained — Kerala Building Rules Section 12(3) & Circular 12/2025 require prior SEIAA clearance for commercial projects exceeding 3,000 sq.m in ecologically sensitive zones.",
            "triggered_by": {
                "field": "environmental_clearance_status",
                "value": "No",
                "project_area": f"{project_area} sq.m.",
                "location": parsed_form.get("location", "Near Vembanad Lake")
            },
            "relevant_sources": ["SRC-1", "SRC-2", "SRC-3"]
        })
        
        # Associated Judicial Precedent Warning
        risks.append({
            "check_type": "precedent_risk",
            "severity": "high",
            "message": "⚠️ Legal Precedent Risk: High Court of Kerala in WP(C) No. 1234/2023 ruled that building permits issued without mandatory environmental clearance under Section 12(3) are void ab initio, resulting in permit quashing, demolition orders, and departmental inquiry against issuing officers.",
            "triggered_by": {
                "precedent_case": "High Court of Kerala, WP(C) No. 1234/2023",
                "holding": "Void ab initio permit quashed + demolition ordered"
            },
            "relevant_sources": ["SRC-5"]
        })

    # CHECK 2: Outdated Reference Detector (GO 22/2021/LSGD)
    # Trigger: query or form cites GO No. 22/2021/LSGD
    if "22/2021" in combined_text or any("22/2021" in str(o) for o in cited_orders):
        risks.append({
            "check_type": "outdated_reference",
            "severity": "medium",
            "message": "⚠️ Outdated Reference Alert: GO No. 22/2021/LSGD cited — this GO has been superseded by GO(P) No. 45/2024/LSGD dated 10.04.2024 (Para 4 supersession clause). Earlier exemptions for projects <5,000 sq.m no longer apply.",
            "triggered_by": {
                "cited_document": "GO No. 22/2021/LSGD",
                "superseding_document": "GO(P) No. 45/2024/LSGD"
            },
            "relevant_sources": ["SRC-2", "SRC-4"]
        })

    return risks
