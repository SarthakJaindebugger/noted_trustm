import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from api.auth import AuthenticatedUser, require_authenticated_user
from services.rag import RAGService
from config import settings

logger = logging.getLogger(__name__)

# Initialize RAG service – it now uses the correct parquet path and model defaults
rag_service = RAGService()   # reads PARQUET_PATH env or default absolute path
# Optionally, if you want to hardcode the path directly inside the container:
# rag_service = RAGService(parquet_file_path="/app/data/rag_embeddings.parquet")

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
    current_user: AuthenticatedUser = Depends(require_authenticated_user)
):
    """
    Query the RAG system with a natural language question.
    Returns a generated response with context documents.
    """
    try:
        context_docs = rag_service.search_similar_documents(request.query, top_k=request.top_k)
        response = rag_service.generate_response(request.query, context_docs)
        return QueryResponse(response=response, context_docs=context_docs)
    except Exception as e:
        logger.error(f"Failed to process RAG query: {e}")
        raise HTTPException(status_code=500, detail="Failed to process query")

@rag_router.post("/search", response_model=SearchResponse)
async def search_documents(
    request: SearchRequest,
    current_user: AuthenticatedUser = Depends(require_authenticated_user)
):
    """
    Search for documents similar to the query using cosine similarity.
    Returns a list of similar documents with their metadata.
    """
    try:
        results = rag_service.search_similar_documents(request.query, top_k=request.top_k)
        return SearchResponse(results=results)
    except Exception as e:
        logger.error(f"Failed to search documents: {e}")
        raise HTTPException(status_code=500, detail="Failed to search documents")