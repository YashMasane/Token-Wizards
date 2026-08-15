import re
import math
import logging
from typing import List, Dict, Any, Optional
from app.services.vector_store import vector_store_service

logger = logging.getLogger(__name__)

def tokenize(text: str) -> List[str]:
    return re.findall(r"\w+", text.lower())

class FallbackBM25:
    """Lightweight pure-python BM25 fallback when rank_bm25 is not installed."""
    def __init__(self, tokenized_corpus: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = len(tokenized_corpus)
        self.doc_lens = [len(doc) for doc in tokenized_corpus]
        self.avgdl = sum(self.doc_lens) / self.corpus_size if self.corpus_size > 0 else 1.0
        
        self.doc_freqs = []
        self.idf = {}
        df_counts = {}

        for doc in tokenized_corpus:
            freqs = {}
            for word in doc:
                freqs[word] = freqs.get(word, 0) + 1
            self.doc_freqs.append(freqs)
            for word in freqs:
                df_counts[word] = df_counts.get(word, 0) + 1

        for word, freq in df_counts.items():
            self.idf[word] = math.log((self.corpus_size - freq + 0.5) / (freq + 0.5) + 1)

    def get_scores(self, query_tokens: List[str]) -> List[float]:
        scores = [0.0] * self.corpus_size
        for idx, doc_freqs in enumerate(self.doc_freqs):
            doc_len = self.doc_lens[idx]
            for token in query_tokens:
                if token in doc_freqs:
                    freq = doc_freqs[token]
                    idf = self.idf.get(token, 0.0)
                    numerator_val = freq * (self.k1 + 1)  # renamed from 'freqs' to avoid shadowing
                    denominator = freq + self.k1 * (1 - self.b + self.b * (doc_len / self.avgdl))
                    scores[idx] += idf * (numerator_val / denominator)
        return scores



class HybridRetriever:
    def __init__(self):
        self.chunks: List[Dict[str, Any]] = []
        self.bm25: Any = None
        self._is_indexed = False

    def index_documents(self, chunks: List[Dict[str, Any]]):
        self.chunks = chunks
        tokenized_corpus = [tokenize(c["content"] + " " + c.get("clause_or_rule", "") + " " + c.get("document_name", "")) for c in chunks]
        
        try:
            from rank_bm25 import BM25Okapi
            self.bm25 = BM25Okapi(tokenized_corpus)
        except ImportError:
            logger.info("rank_bm25 not installed. Using internal FallbackBM25 engine.")
            self.bm25 = FallbackBM25(tokenized_corpus)
            
        self._is_indexed = True
        vector_store_service.index_documents(chunks)
        logger.info(f"Hybrid Retriever (BM25 + Vector Store) indexed {len(chunks)} chunks.")

    def search_bm25(self, query: str, top_k: int = 5, doc_type_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self._is_indexed or self.bm25 is None:
            return []
        tokenized_query = tokenize(query)
        
        if hasattr(self.bm25, "get_scores"):
            scores = self.bm25.get_scores(tokenized_query)
        else:
            scores = [0.0] * len(self.chunks)
            
        filtered_indices = []
        for idx, chunk in enumerate(self.chunks):
            if doc_type_filter:
                if doc_type_filter == "Rules" and chunk.get("doc_type") != "Rules":
                    continue
                elif doc_type_filter in ["Government Order", "Circular"] and chunk.get("doc_type") not in ["Government Order", "Circular"]:
                    continue
                elif doc_type_filter == "Judgment" and chunk.get("doc_type") != "Judgment":
                    continue
            filtered_indices.append(idx)
            
        if not filtered_indices:
            return []

        sub_scores = [scores[i] for i in filtered_indices]
        top_sub_idx = sorted(range(len(sub_scores)), key=lambda i: sub_scores[i], reverse=True)[:top_k]

        results = []
        for sub_i in top_sub_idx:
            orig_i = filtered_indices[sub_i]
            res_chunk = dict(self.chunks[orig_i])
            res_chunk["bm25_score"] = float(scores[orig_i])
            results.append(res_chunk)
        return results

    def hybrid_search(self, query: str, top_k: int = 5, doc_type_filter: Optional[str] = None, k_rrf: int = 60) -> List[Dict[str, Any]]:
        dense_results = vector_store_service.search(query, top_k=top_k * 2, doc_type_filter=doc_type_filter)
        bm25_results = self.search_bm25(query, top_k=top_k * 2, doc_type_filter=doc_type_filter)

        rrf_scores: Dict[str, float] = {}
        chunk_map: Dict[str, Dict[str, Any]] = {}

        for rank, chunk in enumerate(dense_results):
            cid = chunk["chunk_id"]
            chunk_map[cid] = chunk
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (k_rrf + rank + 1))

        for rank, chunk in enumerate(bm25_results):
            cid = chunk["chunk_id"]
            if cid not in chunk_map:
                chunk_map[cid] = chunk
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (k_rrf + rank + 1))

        sorted_cids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)[:top_k]

        final_results = []
        for cid in sorted_cids:
            chunk_obj = dict(chunk_map[cid])
            chunk_obj["rrf_score"] = round(rrf_scores[cid], 5)
            final_results.append(chunk_obj)

        return final_results

hybrid_retriever = HybridRetriever()
