# RAG Strategy

## Document Ingestion

1. **PDF Extraction**: Use PyPDF2 to extract text
2. **Chunking**: Split by headings/clauses (~500-1000 tokens)
3. **Embedding**: Generate embeddings using OpenAI text-embedding-3-small
4. **Storage**: Store in pgvector with metadata (document, version, page, section)

## Retrieval

- **Vector Search**: Use pgvector cosine similarity
- **Top-K**: Retrieve top 5-10 most relevant chunks
- **Citations**: Include document version, page number, clause reference

## Constraints

- **Scope**: Only constitution, rules, policies, and member's own account
- **No Cross-Member Access**: All account queries are user-scoped
- **No Direct SQL**: LLM uses tool contracts only

## Tool Contracts

- `get_my_account_summary`: Member's account summary
- `get_my_loans`: Member's loans
- `get_my_penalties`: Member's penalties
- `get_my_declarations`: Member's declarations
- `explain_interest_rate`: Interest rate calculation
- `get_policy_answer`: RAG retrieval with citations
