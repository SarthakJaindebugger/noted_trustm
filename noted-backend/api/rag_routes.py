import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any

from api.auth import AuthenticatedUser, require_authenticated_user
from services.rag import RAGService

logger = logging.getLogger(__name__)

rag_service = RAGService()

rag_router = APIRouter(prefix="/rag")


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


class QueryResponse(BaseModel):
    response: str
    context_docs: List[Dict[str, Any]]


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


class SearchResponse(BaseModel):
    results: List[Dict[str, Any]]


@rag_router.post("/query", response_model=QueryResponse)
async def query_rag(
    request: QueryRequest,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Query the RAG system — runs retrieval + LLM generation in background thread."""
    try:
        logger.info("[RAG] Query received: %s", request.query)
        result = await rag_service.query_async(request.query, top_k=request.top_k)
        logger.info("[RAG] Response generated, %d context docs", len(result["context_docs"]))
        return QueryResponse(response=result["response"], context_docs=result["context_docs"])
    except Exception as e:
        logger.error("[RAG] Query failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"RAG query failed: {str(e)}")


@rag_router.post("/search", response_model=SearchResponse)
async def search_documents(
    request: SearchRequest,
    current_user: AuthenticatedUser = Depends(require_authenticated_user),
):
    """Search for similar documents — runs in background thread."""
    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, rag_service.search_similar_documents, request.query, request.top_k
        )
        return SearchResponse(results=results)
    except Exception as e:
        logger.error("RAG search failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to search documents")
