"""Document ingestion service for RAG."""
import PyPDF2
from typing import List, Dict
from app.models.ai import DocumentChunk, DocumentEmbedding
from app.models.system import ConstitutionDocumentVersion
from sqlalchemy.orm import Session
from openai import OpenAI
from app.core.config import settings
import uuid


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from PDF file."""
    with open(pdf_path, "rb") as file:
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
    return text


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
    text = extract_text_from_pdf(pdf_path)
    
    # Chunk text
    chunks = chunk_text(text)
    
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
        
        # Create embedding record
        from app.models.ai import DocumentEmbedding
        embedding = DocumentEmbedding(
            chunk_id=chunk.id,
            embedding=embedding_vector,
            model_name=settings.EMBEDDING_MODEL
        )
        db.add(embedding)
        
        document_chunks.append(chunk)
    
    db.commit()
    return document_chunks
