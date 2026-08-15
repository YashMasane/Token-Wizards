import pytest
from app.services.document_loader import load_mock_corpus_documents
from app.services.hybrid_retriever import hybrid_retriever

def test_mock_corpus_indexing_and_search():
    chunks = load_mock_corpus_documents()
    assert len(chunks) >= 5
    
    hybrid_retriever.index_documents(chunks)
    
    # Search for Section 12(3) environmental clearance
    results = hybrid_retriever.hybrid_search("Section 12(3) environmental clearance SEIAA", top_k=3)
    assert len(results) > 0
    top_doc = results[0]
    assert "doc1_kerala_building_rules_2022" in top_doc["doc_id"] or "12(3)" in top_doc.get("clause_or_rule", "")

def test_supersession_go_search():
    chunks = load_mock_corpus_documents()
    hybrid_retriever.index_documents(chunks)
    
    results = hybrid_retriever.hybrid_search("GO 45/2024 supersedes GO 22/2021", top_k=3, doc_type_filter="Government Order")
    assert len(results) > 0
    found_go = any("45/2024" in r["document_name"] or "22/2021" in r["content"] for r in results)
    assert found_go is True
