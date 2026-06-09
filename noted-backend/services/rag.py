import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
import json
import logging
import ollama
import requests
import os
from sklearn.metrics.pairwise import cosine_similarity
from pathlib import Path

logger = logging.getLogger(__name__)

class RAGService:
    """
    RAG Service that uses Hugging Face API for embeddings and Ollama for generation.
    """
    
    def __init__(self, parquet_file_path=None, generation_model=None):
        """
        Initialize RAG service.
        
        Args:
            parquet_file_path: Path to the parquet file with embeddings and texts
            generation_model: Ollama model name for generating responses
        """
        self.parquet_file_path = (
            parquet_file_path
            or os.getenv("PARQUET_PATH")
            or "/data/noted_s2t_pipeline/outputs/rag_pipeline/rag_embeddings.parquet"
        )
        self.generation_model = (
            generation_model
            or os.getenv("OLLAMA_MODEL")
            or os.getenv("SUMMARY_MODEL")
            or "gpt-oss:120b-cloud"
        )
        self.ollama_host = os.getenv("OLLAMA_HOST")
        self.ollama_api_key = os.getenv("OLLAMA_API_KEY")

        # Hugging Face API configuration for embeddings
        self.hf_api_token = os.getenv("HUGGINGFACEHUB_API_TOKEN") or os.getenv("HF_TOKEN")
        if not self.hf_api_token:
            logger.warning("No Hugging Face API token found. Set HUGGINGFACEHUB_API_TOKEN or HF_TOKEN")

        self.hf_api_url = os.getenv(
            "HUGGINGFACE_EMBED_URL",
            "https://api-inference.huggingface.co/pipeline/feature-extraction/Qwen/Qwen3-Embedding-8B",
        )

        self.ollama_client = ollama.Client(host=self.ollama_host)

        logger.info("RAG service configured with Ollama host=%s model=%s", self.ollama_host, self.generation_model)
        logger.info("Embedding endpoint=%s", self.hf_api_url)

        self.data = None
        self.embeddings = None
        self.texts = None

        self._load_data()
    
    def _load_data(self):
        """Load the parquet file and prepare embeddings for similarity search."""
        try:
            self.data = pd.read_parquet(self.parquet_file_path)
            self.embeddings = np.array(self.data['embedding'].tolist())
            self.texts = self.data['text'].tolist()
            logger.info(f"Loaded {len(self.texts)} documents for RAG service from {self.parquet_file_path}")
            
            # Log embedding dimension to verify compatibility
            if len(self.embeddings) > 0:
                embedding_dim = len(self.embeddings[0])
                logger.info(f"Stored embedding dimension: {embedding_dim}")
        except Exception as e:
            logger.error(f"Failed to load parquet file: {e}")
            raise
    
    def _get_text_embedding(self, text: str) -> List[float]:
        """
        Get embedding for a query text using Hugging Face Inference API.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector (4096 dimensions for Qwen3-Embedding-8B)
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.hf_api_token}",
                "Content-Type": "application/json"
            }
            
            # The API expects the input text directly
            payload = {"inputs": text}
            
            response = requests.post(self.hf_api_url, headers=headers, json=payload, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"Hugging Face API error: {response.status_code} - {response.text}")
                # Fallback: return zero vector of appropriate dimension
                if self.embeddings is not None and len(self.embeddings) > 0:
                    return [0.0] * self.embeddings.shape[1]
                return [0.0] * 4096  # Qwen3-Embedding-8B default dimension
            
            embedding = response.json()
            
            # The response may be nested. For feature-extraction pipeline, it returns a list of lists
            if isinstance(embedding, list) and len(embedding) > 0 and isinstance(embedding[0], list):
                embedding = embedding[0]  # Extract the actual embedding vector
            
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to get embedding for text: {e}")
            # Return a zero vector as fallback
            if self.embeddings is not None and len(self.embeddings) > 0:
                return [0.0] * self.embeddings.shape[1]
            return [0.0] * 4096
    
    def search_similar_documents(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search for documents similar to the query using cosine similarity.
        
        Args:
            query: Query text
            top_k: Number of top similar documents to return
            
        Returns:
            List of similar documents with their metadata
        """
        try:
            # Get embedding for the query
            query_embedding = self._get_text_embedding(query)
            query_embedding = np.array(query_embedding).reshape(1, -1)
            
            # Calculate cosine similarities
            similarities = cosine_similarity(query_embedding, self.embeddings)[0]
            
            # Get top-k most similar documents
            top_indices = np.argsort(similarities)[::-1][:top_k]
            
            # Prepare results
            results = []
            for idx in top_indices:
                doc_data = self.data.iloc[idx].to_dict()
                doc_data['similarity_score'] = float(similarities[idx])
                results.append(self._normalize_doc(doc_data))
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to search similar documents: {e}")
            return []

    def _normalize_doc(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Convert pandas/numpy document fields to JSON-safe Python values."""
        def default(o):
            if isinstance(o, np.generic):
                return o.item()
            if isinstance(o, np.ndarray):
                return o.tolist()
            return str(o)

        return json.loads(json.dumps(doc, default=default))
    
    def generate_response(self, query: str, context_docs: List[Dict[str, Any]] = None) -> str:
        """
        Generate a response using Ollama with the provided context.
        
        Args:
            query: User query
            context_docs: Context documents to use for generation
            
        Returns:
            Generated response
        """
        try:
            if context_docs is None:
                context_docs = self.search_similar_documents(query, top_k=3)
            
            # Prepare context text
            context_text = "\n\n".join([
                f"Context {i+1} (Similarity: {doc.get('similarity_score', 0):.2f}):\n{doc['text']}"
                for i, doc in enumerate(context_docs)
            ])
            
            # Create prompt with context
            prompt = f"""
You are a helpful assistant that answers questions based on the provided context.
Use the following context information to answer the user's question accurately.

Context Information:
{context_text}

User Question: {query}

Please provide a helpful and accurate response based on the context provided above.
If the context doesn't contain relevant information, acknowledge that and provide general guidance.
"""
            
            # Generate response using Ollama
            response = self.ollama_client.chat(
                model=self.generation_model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            message = getattr(response, 'message', None)
            if message is None:
                raise RuntimeError("Ollama response did not contain message content")
            return getattr(message, 'content', str(response))
            
        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            return "I apologize, but I encountered an error while processing your request. Please try again later."
    
    def query(self, query: str) -> str:
        """
        Main method to query the RAG system.
        
        Args:
            query: User query
            
        Returns:
            Generated response
        """
        try:
            context_docs = self.search_similar_documents(query, top_k=3)
            response = self.generate_response(query, context_docs)
            return response
        except Exception as e:
            logger.error(f"Failed to process query: {e}")
            return "I apologize, but I encountered an error while processing your request. Please try again later."