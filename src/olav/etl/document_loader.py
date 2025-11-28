"""Document loader for RAG indexing.

Loads documents from various formats (PDF, Markdown, TXT) and prepares
them for embedding and indexing in OpenSearch.

Supported formats:
- PDF (via pdfplumber)
- Markdown (.md)
- Plain text (.txt)
- YAML (.yaml, .yml) - for config reference docs
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Supported file extensions
SUPPORTED_EXTENSIONS = {".pdf", ".md", ".txt", ".yaml", ".yml", ".rst"}

# Chunk size configuration
DEFAULT_CHUNK_SIZE = 1000  # characters
DEFAULT_CHUNK_OVERLAP = 200  # characters


@dataclass
class DocumentChunk:
    """A chunk of document content for embedding.

    Attributes:
        content: Text content of the chunk
        metadata: Document metadata (source, page, vendor, etc.)
        chunk_id: Unique identifier for this chunk
    """

    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_id: str = ""

    def __post_init__(self) -> None:
        if not self.chunk_id and self.metadata.get("source"):
            # Generate chunk_id from source + chunk index
            source = self.metadata["source"]
            chunk_idx = self.metadata.get("chunk_index", 0)
            self.chunk_id = f"{source}:{chunk_idx}"


@dataclass
class Document:
    """A loaded document with content and metadata.

    Attributes:
        content: Full text content
        metadata: Document metadata
        source: Source file path
    """

    content: str
    metadata: dict[str, Any]
    source: str

    @property
    def word_count(self) -> int:
        """Get approximate word count."""
        return len(self.content.split())

    @property
    def char_count(self) -> int:
        """Get character count."""
        return len(self.content)


class TextSplitter:
    """Split text into chunks with configurable size and overlap.

    Uses recursive character-based splitting similar to LangChain's
    RecursiveCharacterTextSplitter.
    """

    # Split separators in order of preference
    SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> None:
        """Initialize text splitter.

        Args:
            chunk_size: Maximum chunk size in characters
            chunk_overlap: Overlap between chunks in characters
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str) -> list[str]:
        """Split text into chunks.

        Args:
            text: Text to split

        Returns:
            List of text chunks
        """
        if len(text) <= self.chunk_size:
            return [text]

        return self._recursive_split(text, self.SEPARATORS)

    def _recursive_split(self, text: str, separators: list[str]) -> list[str]:
        """Recursively split text using separators.

        Args:
            text: Text to split
            separators: List of separators to try

        Returns:
            List of text chunks
        """
        if not separators:
            # No more separators, force split at chunk_size
            return self._force_split(text)

        separator = separators[0]
        if separator == "":
            # Character-level split
            return self._force_split(text)

        splits = text.split(separator)

        # Merge small splits and split large ones
        chunks: list[str] = []
        current_chunk = ""

        for split in splits:
            # Add separator back (except for first split)
            piece = split if not current_chunk else separator + split

            if len(current_chunk) + len(piece) <= self.chunk_size:
                current_chunk += piece
            else:
                if current_chunk:
                    chunks.append(current_chunk)

                # Check if piece itself needs splitting
                if len(split) > self.chunk_size:
                    # Recursively split with next separator
                    sub_chunks = self._recursive_split(split, separators[1:])
                    chunks.extend(sub_chunks[:-1])
                    current_chunk = sub_chunks[-1] if sub_chunks else ""
                else:
                    current_chunk = split

        if current_chunk:
            chunks.append(current_chunk)

        # Add overlap between chunks
        return self._add_overlap(chunks)

    def _force_split(self, text: str) -> list[str]:
        """Force split text at chunk_size boundaries.

        Args:
            text: Text to split

        Returns:
            List of text chunks
        """
        chunks = []
        for i in range(0, len(text), self.chunk_size - self.chunk_overlap):
            chunk = text[i : i + self.chunk_size]
            if chunk:
                chunks.append(chunk)
        return chunks

    def _add_overlap(self, chunks: list[str]) -> list[str]:
        """Add overlap between consecutive chunks.

        Args:
            chunks: List of chunks without overlap

        Returns:
            List of chunks with overlap added
        """
        if len(chunks) <= 1 or self.chunk_overlap == 0:
            return chunks

        result = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_chunk = chunks[i - 1]
            overlap_text = (
                prev_chunk[-self.chunk_overlap :]
                if len(prev_chunk) > self.chunk_overlap
                else prev_chunk
            )
            result.append(overlap_text + chunks[i])

        return result


class DocumentLoader:
    """Load documents from various file formats.

    Supports:
    - PDF files (requires pdfplumber)
    - Markdown files
    - Plain text files
    - YAML/config files

    Example:
        >>> loader = DocumentLoader()
        >>> doc = loader.load_file(Path("manual.pdf"))
        >>> chunks = loader.chunk_document(doc)
    """

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> None:
        """Initialize document loader.

        Args:
            chunk_size: Chunk size for text splitting
            chunk_overlap: Overlap between chunks
        """
        self.splitter = TextSplitter(chunk_size, chunk_overlap)
        self._pdf_available = self._check_pdf_support()

    def _check_pdf_support(self) -> bool:
        """Check if PDF support is available."""
        try:
            import pdfplumber  # noqa: F401

            return True
        except ImportError:
            logger.warning("pdfplumber not installed. PDF support disabled.")
            return False

    def load_file(self, path: Path) -> Document | None:
        """Load a single document file.

        Args:
            path: Path to document file

        Returns:
            Document object or None if loading failed
        """
        if not path.exists():
            logger.error(f"File not found: {path}")
            return None

        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            logger.warning(f"Unsupported file format: {suffix}")
            return None

        try:
            if suffix == ".pdf":
                return self._load_pdf(path)
            if suffix == ".md":
                return self._load_markdown(path)
            if suffix in {".yaml", ".yml"}:
                return self._load_yaml(path)
            return self._load_text(path)
        except Exception as e:
            logger.error(f"Failed to load {path}: {e}")
            return None

    def _load_pdf(self, path: Path) -> Document | None:
        """Load PDF file using pdfplumber.

        Args:
            path: Path to PDF file

        Returns:
            Document object or None
        """
        if not self._pdf_available:
            logger.error("PDF support not available. Install pdfplumber.")
            return None

        import pdfplumber

        text_parts: list[str] = []
        page_count = 0

        with pdfplumber.open(path) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)

        content = "\n\n".join(text_parts)

        return Document(
            content=content,
            metadata={
                "source": str(path),
                "format": "pdf",
                "page_count": page_count,
                "vendor": self._infer_vendor(path),
                "document_type": self._infer_document_type(path),
            },
            source=str(path),
        )

    def _load_markdown(self, path: Path) -> Document:
        """Load Markdown file.

        Args:
            path: Path to Markdown file

        Returns:
            Document object
        """
        content = path.read_text(encoding="utf-8")

        # Extract title from first heading
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = title_match.group(1) if title_match else path.stem

        return Document(
            content=content,
            metadata={
                "source": str(path),
                "format": "markdown",
                "title": title,
                "vendor": self._infer_vendor(path),
                "document_type": self._infer_document_type(path),
            },
            source=str(path),
        )

    def _load_yaml(self, path: Path) -> Document:
        """Load YAML file as reference document.

        Args:
            path: Path to YAML file

        Returns:
            Document object
        """
        content = path.read_text(encoding="utf-8")

        return Document(
            content=content,
            metadata={
                "source": str(path),
                "format": "yaml",
                "vendor": self._infer_vendor(path),
                "document_type": "configuration",
            },
            source=str(path),
        )

    def _load_text(self, path: Path) -> Document:
        """Load plain text file.

        Args:
            path: Path to text file

        Returns:
            Document object
        """
        content = path.read_text(encoding="utf-8")

        return Document(
            content=content,
            metadata={
                "source": str(path),
                "format": "text",
                "vendor": self._infer_vendor(path),
                "document_type": self._infer_document_type(path),
            },
            source=str(path),
        )

    def _infer_vendor(self, path: Path) -> str:
        """Infer vendor from file path or name.

        Args:
            path: File path

        Returns:
            Vendor name or "unknown"
        """
        path_lower = str(path).lower()

        # Check path components and filename for vendor keywords
        vendors = {
            "cisco": ["cisco", "ios", "nxos", "iosxr", "iosxe"],
            "arista": ["arista", "eos"],
            "juniper": ["juniper", "junos"],
            "paloalto": ["paloalto", "panos"],
            "fortinet": ["fortinet", "fortigate", "fortios"],
            "huawei": ["huawei", "vrp"],
            "nokia": ["nokia", "sros"],
            "ietf": ["rfc", "ietf"],
            "openconfig": ["openconfig", "yang"],
        }

        for vendor, keywords in vendors.items():
            if any(kw in path_lower for kw in keywords):
                return vendor

        return "unknown"

    def _infer_document_type(self, path: Path) -> str:
        """Infer document type from file path or name.

        Args:
            path: File path

        Returns:
            Document type
        """
        path_lower = str(path).lower()
        name_lower = path.stem.lower()

        type_keywords = {
            "manual": ["manual", "guide", "handbook"],
            "configuration": ["config", "configuration", "setup"],
            "reference": ["reference", "api", "command"],
            "troubleshooting": ["troubleshoot", "debug", "diagnos"],
            "release_notes": ["release", "changelog", "notes"],
            "rfc": ["rfc"],
        }

        for doc_type, keywords in type_keywords.items():
            if any(kw in path_lower or kw in name_lower for kw in keywords):
                return doc_type

        return "general"

    def chunk_document(self, doc: Document) -> list[DocumentChunk]:
        """Split document into chunks for embedding.

        Args:
            doc: Document to chunk

        Returns:
            List of DocumentChunk objects
        """
        text_chunks = self.splitter.split_text(doc.content)

        chunks = []
        for i, text in enumerate(text_chunks):
            chunk = DocumentChunk(
                content=text,
                metadata={
                    **doc.metadata,
                    "chunk_index": i,
                    "total_chunks": len(text_chunks),
                },
            )
            chunks.append(chunk)

        return chunks

    def load_directory(
        self,
        directory: Path,
        recursive: bool = True,
    ) -> Iterator[Document]:
        """Load all documents from a directory.

        Args:
            directory: Directory path
            recursive: Whether to search recursively

        Yields:
            Document objects
        """
        if not directory.exists():
            logger.error(f"Directory not found: {directory}")
            return

        pattern = "**/*" if recursive else "*"

        for path in directory.glob(pattern):
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                doc = self.load_file(path)
                if doc:
                    yield doc


def load_and_chunk_documents(
    directory: Path,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> Iterator[DocumentChunk]:
    """Convenience function to load and chunk all documents in a directory.

    Args:
        directory: Directory containing documents
        chunk_size: Chunk size for splitting
        chunk_overlap: Overlap between chunks

    Yields:
        DocumentChunk objects ready for embedding
    """
    loader = DocumentLoader(chunk_size, chunk_overlap)

    for doc in loader.load_directory(directory):
        logger.info(f"Processing: {doc.source} ({doc.word_count} words)")
        yield from loader.chunk_document(doc)
