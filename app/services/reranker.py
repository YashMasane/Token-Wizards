import logging
from typing import List, Dict, Any
from app.models.llm_factory import get_llm
import json

logger = logging.getLogger(__name__)

class CrossEncoderReranker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self.model = None
        self._initialized = False

    def _lazy_init(self):
        if not self._initialized:
            try:
                from sentence_transformers import CrossEncoder
                logger.info(f"Loading Cross-Encoder model: {self.model_name}...")
                self.model = CrossEncoder(self.model_name)
                logger.info("Cross-Encoder loaded successfully.")
                self._initialized = True
            except ImportError:
                logger.warning("sentence-transformers not installed. Reranker will fall back to LLM scoring.")
                self._initialized = True
            except Exception as e:
                logger.error(f"Failed to load Cross-Encoder: {e}. Falling back to LLM scoring.")
                self._initialized = True

    def rerank(self, query: str, chunks: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
        if not chunks:
            return []

        self._lazy_init()

        if self.model:
            return self._rerank_with_cross_encoder(query, chunks, top_n)
        else:
            return self._rerank_with_llm(query, chunks, top_n)

    def _rerank_with_cross_encoder(self, query: str, chunks: List[Dict[str, Any]], top_n: int) -> List[Dict[str, Any]]:
        # Prepare pairs for cross-encoder: (query, document)
        pairs = [[query, c.get("content", "")] for c in chunks]
        
        try:
            scores = self.model.predict(pairs)
            
            # Attach scores and sort
            for i, chunk in enumerate(chunks):
                chunk["rerank_score"] = float(scores[i])
                
            sorted_chunks = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)
            return sorted_chunks[:top_n]
        except Exception as e:
            logger.error(f"Cross-encoder prediction failed: {e}. Falling back to RRF sorting.")
            # Fallback: just return top N sorted by RRF if available
            return sorted(chunks, key=lambda x: x.get("rrf_score", 0), reverse=True)[:top_n]

    def _rerank_with_llm(self, query: str, chunks: List[Dict[str, Any]], top_n: int) -> List[Dict[str, Any]]:
        # Fallback to LLM if sentence-transformers fails or is not available
        logger.info("Using LLM fallback for reranking.")
        llm = get_llm(temperature=0.0)
        
        system_prompt = (
            "You are a relevance scoring engine. "
            "Score the relevance of the following passages to the query on a scale of 0 to 10. "
            "Output valid JSON in this format: {\"scores\": [score1, score2, ...]} where the scores list matches the order of the provided passages."
        )
        
        passages_text = "\n\n".join([f"Passage {i+1}: {c.get('content', '')[:500]}..." for i, c in enumerate(chunks)])
        user_prompt = f"Query: {query}\n\nPassages:\n{passages_text}"
        
        try:
            res = llm.invoke([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ])
            content = res.content
            
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].strip()
                
            parsed = json.loads(content)
            scores = parsed.get("scores", [])
            
            # If LLM didn't return exactly the right number of scores, fallback to RRF
            if len(scores) != len(chunks):
                logger.warning(f"LLM returned {len(scores)} scores for {len(chunks)} chunks. Falling back to RRF.")
                return sorted(chunks, key=lambda x: x.get("rrf_score", 0), reverse=True)[:top_n]
                
            for i, chunk in enumerate(chunks):
                chunk["rerank_score"] = float(scores[i])
                
            sorted_chunks = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)
            return sorted_chunks[:top_n]
            
        except Exception as e:
            logger.error(f"LLM reranking failed: {e}. Falling back to RRF sorting.")
            return sorted(chunks, key=lambda x: x.get("rrf_score", 0), reverse=True)[:top_n]

reranker_service = CrossEncoderReranker()
