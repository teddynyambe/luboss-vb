"""RAG retrieval service."""
import json
import math
from sqlalchemy.orm import Session
from app.models.ai import DocumentChunk, DocumentEmbedding
from typing import List, Dict, Any
from openai import OpenAI
from app.core.config import settings


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def retrieve_relevant_chunks(
    db: Session,
    query: str,
    top_k: int = 5,
    document_name: str = None
) -> List[Dict[str, Any]]:
    """
    Retrieve relevant document chunks using cosine similarity.
    Embeddings are stored as JSON text; similarity is computed in Python.
    """
    if not settings.OPENAI_API_KEY:
        return []

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    query_response = client.embeddings.create(
        model=settings.EMBEDDING_MODEL,
        input=query
    )
    query_embedding = query_response.data[0].embedding

    # Fetch all chunks with embeddings
    try:
        q = db.query(DocumentChunk, DocumentEmbedding).join(
            DocumentEmbedding, DocumentChunk.id == DocumentEmbedding.chunk_id
        ).filter(DocumentEmbedding.model_name == settings.EMBEDDING_MODEL)

        if document_name:
            q = q.filter(DocumentChunk.document_name == document_name)

        rows = q.all()
    except Exception:
        return []

    if not rows:
        return []

    # Compute similarity for each chunk
    scored = []
    for chunk, emb in rows:
        # Parse embedding from JSON string or list
        embedding_data = emb.embedding
        if isinstance(embedding_data, str):
            try:
                embedding_data = json.loads(embedding_data)
            except (json.JSONDecodeError, ValueError):
                continue
        if not isinstance(embedding_data, (list, tuple)):
            continue

        similarity = _cosine_similarity(query_embedding, embedding_data)
        scored.append((chunk, similarity))

    # Sort by similarity descending and take top_k
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:top_k]

    results = []
    for chunk, similarity in top:
        results.append({
            "id": str(chunk.id),
            "document_name": chunk.document_name,
            "version": chunk.version,
            "chunk_text": chunk.chunk_text,
            "page_number": chunk.page_number,
            "metadata": chunk.chunk_metadata,
            "similarity": similarity,
        })
    return results


def format_citations(chunks: List[Dict]) -> List[Dict]:
    """Format chunks as citations."""
    citations = []
    for chunk in chunks:
        text_preview = (chunk.get("chunk_text") or "")[:200]
        citations.append({
            "document": chunk.get("document_name"),
            "version": chunk.get("version"),
            "page": chunk.get("page_number"),
            "text": text_preview,
        })
    return citations
