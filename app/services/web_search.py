import os
import logging
from typing import List, Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)

def perform_fallback_web_search(query: str, max_results: int = 3) -> List[Dict[str, Any]]:
    """
    Fallback web search using Tavily API (if TAVILY_API_KEY is configured) or DuckDuckGo.
    """
    tavily_key = settings.TAVILY_API_KEY or os.getenv("TAVILY_API_KEY")
    results = []

    # Strategy 1: Tavily API Search (AI-optimized RAG search)
    if tavily_key:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=tavily_key)
            response = client.search(query=query + " Kerala Building Rules LSGD", max_results=max_results)
            raw_results = response.get("results", [])
            for r in raw_results:
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("content", ""),
                    "url": r.get("url", ""),
                    "source": "Tavily Search API"
                })
            logger.info(f"Tavily Web Search API returned {len(results)} results.")
            if results:
                return results
        except Exception as e:
            logger.warning(f"Tavily Search API error: {e}. Falling back to DuckDuckGo.")

    # Strategy 2: DuckDuckGo Search (Free Fallback)
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            search_gen = ddgs.text(query + " Kerala Building Rules LSGD", max_results=max_results)
            for r in search_gen:
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("href", ""),
                    "source": "DuckDuckGo Search"
                })
        logger.info(f"DuckDuckGo Search returned {len(results)} results.")
    except Exception as e:
        logger.warning(f"DuckDuckGo search failed: {e}")

    return results

