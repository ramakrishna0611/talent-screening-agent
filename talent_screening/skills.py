"""Skill names: one canonical form per skill, and detection in resume text.

A skill only counts if it literally appears in the resume (under any known alias). The LLM helps
structure the resume, but it cannot add a skill the candidate never wrote.
"""
import re

# canonical -> aliases (all lower case). Keep aliases specific to avoid false matches.
ALIASES: dict[str, list[str]] = {
    "python": ["python", "python3"],
    "fastapi": ["fastapi", "fast api"],
    "django": ["django"],
    "flask": ["flask"],
    "sql": ["sql", "mysql", "postgresql", "postgres", "sql server", "t-sql", "pl/sql", "sqlite"],
    "rest apis": ["rest api", "rest apis", "restful", "rest services", "rest endpoints"],
    "docker": ["docker", "dockerfile", "containers"],
    "aws": ["aws", "amazon web services", "ec2", "s3", "lambda"],
    "redis": ["redis"],
    "java": ["java"],
    "spring boot": ["spring boot", "spring"],
    "apex": ["apex"],
    "lwc": ["lwc", "lightning web components", "lightning web component"],
    "soql": ["soql"],
    "salesforce flows": ["salesforce flow", "salesforce flows", "flow builder", "record-triggered flow",
                         "record-triggered flows", "screen flow", "screen flows"],
    "agentforce": ["agentforce"],
    "salesforce integration": ["named credential", "named credentials", "platform events", "salesforce rest api",
                               "callouts", "apex callouts"],
    "data cloud": ["data cloud"],
    "llm apis": ["openai api", "claude api", "anthropic api", "gemini api", "llm api", "llm apis", "gpt-4",
                 "chat completions", "groq"],
    "rag": ["rag", "retrieval-augmented", "retrieval augmented"],
    "prompt engineering": ["prompt engineering", "prompt design", "prompting"],
    "langchain": ["langchain", "langgraph"],
    "vector databases": ["vector database", "vector databases", "vector db", "chromadb", "chroma", "pinecone",
                         "pgvector", "faiss", "weaviate", "qdrant"],
    "llm evaluation": ["ragas", "llm evaluation", "llm-as-a-judge", "llm-as-judge", "evaluation set", "evals"],
    "excel": ["excel", "spreadsheets"],
    "pandas": ["pandas"],
    "power bi": ["power bi", "powerbi"],
    "tableau": ["tableau"],
    "statistics": ["statistics", "statistical", "hypothesis testing", "a/b testing", "regression analysis"],
    "javascript": ["javascript", "js", "es6"],
    "typescript": ["typescript"],
    "react": ["react", "react.js", "reactjs"],
    "next.js": ["next.js", "nextjs"],
    "html": ["html", "html5"],
    "css": ["css", "css3", "tailwind", "sass"],
    "frontend testing": ["jest", "react testing library", "cypress", "playwright", "vitest"],
    "machine learning": ["machine learning", "scikit-learn", "sklearn", "xgboost"],
}
DISPLAY = {"sql": "SQL", "rest apis": "REST APIs", "aws": "AWS", "lwc": "LWC", "soql": "SOQL", "rag": "RAG",
           "llm apis": "LLM APIs", "llm evaluation": "LLM evaluation", "html": "HTML", "css": "CSS",
           "power bi": "Power BI", "next.js": "Next.js", "fastapi": "FastAPI", "javascript": "JavaScript",
           "typescript": "TypeScript", "data cloud": "Data Cloud"}


def display(skill: str) -> str:
    return DISPLAY.get(skill, skill.title())


def canonical(name: str) -> str | None:
    """Map a free-text skill name to its canonical form, or None if unknown."""
    n = name.strip().lower()
    for canon, aliases in ALIASES.items():
        if n == canon or n in aliases:
            return canon
    return None


def _pattern(alias: str) -> re.Pattern:
    # word boundaries that also work for names containing dots or slashes (next.js, pl/sql)
    return re.compile(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])")


_PATTERNS = {canon: [_pattern(a) for a in aliases] for canon, aliases in ALIASES.items()}


def find_in_text(skill: str, text: str) -> str | None:
    """Return a short quote from `text` that proves `skill` is mentioned, or None."""
    low = text.lower()
    for pat in _PATTERNS.get(skill, [_pattern(skill)]):
        m = pat.search(low)
        if m:
            start, end = max(0, m.start() - 60), min(len(text), m.end() + 60)
            snippet = " ".join(text[start:end].split())
            return ("…" if start else "") + snippet + ("…" if end < len(text) else "")
    return None


def skills_in(text: str) -> set[str]:
    """All canonical skills mentioned anywhere in `text`."""
    return {s for s in ALIASES if find_in_text(s, text)}
