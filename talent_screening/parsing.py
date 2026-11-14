"""Turn an uploaded or emailed resume file into plain text, and flag suspicious content."""
import io
import re

from docx import Document
from pypdf import PdfReader

MAX_CHARS = 20_000     # a resume longer than this is truncated (protects the LLM token budget)


class UnsupportedFile(Exception):
    pass


def extract_text(data: bytes, filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif name.endswith(".docx"):
        doc = Document(io.BytesIO(data))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        text = "\n".join(parts)
    elif name.endswith((".txt", ".md")):
        text = data.decode("utf-8", errors="replace")
    else:
        raise UnsupportedFile(f"Unsupported file type: {filename}. Send PDF, DOCX or TXT.")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 100:
        raise UnsupportedFile("Could not read enough text from the file (is it a scanned image?).")
    return text[:MAX_CHARS]


# Phrases that try to steer an automated screener. They never change the score (scoring is code),
# but HR should see them.
INJECTION_PATTERNS = [
    r"ignore (all |any )?(the )?(previous|prior|above|earlier) (instructions|prompts?)",
    r"(disregard|forget) (all |your )?(previous |prior )?(instructions|rules)",
    r"\byou are (now )?(an?|the) (ai|assistant|model|screener|recruiter)",
    r"(score|rate|rank) (this|the|me|my)?\s*(candidate|resume|cv|application)?\s*(as|at|with)?\s*\d{2,3}",
    r"(give|assign) (this candidate|me|him|her|them) (a )?(score|rating) of",
    r"system prompt|developer message|\[system\]|<\|im_start\|>",
    r"(shortlist|hire|select) (this candidate|me) (immediately|now|regardless)",
]
_INJ = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def suspicious_phrases(text: str) -> list[str]:
    hits = []
    for pat in _INJ:
        for m in pat.finditer(text):
            hits.append(" ".join(text[max(0, m.start() - 20):m.end() + 20].split()))
    return hits[:5]
