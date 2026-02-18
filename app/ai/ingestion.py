"""Document ingestion service for RAG."""
import json
import PyPDF2
import uuid
from typing import List, Dict
from app.models.ai import DocumentChunk, DocumentEmbedding
from app.models.system import ConstitutionDocumentVersion
from sqlalchemy.orm import Session
from sqlalchemy import text
from openai import OpenAI
from app.core.config import settings


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from PDF file."""
    with open(pdf_path, "rb") as file:
        pdf_reader = PyPDF2.PdfReader(file)
        text_content = ""
        for page in pdf_reader.pages:
            text_content += page.extract_text() + "\n"
    return text_content


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[Dict]:
    """
    Chunk text by headings/clauses.
    Simplified: splits by paragraphs and combines to ~chunk_size tokens.
    """
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = ""
    current_page = 1

    for para in paragraphs:
        if len(current_chunk) + len(para) > chunk_size and current_chunk:
            chunks.append({
                "text": current_chunk.strip(),
                "page": current_page
            })
            current_chunk = para
        else:
            current_chunk += "\n\n" + para if current_chunk else para

    if current_chunk:
        chunks.append({
            "text": current_chunk.strip(),
            "page": current_page
        })

    return chunks


def generate_embeddings(text: str) -> List[float]:
    """Generate embedding using OpenAI."""
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.embeddings.create(
        model=settings.EMBEDDING_MODEL,
        input=text
    )
    return response.data[0].embedding


def ingest_document(
    db: Session,
    document_name: str,
    version: str,
    pdf_path: str
) -> List[DocumentChunk]:
    """Ingest a document (PDF) into the RAG system."""
    # Extract text
    text_content = extract_text_from_pdf(pdf_path)

    # Chunk text
    chunks = chunk_text(text_content)

    # Create document chunks and embeddings
    document_chunks = []
    for idx, chunk_data in enumerate(chunks):
        # Create chunk
        chunk = DocumentChunk(
            document_name=document_name,
            version=version,
            chunk_text=chunk_data["text"],
            chunk_index=idx,
            page_number=chunk_data.get("page", 1),
            chunk_metadata={"section": "auto"}
        )
        db.add(chunk)
        db.flush()

        # Generate embedding
        embedding_vector = generate_embeddings(chunk_data["text"])

        # Insert embedding using raw SQL — MySQL VECTOR column requires VEC_FROM_TEXT()
        embedding_id = uuid.uuid4()
        db.execute(text("""
            INSERT INTO document_embedding (id, chunk_id, embedding, model_name, created_at)
            VALUES (:id, :chunk_id, VEC_FROM_TEXT(:embedding), :model_name, NOW())
        """), {
            'id': str(embedding_id),
            'chunk_id': str(chunk.id),
            'embedding': json.dumps(embedding_vector),
            'model_name': settings.EMBEDDING_MODEL,
        })

        document_chunks.append(chunk)

    db.commit()
    return document_chunks


def ingest_text_content(
    db: Session,
    document_name: str,
    version: str,
    text_content: str
) -> List[DocumentChunk]:
    """Ingest raw text content into the RAG system (no PDF extraction needed).

    Deletes any existing chunks for the same document_name + version before
    inserting new ones, ensuring the document is always fresh.
    """
    # Delete existing chunks (embeddings cascade via FK or are cleaned separately)
    existing_chunks = db.query(DocumentChunk).filter(
        DocumentChunk.document_name == document_name,
        DocumentChunk.version == version
    ).all()
    for chunk in existing_chunks:
        db.query(DocumentEmbedding).filter(
            DocumentEmbedding.chunk_id == chunk.id
        ).delete(synchronize_session=False)
    db.query(DocumentChunk).filter(
        DocumentChunk.document_name == document_name,
        DocumentChunk.version == version
    ).delete(synchronize_session=False)
    db.flush()

    # Chunk the text
    chunks = chunk_text(text_content)

    # Create document chunks and embeddings
    document_chunks = []
    for idx, chunk_data in enumerate(chunks):
        chunk = DocumentChunk(
            document_name=document_name,
            version=version,
            chunk_text=chunk_data["text"],
            chunk_index=idx,
            page_number=chunk_data.get("page", 1),
            chunk_metadata={"section": "auto"}
        )
        db.add(chunk)
        db.flush()

        # Generate embedding
        embedding_vector = generate_embeddings(chunk_data["text"])

        embedding_id = uuid.uuid4()
        db.execute(text("""
            INSERT INTO document_embedding (id, chunk_id, embedding, model_name, created_at)
            VALUES (:id, :chunk_id, VEC_FROM_TEXT(:embedding), :model_name, NOW())
        """), {
            'id': str(embedding_id),
            'chunk_id': str(chunk.id),
            'embedding': json.dumps(embedding_vector),
            'model_name': settings.EMBEDDING_MODEL,
        })

        document_chunks.append(chunk)

    db.commit()
    return document_chunks
