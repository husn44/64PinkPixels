import hashlib
from pathlib import Path
import pdfplumber
from backend.config import settings


def parse_pdf(file_path: Path) -> tuple[str, str]:
    text_parts = []
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages[:10]):
            # Try layout mode first, then fallback to simple extraction
            page_text = page.extract_text(
                x_tolerance=3, y_tolerance=3, layout=True
            )
            if not page_text or not page_text.strip():
                page_text = page.extract_text(
                    x_tolerance=3, y_tolerance=3, layout=False
                )
            if page_text and page_text.strip():
                text_parts.append(page_text.strip())
            if i >= 9:
                break
    raw_text = "\n\n".join(text_parts)
    text_hash = hashlib.sha256(raw_text.encode()).hexdigest()
    return raw_text, text_hash


def parse_pdf_bytes(file_bytes: bytes, filename: str) -> tuple[str, str]:
    quotes_dir = settings.QUOTES_DIR
    quotes_dir.mkdir(parents=True, exist_ok=True)

    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    file_path = quotes_dir / safe_name
    file_path.write_bytes(file_bytes)

    return parse_pdf(file_path)
