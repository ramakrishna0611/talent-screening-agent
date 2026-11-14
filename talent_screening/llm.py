"""Small wrapper around the OpenAI-compatible Groq API: JSON output, fallback model, malformed-output retry."""
import json

from openai import BadRequestError, OpenAI, RateLimitError

from talent_screening.config import FALLBACK_MODEL, GROQ_API_KEY, LLM_BASE_URL, LLM_MODEL

_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is missing. Copy .env.example to .env and add your key.")
        _client = OpenAI(api_key=GROQ_API_KEY, base_url=LLM_BASE_URL, max_retries=3,
                         default_headers={"User-Agent": "talent-screening-agent"})
    return _client


def json_completion(system: str, user: str, max_tokens: int = 2500) -> dict:
    """Ask for a JSON object. Tries the main model, then the fallback model if rate-limited,
    and retries once if the model returns something that is not valid JSON."""
    plan = [LLM_MODEL, FALLBACK_MODEL, LLM_MODEL] if FALLBACK_MODEL else [LLM_MODEL, LLM_MODEL]
    last: Exception | None = None
    for model in plan:
        try:
            resp = client().chat.completions.create(
                model=model, temperature=0, max_tokens=max_tokens, timeout=90,
                response_format={"type": "json_object"}, reasoning_effort="low",
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
            return json.loads(resp.choices[0].message.content or "{}")
        except (RateLimitError, json.JSONDecodeError) as e:
            last = e
        except BadRequestError as e:              # e.g. the model produced invalid JSON for json mode
            if "json" not in str(e).lower():
                raise
            last = e
    raise last
