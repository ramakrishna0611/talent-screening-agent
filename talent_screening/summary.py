"""LLM-written scorecard summary for HR. It explains the code-computed score; it never changes it."""
import json

from talent_screening.llm import json_completion

SYSTEM = """You write a short screening note for a recruiter. You receive a job, the candidate's
extracted work history and projects, and a score breakdown that was computed by code.
Rules:
- Use only the information provided. Do not invent skills, employers, numbers or dates.
- Do not mention or infer the candidate's gender, age, ethnicity, religion, nationality or location.
- Do not change or argue with the score; explain it.
- Be specific and neutral. Each strength and gap should point to evidence.
- Gaps must be measured against what THIS job asks for (its description, must-have and nice-to-have skills,
  minimum years). Do not list technologies or practices the job does not mention.
Return JSON: {"one_line": string (max 25 words),
              "strengths": [string] (2-4 items), "gaps": [string] (1-4 items),
              "interview_questions": [string] (3 items that probe the gaps or verify claims)}"""


def summarize(job, profile, breakdown: dict) -> dict:
    payload = {
        "job": {"title": job.title, "description": job.description[:1500], "min_years": job.min_years,
                "must_have": [" or ".join(g) for g in (job.must_have or [])], "nice_to_have": job.nice_to_have},
        "candidate": {   # name, email and phone deliberately left out
            "roles": [r.model_dump() for r in profile.roles],
            "projects": [p.model_dump() for p in profile.projects],
            "education": [e.model_dump() for e in profile.education],
            "certifications": profile.certifications,
        },
        "score": breakdown["score"],
        "breakdown": [{k: c[k] for k in ("name", "points", "max_points", "detail")} for c in breakdown["criteria"]],
    }
    out = json_completion(SYSTEM, json.dumps(payload, default=str), max_tokens=1200)
    return {
        "one_line": str(out.get("one_line", ""))[:300],
        "strengths": [str(x) for x in out.get("strengths", [])][:4],
        "gaps": [str(x) for x in out.get("gaps", [])][:4],
        "interview_questions": [str(x) for x in out.get("interview_questions", [])][:3],
    }
