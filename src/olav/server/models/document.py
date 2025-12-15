from pydantic import BaseModel

class DocumentSummary(BaseModel):
    """Summary of a RAG document."""
    id: str
    filename: str
    file_type: str  # "pdf", "docx", "txt", "md"
    size_bytes: int
    uploaded_at: str
    indexed: bool = False
    chunk_count: int = 0

class DocumentListResponse(BaseModel):
    """Response for document list endpoint."""
    documents: list[DocumentSummary]
    total: int

class DocumentUploadResponse(BaseModel):
    """Response from document upload."""
    status: str
    message: str
    document_id: str | None = None
    filename: str | None = None
