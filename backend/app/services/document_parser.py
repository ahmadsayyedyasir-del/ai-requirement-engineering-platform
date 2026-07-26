"""
services/document_parser.py — Extracts plain text from uploaded files (Phase 2).

WHY THIS FILE EXISTS:
  Users can upload PDF or DOCX files containing their business requirements.
  Before the AI can analyze these files, we need to extract the plain text
  from them — the AI doesn't read binary file formats.

SUPPORTED FORMATS:
  .pdf   → pdfplumber (layout-aware, handles tables and multi-column PDFs well)
  .docx  → python-docx (Microsoft Word format)
  .txt   → plain read (already text, just needs decoding)

WHY asyncio.to_thread()?
  pdfplumber and python-docx are SYNCHRONOUS libraries — they block the thread
  while processing. In an async FastAPI application, blocking the event loop
  would freeze ALL other requests until parsing finishes.

  `asyncio.to_thread(fn, arg)` runs the synchronous function in a separate
  thread from Python's thread pool. The event loop continues handling other
  requests while the blocking PDF parsing happens in a worker thread.
  The `await` waits for the thread to finish without blocking the event loop.

  This is the standard pattern for using sync libraries in async Python code.
"""

# asyncio.to_thread — runs a synchronous function in a thread pool
import asyncio

# Path — clean way to work with file paths and extensions
from pathlib import Path


async def extract_text_from_file(file_path: str, ext: str) -> str:
    """
    Extract plain text from a file, dispatching to the correct parser by extension.

    This is the ONLY public function in this module — called by:
      - inputs.py (the _process_file_extraction background task)

    WHY ASYNC WRAPPER OVER SYNC PARSERS?
      The parsing libraries block the thread. Using asyncio.to_thread()
      moves them off the event loop so FastAPI stays responsive.

    Args:
        file_path: Absolute path to the saved file on disk.
        ext:       File extension (e.g., ".pdf", ".docx", ".txt")

    Returns:
        The extracted text content as a plain string, ready for the AI pipeline.

    Raises:
        ValueError: If the extension is not supported.
        Exception: If the file is corrupted, password-protected, etc.
    """
    ext = ext.lower()  # Normalize: ".PDF" → ".pdf"

    if ext == ".pdf":
        # Run the synchronous PDF parser in a thread pool to avoid blocking
        return await asyncio.to_thread(_extract_pdf, file_path)

    elif ext == ".docx":
        # Run the synchronous DOCX parser in a thread pool
        return await asyncio.to_thread(_extract_docx, file_path)

    elif ext == ".txt":
        # Text files can be read synchronously — they're fast and don't parse binary formats
        return await asyncio.to_thread(_extract_txt, file_path)

    else:
        raise ValueError(f"Unsupported file extension: {ext}")


def _extract_pdf(file_path: str) -> str:
    """
    Extract text from a PDF file using pdfplumber.

    WHY pdfplumber (not PyPDF2)?
      pdfplumber is "layout-aware" — it understands the spatial layout of text
      on the page, which helps with:
        - Multi-column PDFs (it doesn't scramble the columns)
        - PDFs with tables (it can extract table data meaningfully)
        - PDFs with headers/footers (it strips them more reliably)
      PyPDF2 extracts raw text stream which often comes out garbled for complex layouts.

    WHAT `page.extract_text()` DOES:
      Reads all text on a page and returns it as a string, preserving
      rough line breaks. Returns None for pages with only images (scanned PDFs).

    NOTE: Scanned PDFs (images of text, not actual text layers) won't work here.
    They'd need OCR (Optical Character Recognition) which is out of scope.
    """
    import pdfplumber  # Import here to avoid loading at startup if not needed

    pages = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:  # Skip blank pages and image-only pages
                pages.append(text.strip())

    # Join pages with double newline so page boundaries are visible in the extracted text
    return "\n\n".join(pages)


def _extract_docx(file_path: str) -> str:
    """
    Extract text from a Microsoft Word (.docx) file using python-docx.

    HOW DOCX FILES WORK:
      A .docx file is actually a ZIP archive containing XML files.
      python-docx unpacks the ZIP and reads the XML to extract paragraphs.
      Each `paragraph` object corresponds to a paragraph of text in Word.

    WHY CHECK p.text.strip()?
      Word documents often contain empty paragraphs used for spacing.
      Filtering out empty/whitespace-only paragraphs keeps the extracted
      text clean and avoids wasting LLM tokens on blank lines.

    LIMITATIONS:
      - Text in tables is NOT extracted (python-docx handles this separately)
      - Text in headers/footers is NOT extracted
      - Text in text boxes or images is NOT extracted
      These are acceptable limitations for a requirements document.
    """
    import docx  # python-docx — imports as `docx`

    doc = docx.Document(file_path)

    # Extract all non-empty paragraphs, stripping leading/trailing whitespace
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

    # Join with double newline to preserve paragraph structure
    return "\n\n".join(paragraphs)


def _extract_txt(file_path: str) -> str:
    """
    Read a plain text file directly.

    WHY errors="replace"?
      Some text files use non-UTF-8 encodings (e.g., Windows-1252 for older docs).
      `errors="replace"` replaces any undecodable characters with the Unicode
      replacement character (?) instead of raising an exception.
      This is safer than crashing on a single bad character.
    """
    return Path(file_path).read_text(encoding="utf-8", errors="replace")
