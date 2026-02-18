from sqlalchemy import Column, String, ForeignKey, DateTime, Integer, Text, JSON, Uuid, text
from sqlalchemy.orm import relationship
from app.db.types import MySQLVector
import uuid
from app.db.base import Base


class DocumentChunk(Base):
    """Document chunk for RAG."""
    __tablename__ = "document_chunk"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_name = Column(String(255), nullable=False, index=True)  # e.g., "constitution", "collateral_policy"
    version = Column(String(20), nullable=False, index=True)
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)  # Order within document
    page_number = Column(Integer, nullable=True)
    chunk_metadata = Column(JSON, nullable=True, name="metadata")  # Additional metadata (section, clause, etc.)
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    embedding = relationship("DocumentEmbedding", back_populates="chunk", uselist=False)


class DocumentEmbedding(Base):
    """Vector embedding for document chunk."""
    __tablename__ = "document_embedding"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id = Column(Uuid(as_uuid=True), ForeignKey("document_chunk.id"), nullable=False, unique=True, index=True)
    embedding = Column(MySQLVector(1536), nullable=False)  # OpenAI text-embedding-3-small dimension
    model_name = Column(String(100), nullable=False, default="text-embedding-3-small")
    created_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    # Relationships
    chunk = relationship("DocumentChunk", back_populates="embedding")


class AIAuditLog(Base):
    """AI chat audit log."""
    __tablename__ = "ai_audit_log"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True)
    query_text = Column(Text, nullable=False)
    tool_calls = Column(JSON, nullable=True)  # Array of tool calls made
    response = Column(Text, nullable=True)
    citations = Column(JSON, nullable=True)  # Array of citations (doc, version, page)
    timestamp = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True)
