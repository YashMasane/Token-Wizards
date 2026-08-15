import os
import re
import logging
import json
from typing import List, Dict, Any, Optional
from app.config import settings
import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

class FallbackEmbeddingManager:
    """Pure-python TF-IDF term frequency vector encoder fallback."""
    def __init__(self):
        self.vocab = {}

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"\w+", text.lower())

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        # Build vocabulary dynamically
        for t in texts:
            for w in self._tokenize(t):
                if w not in self.vocab and len(self.vocab) < 384:
                    self.vocab[w] = len(self.vocab)

        dim = 384
        embeddings = []
        for t in texts:
            vec = [0.0] * dim
            tokens = self._tokenize(t)
            for tok in tokens:
                if tok in self.vocab:
                    vec[self.vocab[tok]] += 1.0
            embeddings.append(vec)
        return embeddings

    def embed_query(self, query: str) -> List[float]:
        dim = 384
        vec = [0.0] * dim
        tokens = self._tokenize(query)
        for tok in tokens:
            if tok in self.vocab:
                vec[self.vocab[tok]] += 1.0
        return vec


class EmbeddingManager:
    _instance = None

    def __init__(self):
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading Embedding Model: {settings.EMBEDDING_MODEL_NAME}")
            self.model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
            self.is_fallback = False
        except Exception as e:
            logger.warning(f"sentence_transformers not available ({e}). Using FallbackEmbeddingManager.")
            self.model = FallbackEmbeddingManager()
            self.is_fallback = True

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if self.is_fallback:
            return self.model.embed_texts(texts)
        embeddings = self.model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        return embeddings.tolist()

    def embed_query(self, query: str) -> List[float]:
        if self.is_fallback:
            return self.model.embed_query(query)
        embedding = self.model.encode([query], show_progress_bar=False, convert_to_numpy=True)[0]
        return embedding.tolist()


class VectorStoreService:
    def __init__(self):
        self.embedding_mgr = EmbeddingManager.get_instance()
        
        persist_dir = settings.CHROMA_PERSIST_DIR
        if not os.path.exists(persist_dir):
            os.makedirs(persist_dir, exist_ok=True)
            
        logger.info(f"Initializing ChromaDB PersistentClient at {persist_dir}")
        self.chroma_client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.chroma_client.get_or_create_collection(
            name="legal_documents",
            metadata={"hnsw:space": "cosine"}
        )
        self._is_indexed = self.collection.count() > 0

    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """ChromaDB metadata only accepts str, int, float, bool. Complex types must be stringified."""
        clean_meta = {}
        for k, v in metadata.items():
            if k == "content":
                continue # don't put full content in metadata
            if isinstance(v, (str, int, float, bool)):
                clean_meta[k] = v
            elif v is None:
                clean_meta[k] = "None"
            else:
                clean_meta[k] = json.dumps(v)
        return clean_meta

    def index_documents(self, chunks: List[Dict[str, Any]]):
        if not chunks:
            return
            
        ids = [c["chunk_id"] for c in chunks]
        contents = [c["content"] for c in chunks]
        metadatas = [self._sanitize_metadata(c) for c in chunks]
        
        # Check which ones already exist to avoid re-embedding everything if unchanged
        existing = self.collection.get(ids=ids)["ids"]
        new_indices = [i for i, cid in enumerate(ids) if cid not in existing]
        
        if new_indices:
            logger.info(f"Embedding and upserting {len(new_indices)} new chunks into ChromaDB...")
            new_contents = [contents[i] for i in new_indices]
            new_embeddings = self.embedding_mgr.embed_texts(new_contents)
            
            # Normalize embeddings for cosine similarity
            import numpy as np
            new_embeddings_np = np.array(new_embeddings, dtype=np.float32)
            norms = np.linalg.norm(new_embeddings_np, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            new_embeddings_np = new_embeddings_np / norms
            normalized_embeddings = new_embeddings_np.tolist()
            
            self.collection.upsert(
                ids=[ids[i] for i in new_indices],
                embeddings=normalized_embeddings,
                documents=[contents[i] for i in new_indices],
                metadatas=[metadatas[i] for i in new_indices]
            )
        else:
            logger.info("All chunks already exist in ChromaDB. No new embeddings required.")
            
        self._is_indexed = True
        logger.info(f"VectorStore (ChromaDB) currently holds {self.collection.count()} chunks.")

    def search(self, query: str, top_k: int = 5, doc_type_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self._is_indexed:
            return []
            
        q_emb = self.embedding_mgr.embed_query(query)
        import numpy as np
        q_emb_np = np.array(q_emb, dtype=np.float32)
        q_norm = np.linalg.norm(q_emb_np)
        if q_norm > 0:
            q_emb_np = q_emb_np / q_norm
        
        # Where clause for metadata filtering
        where_clause = None
        if doc_type_filter:
            where_clause = {"doc_type": doc_type_filter}
            
        # ChromaDB query
        results = self.collection.query(
            query_embeddings=[q_emb_np.tolist()],
            n_results=top_k,
            where=where_clause,
            include=["documents", "metadatas", "distances"]
        )
        
        if not results or not results['ids'] or len(results['ids'][0]) == 0:
            return []
            
        formatted_results = []
        for idx in range(len(results['ids'][0])):
            chunk_id = results['ids'][0][idx]
            content = results['documents'][0][idx]
            metadata = results['metadatas'][0][idx]
            distance = results['distances'][0][idx]
            
            # Convert cosine distance to similarity score
            # Note: ChromaDB with cosine space returns distance = 1.0 - cosine_similarity
            similarity = round(1.0 - distance, 4)
            
            # Reconstruct the chunk dict matching expected format
            res_chunk = {
                "chunk_id": chunk_id,
                "content": content,
                "similarity_score": similarity,
                **metadata
            }
            formatted_results.append(res_chunk)
            
        return formatted_results

vector_store_service = VectorStoreService()
