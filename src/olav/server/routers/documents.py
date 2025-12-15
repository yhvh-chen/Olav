"""Documents API Router.

This module provides endpoints for managing RAG documents:
- List uploaded documents
- Upload new documents
- Delete documents
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from olav.server.auth import CurrentUser
from olav.server.models.document import (
    DocumentListResponse,
    DocumentSummary,
    DocumentUploadResponse,
)

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="List RAG documents",
    responses={
        200: {
            "description": "List of uploaded documents",
            "content": {
                "application/json": {
                    "example": {
                        "documents": [
                            {
                                "id": "cisco_bgp_guide",
                                "filename": "Cisco_BGP_Guide.pdf",
                                "file_type": "pdf",
                                "size_bytes": 1234567,
                                "uploaded_at": "2025-12-01T10:00:00Z",
                                "indexed": True,
                                "chunk_count": 326,
                            }
                        ],
                        "total": 1,
                    }
                }
            },
        },
    },
)
async def list_documents(current_user: CurrentUser) -> DocumentListResponse:
    """
    List all uploaded RAG documents from data/documents/.

    **Required**: Bearer token authentication
    """
    docs_dir = Path("data/documents")
    documents: list[DocumentSummary] = []

    supported_types = {".pdf", ".docx", ".doc", ".txt", ".md", ".html"}

    try:
        if docs_dir.exists():
            for doc_file in sorted(docs_dir.iterdir()):
                if doc_file.is_file() and doc_file.suffix.lower() in supported_types:
                    stat = doc_file.stat()

                    # Check if indexed (look for corresponding .indexed marker or index entries)
                    # For now, assume all existing files are indexed
                    indexed = True
                    chunk_count = 0  # Would query OpenSearch for actual count

                    documents.append(
                        DocumentSummary(
                            id=doc_file.stem,
                            filename=doc_file.name,
                            file_type=doc_file.suffix.lstrip(".").lower(),
                            size_bytes=stat.st_size,
                            uploaded_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            indexed=indexed,
                            chunk_count=chunk_count,
                        )
                    )

            return DocumentListResponse(documents=documents, total=len(documents))

    except Exception as e:
        logger.error(f"Failed to list documents: {e}")

    return DocumentListResponse(documents=[], total=0)


@router.post(
    "/documents/upload",
    response_model=DocumentUploadResponse,
    summary="Upload a document for RAG",
    responses={
        200: {"description": "Document uploaded successfully"},
        400: {"description": "Invalid file type"},
    },
)
async def upload_document(
    current_user: CurrentUser,
    file: Any = None,  # Would be UploadFile in real implementation
) -> DocumentUploadResponse:
    """
    Upload a document for RAG indexing.

    **Supported file types**: PDF, DOCX, TXT, MD, HTML

    **Required**: Bearer token authentication

    **Note**: This endpoint requires multipart/form-data.
    The actual file upload implementation requires FastAPI's UploadFile.

    **Example Request**:
    ```bash
    curl -X POST http://localhost:8000/documents/upload \\
      -H "Authorization: Bearer <token>" \\
      -F "file=@document.pdf"
    ```
    """
    # Placeholder - actual implementation would:
    # 1. Save file to data/documents/
    # 2. Trigger ETL pipeline to chunk and index
    # 3. Return document ID and status

    return DocumentUploadResponse(
        status="not_implemented",
        message="File upload requires multipart/form-data. This endpoint is a placeholder.",
        document_id=None,
        filename=None,
    )


@router.delete(
    "/documents/{document_id}",
    summary="Delete a document",
    responses={
        200: {"description": "Document deleted"},
        404: {"description": "Document not found"},
    },
)
async def delete_document(
    document_id: str,
    current_user: CurrentUser,
) -> dict:
    """
    Delete a document and remove it from the RAG index.

    **Required**: Bearer token authentication
    """
    docs_dir = Path("data/documents")

    # Find file with matching stem
    for doc_file in docs_dir.iterdir():
        if doc_file.stem == document_id:
            try:
                doc_file.unlink()
                # TODO: Also remove from OpenSearch index
                return {"status": "deleted", "document_id": document_id}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

    raise HTTPException(status_code=404, detail="Document not found")
