"""Text normalization and cleaning utilities for extracted document content."""

import re
import unicodedata


def clean_text(text: str) -> str:
    """Clean and normalize extracted document text for downstream processing.

    Applies:
    - NFKC Unicode normalization.
    - Removal of null bytes and non-printable control characters.
    - Reconnection of words hyphenated across line breaks.
    - Collapsing of excessive horizontal whitespace.
    - Normalization of consecutive newline characters (preserves paragraphs).

    Args:
        text: Raw extracted text string.

    Returns:
        Cleaned, normalized text.
    """
    if not text:
        return ""

    # 1. Unicode NFKC normalization (standardizes ligatures, full-width characters, etc.)
    normalized = unicodedata.normalize("NFKC", text)

    # 2. Remove null bytes and non-printable control characters (preserve \t, \n, \r)
    cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", normalized)

    # 3. Restore words hyphenated across linebreaks (e.g., 'regu-\nlation' -> 'regulation')
    cleaned = re.sub(r"(\b[a-zA-Z]+)-\n([a-zA-Z]+\b)", r"\1\2", cleaned)

    # 4. Normalize inline horizontal whitespace (tabs, multiple spaces -> single space)
    cleaned = re.sub(r"[^\S\r\n]+", " ", cleaned)

    # 5. Clean trailing whitespace per line
    lines = [line.strip() for line in cleaned.splitlines()]

    # 6. Collapse excessive consecutive linebreaks (3+ newlines -> 2 newlines)
    result = "\n".join(lines)
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()


def extract_snippet(text: str, max_chars: int = 200) -> str:
    """Extract a concise snippet from the beginning of text."""
    if not text:
        return ""
    cleaned = clean_text(text)
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[:max_chars].rstrip()}..."

