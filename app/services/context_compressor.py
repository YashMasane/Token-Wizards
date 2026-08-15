from typing import List, Dict, Any

def deduplicate_and_partition_chunks(chunks: List[Dict[str, Any]], min_score_threshold: float = 0.0) -> Dict[str, Any]:
    """
    De-duplicates retrieved text chunks, filters them by relevance score,
    and partitions them by domain metadata type.
    """
    seen_ids = set()
    unique_chunks = []
    filtered_out_count = 0
    
    for c in chunks:
        cid = c.get("chunk_id")
        
        # Check relevance score (either rerank_score or rrf_score)
        score = c.get("rerank_score", c.get("rrf_score", 10.0))
        if score < min_score_threshold:
            filtered_out_count += 1
            continue

        if cid not in seen_ids:
            seen_ids.add(cid)
            unique_chunks.append(c)

    partitioned = {
        "all_chunks": unique_chunks,
        "statutory_rules": [c for c in unique_chunks if c.get("doc_type") == "Rules"],
        "go_orders": [c for c in unique_chunks if c.get("doc_type") in ["Government Order", "Circular"]],
        "judgments": [c for c in unique_chunks if c.get("doc_type") == "Judgment"],
        "filtered_out_count": filtered_out_count
    }
    return partitioned

