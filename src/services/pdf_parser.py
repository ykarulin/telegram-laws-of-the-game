"""PDF document parsing and text extraction."""
import logging
import os
from typing import List, Dict, Any, Optional

import pdfplumber

logger = logging.getLogger(__name__)


class PDFParser:
    """Parse PDF documents and extract text content."""

    # Maximum file size: 100 MB
    MAX_FILE_SIZE = 100 * 1024 * 1024

    def __init__(self, max_file_size: int = MAX_FILE_SIZE):
        """Initialize PDF parser.

        Args:
            max_file_size: Maximum allowed file size in bytes
        """
        self.max_file_size = max_file_size

    def validate_file(self, file_path: str) -> bool:
        """Validate PDF file before processing.

        Args:
            file_path: Path to PDF file

        Returns:
            True if file is valid

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is invalid
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        if not file_path.lower().endswith(".pdf"):
            raise ValueError(f"File must be a PDF: {file_path}")

        file_size = os.path.getsize(file_path)
        if file_size > self.max_file_size:
            raise ValueError(
                f"File too large ({file_size} bytes). Max: {self.max_file_size} bytes"
            )

        if file_size == 0:
            raise ValueError("File is empty")

        logger.debug(f"Validated PDF file: {file_path} ({file_size} bytes)")
        return True

    def extract_text(self, file_path: str, preserve_layout: bool = False) -> str:
        """Extract all text from PDF.

        Args:
            file_path: Path to PDF file
            preserve_layout: If True, try to preserve text layout

        Returns:
            Extracted text content

        Raises:
            Exception: If PDF parsing fails
        """
        self.validate_file(file_path)

        try:
            full_text = ""
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    try:
                        if preserve_layout:
                            text = page.extract_text(layout=True)
                        else:
                            text = page.extract_text()

                        if text:
                            full_text += f"\n--- Page {page_num} ---\n{text}"
                    except Exception as e:
                        logger.warning(f"Failed to extract text from page {page_num}: {e}")
                        continue

            if not full_text.strip():
                raise ValueError("No text content could be extracted from PDF")

            logger.info(f"Extracted {len(full_text)} characters from {file_path}")
            return full_text
        except Exception as e:
            logger.error(f"PDF extraction failed for {file_path}: {e}")
            raise

    def extract_tables(self, file_path: str) -> List[List[List[str]]]:
        """Extract tables from PDF as structured data.

        Args:
            file_path: Path to PDF file

        Returns:
            List of tables, where each table is a list of rows, each row is a list of cells

        Raises:
            Exception: If PDF parsing fails
        """
        self.validate_file(file_path)

        try:
            all_tables = []
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    try:
                        tables = page.extract_tables()
                        if tables:
                            all_tables.extend(tables)
                            logger.debug(f"Extracted {len(tables)} tables from page {page_num}")
                    except Exception as e:
                        logger.warning(f"Failed to extract tables from page {page_num}: {e}")
                        continue

            logger.info(f"Extracted {len(all_tables)} total tables from {file_path}")
            return all_tables
        except Exception as e:
            logger.error(f"Table extraction failed for {file_path}: {e}")
            raise

    def extract_text_and_tables(
        self, file_path: str, preserve_layout: bool = False
    ) -> Dict[str, Any]:
        """Extract both text and tables from PDF.

        Args:
            file_path: Path to PDF file
            preserve_layout: If True, try to preserve text layout

        Returns:
            Dictionary with 'text' and 'tables' keys
        """
        text = self.extract_text(file_path, preserve_layout=preserve_layout)
        tables = self.extract_tables(file_path)

        return {
            "text": text,
            "tables": tables,
            "total_pages": len(pdfplumber.open(file_path).pages),
            "file_name": os.path.basename(file_path),
        }

    def get_pdf_info(self, file_path: str) -> Dict[str, Any]:
        """Get metadata about PDF file.

        Args:
            file_path: Path to PDF file

        Returns:
            Dictionary with PDF metadata
        """
        self.validate_file(file_path)

        try:
            with pdfplumber.open(file_path) as pdf:
                info = {
                    "file_name": os.path.basename(file_path),
                    "file_size": os.path.getsize(file_path),
                    "num_pages": len(pdf.pages),
                    "metadata": pdf.metadata,
                    "author": pdf.metadata.get("Author", "") if pdf.metadata else "",
                    "title": pdf.metadata.get("Title", "") if pdf.metadata else "",
                    "creation_date": pdf.metadata.get("CreationDate", "") if pdf.metadata else "",
                }
            logger.debug(f"Got PDF info: {info['num_pages']} pages")
            return info
        except Exception as e:
            logger.error(f"Failed to get PDF info for {file_path}: {e}")
            raise

    @staticmethod
    def format_table_as_markdown(table: List[List[str]]) -> str:
        """Format extracted table as markdown.

        Args:
            table: Table as list of rows, where each row is list of cells

        Returns:
            Markdown-formatted table string
        """
        if not table or not table[0]:
            return ""

        markdown = ""
        # Header row
        markdown += "| " + " | ".join(str(cell) if cell else "" for cell in table[0]) + " |\n"
        # Separator
        markdown += "|" + "|".join(["---"] * len(table[0])) + "|\n"
        # Data rows
        for row in table[1:]:
            markdown += "| " + " | ".join(str(cell) if cell else "" for cell in row) + " |\n"

        return markdown
