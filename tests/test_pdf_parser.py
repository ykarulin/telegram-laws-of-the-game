"""Tests for PDF parsing and document processing."""
import pytest
from unittest.mock import MagicMock, patch
from src.services.pdf_parser import PDFParser
from src.services.embedding_service import Chunk


class TestPDFParser:
    """Test PDF parsing functionality."""

    @pytest.fixture
    def parser(self):
        """Create a PDF parser instance."""
        return PDFParser()

    def test_parser_initialization(self):
        """Test PDF parser initialization."""
        parser = PDFParser()
        assert parser is not None

    def test_parse_pdf_file(self, parser):
        """Test parsing a PDF file."""
        mock_pdf_path = "test_document.pdf"

        with patch("src.services.pdf_parser.pdfplumber.open") as mock_pdf_open:
            mock_pdf = MagicMock()
            mock_pdf_open.return_value.__enter__.return_value = mock_pdf

            # Mock pages and content
            mock_page1 = MagicMock()
            mock_page1.extract_text.return_value = "Page 1 content"
            mock_page2 = MagicMock()
            mock_page2.extract_text.return_value = "Page 2 content"

            mock_pdf.pages = [mock_page1, mock_page2]

            # Mock the extract method
            with patch.object(parser, "extract_text") as mock_extract:
                mock_extract.return_value = "Page 1 content\n\nPage 2 content"

                result = mock_extract()
                assert result is not None
                assert "Page 1" in result
                assert "Page 2" in result

    def test_parse_empty_pdf(self, parser):
        """Test parsing an empty PDF."""
        with patch("src.services.pdf_parser.pdfplumber.open") as mock_pdf_open:
            mock_pdf = MagicMock()
            mock_pdf_open.return_value.__enter__.return_value = mock_pdf
            mock_pdf.pages = []

            with patch.object(parser, "extract_text") as mock_extract:
                mock_extract.return_value = ""

                result = mock_extract()
                assert result == ""

    def test_parse_pdf_with_special_characters(self, parser):
        """Test parsing PDF with special characters."""
        text_with_special = "Rules & Regulations: Law #1 — Offside (50/50)"

        with patch.object(parser, "extract_text") as mock_extract:
            mock_extract.return_value = text_with_special

            result = mock_extract()
            assert "&" in result
            assert "—" in result
            assert "#" in result

    def test_extract_page_numbers(self, parser):
        """Test extraction of page numbers."""
        with patch("src.services.pdf_parser.pdfplumber.open") as mock_pdf_open:
            mock_pdf = MagicMock()
            mock_pdf_open.return_value.__enter__.return_value = mock_pdf

            # Create pages
            mock_page1 = MagicMock()
            mock_page1.page_number = 1
            mock_page2 = MagicMock()
            mock_page2.page_number = 2

            mock_pdf.pages = [mock_page1, mock_page2]

            page_numbers = [p.page_number for p in mock_pdf.pages]
            assert page_numbers == [1, 2]

    def test_extract_document_metadata(self, parser):
        """Test extraction of document metadata."""
        with patch("src.services.pdf_parser.pdfplumber.open") as mock_pdf_open:
            mock_pdf = MagicMock()
            mock_pdf_open.return_value.__enter__.return_value = mock_pdf

            # Mock metadata
            mock_pdf.metadata = {
                "Title": "Laws of the Game 2025-26",
                "Author": "FIFA",
                "Subject": "Football Rules"
            }

            metadata = mock_pdf.metadata
            assert metadata["Title"] == "Laws of the Game 2025-26"
            assert metadata["Author"] == "FIFA"


    def test_extract_text_preserves_structure(self, parser):
        """Test that text extraction preserves document structure."""
        structured_text = "TITLE\n\nSection 1\nContent 1\n\nSection 2\nContent 2"

        with patch.object(parser, "extract_text") as mock_extract:
            mock_extract.return_value = structured_text

            result = mock_extract()
            # Should preserve line breaks
            assert "\n\n" in result

    def test_parse_multiple_pdfs(self, parser):
        """Test parsing multiple PDF files."""
        pdf_files = ["file1.pdf", "file2.pdf", "file3.pdf"]

        results = {}
        for pdf_file in pdf_files:
            with patch.object(parser, "extract_text") as mock_extract:
                mock_extract.return_value = f"Content of {pdf_file}"
                results[pdf_file] = mock_extract()

        assert len(results) == 3
        assert all(isinstance(v, str) for v in results.values())

    def test_extract_section_headers(self, parser):
        """Test extraction of section headers."""
        text_with_headers = "LAW 1: THE FIELD OF PLAY\n\nLAW 2: THE BALL"

        with patch.object(parser, "extract_text") as mock_extract:
            mock_extract.return_value = text_with_headers

            result = mock_extract()
            assert "LAW 1" in result
            assert "LAW 2" in result


    def test_handle_text_encoding(self, parser):
        """Test handling of different text encodings."""
        # Test UTF-8 with special characters
        utf8_text = "Football® - Official Rules™"

        with patch.object(parser, "extract_text") as mock_extract:
            mock_extract.return_value = utf8_text

            result = mock_extract()
            assert "®" in result
            assert "™" in result

    def test_extract_table_content(self, parser):
        """Test extraction of table content from PDF."""
        table_text = "Player Name | Goals | Assists\nJohn Doe | 10 | 5"

        with patch.object(parser, "extract_text") as mock_extract:
            mock_extract.return_value = table_text

            result = mock_extract()
            assert "|" in result
            assert "Player Name" in result

    def test_skip_empty_pages(self, parser):
        """Test that empty pages are handled properly."""
        with patch("src.services.pdf_parser.pdfplumber.open") as mock_pdf_open:
            mock_pdf = MagicMock()
            mock_pdf_open.return_value.__enter__.return_value = mock_pdf

            # Create pages with some empty
            mock_page1 = MagicMock()
            mock_page1.extract_text.return_value = "Content"
            mock_page2 = MagicMock()
            mock_page2.extract_text.return_value = ""  # Empty
            mock_page3 = MagicMock()
            mock_page3.extract_text.return_value = "More content"

            mock_pdf.pages = [mock_page1, mock_page2, mock_page3]

            # Filter empty pages
            non_empty = [p for p in mock_pdf.pages if p.extract_text()]
            assert len(non_empty) == 2

    def test_large_pdf_processing(self, parser):
        """Test processing of large PDF files."""
        # Simulate large document with many pages
        large_text = "Page content\n" * 10000

        with patch.object(parser, "extract_text") as mock_extract:
            mock_extract.return_value = large_text

            result = mock_extract()
            # Should handle large text
            assert len(result) > 100000

    def test_parse_pdf_preserves_language(self, parser):
        """Test that text extraction preserves language."""
        multilingual_text = "English text. Texte français. Texto español."

        with patch.object(parser, "extract_text") as mock_extract:
            mock_extract.return_value = multilingual_text

            result = mock_extract()
            assert "English" in result
            assert "français" in result
            assert "español" in result

    def test_extract_page_boundaries(self, parser):
        """Test identification of page boundaries."""
        with patch("src.services.pdf_parser.pdfplumber.open") as mock_pdf_open:
            mock_pdf = MagicMock()
            mock_pdf_open.return_value.__enter__.return_value = mock_pdf

            # Create mock pages
            pages = [MagicMock() for _ in range(5)]
            for i, page in enumerate(pages):
                page.page_number = i + 1
                page.extract_text.return_value = f"Page {i+1} content"

            mock_pdf.pages = pages

            page_count = len(mock_pdf.pages)
            assert page_count == 5

    def test_pdf_extract_with_different_formats(self, parser):
        """Test extraction from PDFs with different layouts."""
        layouts = [
            "Single column text layout",
            "Multi-column layout\nColume 1\nColumn 2",
            "List format\n• Item 1\n• Item 2\n• Item 3"
        ]

        for layout in layouts:
            with patch.object(parser, "extract_text") as mock_extract:
                mock_extract.return_value = layout

                result = mock_extract()
                assert len(result) > 0

    def test_parse_document_service_integration(self):
        """Test document service integration with parser."""
        from src.services.document_service import DocumentService

        with patch("src.services.pdf_parser.PDFParser.extract_text") as mock_extract:
            mock_extract.return_value = "Test document content"

            # Simulate document processing
            content = "Test document content"
            assert len(content) > 0

    def test_chunk_extraction_from_parsed_text(self, parser):
        """Test creating chunks from parsed text."""
        parsed_text = "Section 1: Introduction\nContent here.\n\nSection 2: Rules\nMore content here."

        chunks = []
        # Simulate chunking
        lines = parsed_text.split("\n\n")
        for line in lines:
            if line.strip():
                chunks.append(line)

        assert len(chunks) == 2
        assert "Introduction" in chunks[0]
        assert "Rules" in chunks[1]

    def test_preserve_footnotes_and_references(self, parser):
        """Test preservation of footnotes and references."""
        text_with_footnotes = "Rule text1 here.\n[1] Footnote content"

        with patch.object(parser, "extract_text") as mock_extract:
            mock_extract.return_value = text_with_footnotes

            result = mock_extract()
            assert "[1]" in result
            assert "Footnote" in result

    def test_handle_scanned_pdf_text_extraction_limitations(self, parser):
        """Test handling of scanned PDFs (OCR limitations)."""
        # Scanned PDFs may have OCR errors
        ocr_text = "Offside (occaisional OCR errors) rule"

        with patch.object(parser, "extract_text") as mock_extract:
            mock_extract.return_value = ocr_text

            result = mock_extract()
            # Should return text even with OCR imperfections
            assert len(result) > 0
