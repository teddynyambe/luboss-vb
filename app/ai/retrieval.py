"""RAG retrieval service."""
import json
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.models.ai import DocumentChunk, DocumentEmbedding
from typing import List, Dict, Any
from openai import OpenAI
from app.core.config import settings


def retrieve_relevant_chunks(
    db: Session,
    query: str,
    top_k: int = 5,
    document_name: str = None
) -> List[Dict[str, Any]]:
    """
    Retrieve relevant document chunks using MySQL VEC_DISTANCE_COSINE similarity.
    """
    if not settings.OPENAI_API_KEY:
        return []

    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    query_response = client.embeddings.create(
        model=settings.EMBEDDING_MODEL,
        input=query
    )
    query_embedding = query_response.data[0].embedding

    query_sql = """
        SELECT
            dc.id,
            dc.document_name,
            dc.version,
            dc.chunk_text,
            dc.page_number,
            dc.metadata,
            1 - VEC_DISTANCE_COSINE(de.embedding, VEC_FROM_TEXT(:query_embedding)) AS similarity
        FROM document_chunk dc
        JOIN document_embedding de ON dc.id = de.chunk_id
        WHERE de.model_name = :model_name
    """
    params: Dict[str, Any] = {
        "query_embedding": json.dumps(query_embedding),
        "model_name": settings.EMBEDDING_MODEL,
        "top_k": top_k,
    }
    if document_name:
        query_sql += " AND dc.document_name = :document_name"
        params["document_name"] = document_name

    query_sql += " ORDER BY similarity DESC LIMIT :top_k"

    try:
        rows = db.execute(text(query_sql), params).fetchall()
    except Exception:
        return []

    results = []
    for row in rows:
        results.append({
            "id": str(row.id),
            "document_name": row.document_name,
            "version": row.version,
            "chunk_text": row.chunk_text,
            "page_number": row.page_number,
            "metadata": row.metadata,
            "similarity": float(row.similarity) if row.similarity is not None else 0,
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
