import sys
import os

# Add the parent directory to the path so we can import from the backend
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.rag import RAGService

def test_rag_service():
    """Test the RAG service with a sample query."""
    try:
        # Initialize the RAG service
        rag_service = RAGService()
        
        # Test query
        query = "What services are available for immigrants?"
        
        print(f"Testing RAG service with query: {query}")
        print("=" * 50)
        
        # Search for similar documents
        print("Searching for similar documents...")
        results = rag_service.search_similar_documents(query, top_k=3)
        
        print(f"Found {len(results)} similar documents:")
        for i, doc in enumerate(results):
            print(f"\nDocument {i+1}:")
            print(f"  Similarity Score: {doc.get('similarity_score', 0):.4f}")
            print(f"  Text: {doc.get('text', '')[:200]}...")
        
        print("\n" + "=" * 50)
        
        # Generate response
        print("Generating response...")
        response = rag_service.generate_response(query, results)
        print(f"Generated response:\n{response}")
        
        print("\n" + "=" * 50)
        
        # Test the query method
        print("Testing query method...")
        response2 = rag_service.query(query)
        print(f"Query method response:\n{response2}")
        
    except Exception as e:
        print(f"Error testing RAG service: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_rag_service()