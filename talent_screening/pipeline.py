"""One entry point used by the dashboard upload, the email poller and the evaluation:
file -> text -> profile -> score -> summary -> saved Application."""
from datetime import date

from sqlalchemy.orm import Session

from talent_screening.extract import extract_profile
from talent_screening.models import Application, AuditLog, Job
from talent_screening.parsing import extract_text, suspicious_phrases
from talent_screening.scoring import score
from talent_screening.summary import summarize


def screen(db: Session, job: Job, data: bytes, filename: str, source: str = "upload",
           sender_email: str | None = None, routing: dict | None = None, actor_id: int | None = None,
           today: date | None = None, with_summary: bool = True) -> Application:
    text = extract_text(data, filename)
    profile = extract_profile(text)
    breakdown = score(profile, text, job, today)

    flags = []
    phrases = suspicious_phrases(text)
    if phrases:
        flags.append({"type": "possible_prompt_injection",
                      "message": "The resume contains text that tries to instruct an AI screener. "
                                 "It had no effect on the score, which is computed by code.",
                      "examples": phrases})
    if breakdown["missing_must_have"]:
        flags.append({"type": "missing_must_have",
                      "message": "Missing required: " + ", ".join(breakdown["missing_must_have"])})

    summary = summarize(job, profile, breakdown) if with_summary else {}
    app = Application(org_id=job.org_id, job_id=job.id, candidate_name=profile.name or "Unknown",
                      candidate_email=sender_email or profile.email, source=source, file_name=filename,
                      resume_text=text, profile=profile.model_dump(), score=breakdown["score"],
                      breakdown=breakdown, summary=summary, flags=flags, routing=routing or {})
    db.add(app)
    db.flush()
    db.add(AuditLog(org_id=job.org_id, actor_id=actor_id, action="screened",
                    details={"application_id": app.id, "job": job.code, "score": app.score, "source": source}))
    db.commit()
    return app
