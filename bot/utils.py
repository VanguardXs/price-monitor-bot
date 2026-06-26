from html import escape


def safe_text(text: str) -> str:
    """Escape user-provided text before inserting into HTML-formatted messages"""
    if not text:
        return ""
    return escape(text, quote=False)


def split_lines(text: str, max_lines: int = 50, max_line_length: int = 80) -> list[str]:
    """Split multiline user input into a clean list of non-empty lines, with hard limits"""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    lines = lines[:max_lines]
    lines = [line[:max_line_length] for line in lines]
    return lines