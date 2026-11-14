"""Settings shared by every module."""
import os
from pathlib import Path

import truststore
from dotenv import load_dotenv

truststore.inject_into_ssl()          # OS certificate store: HTTPS works behind inspecting proxies
load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB_URL = os.getenv("DB_URL", f"sqlite:///{ROOT / 'talent.db'}")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "openai/gpt-oss-20b")

# Default rubric weights (out of 100); HR can override per job
DEFAULT_WEIGHTS = {"must_have": 40, "experience": 20, "nice_to_have": 15, "applied": 25}
INTERNSHIP_WEIGHT = 0.5      # an internship month counts as half a month of experience
