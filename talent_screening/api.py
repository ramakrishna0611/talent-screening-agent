"""FastAPI backend for the recruiter dashboard.

Run:  uvicorn talent_screening.api:app      then open http://127.0.0.1:8000
"""
import os
import secrets
import time
from pathlib import Path

import bcrypt
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import RateLimitError
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from talent_screening import gmail, intake, mailer
from talent_screening.models import (DECISIONS, Application, AuditLog, EmailLog, Job, Organization, OutboundEmail, Recruiter,
                                     make_session_factory)
from talent_screening.parsing import UnsupportedFile
from talent_screening.pipeline import screen
from talent_screening.skills import display

WEB = Path(__file__).parent / "web"
SessionLocal = make_session_factory()
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
UPLOADS_PER_HOUR = int(os.getenv("UPLOADS_PER_HOUR", "10"))
UPLOAD_LOG: dict[str, list[float]] = {}

if os.getenv("AUTO_SEED", "1") == "1":                    # hosted demo: create demo data on an empty database
    with SessionLocal() as _db:
        if _db.query(Organization).count() == 0:
            from talent_screening.seed import seed, seed_demo_applications
            seed(_db)
            seed_demo_applications(_db)

INTAKE_POLL_SECONDS = int(os.getenv("INTAKE_POLL_SECONDS", "0"))      # e.g. 60: check the careers inbox every minute


def _poll_inbox_forever() -> None:
    """Background intake: new applications are processed automatically; HR is notified in the dashboard."""
    import time
    while True:
        time.sleep(INTAKE_POLL_SECONDS)
        if not gmail.configured():
            continue
        try:
            with SessionLocal() as db:
                result = intake.process_inbox(db)
            if result["checked"]:
                print("auto-intake:", result, flush=True)
        except Exception as e:                    # never let the poller die; next round retries
            print(f"auto-intake error: {type(e).__name__}: {e}", flush=True)


app = FastAPI(title="Sieve — resume screening")


@app.on_event("startup")
def _start_poller() -> None:
    if INTAKE_POLL_SECONDS > 0:
        import threading
        threading.Thread(target=_poll_inbox_forever, daemon=True, name="inbox-poller").start()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY") or secrets.token_hex(32),
                   same_site="lax", https_only=os.getenv("HTTPS_ONLY", "0") == "1", max_age=8 * 3600)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current(request: Request, db: Session = Depends(get_db)) -> Recruiter:
    r = db.get(Recruiter, request.session.get("recruiter_id") or -1)
    if r is None:
        raise HTTPException(401, "Please log in.")
    return r


def own_job(db: Session, user: Recruiter, code: str) -> Job:
    job = db.scalar(select(Job).where(Job.code == code.upper(), Job.org_id == user.org_id))
    if job is None:                                   # other companies' jobs look exactly like missing ones
        raise HTTPException(404, "Job not found.")
    return job


def own_application(db: Session, user: Recruiter, app_id: int) -> Application:
    a = db.get(Application, app_id)
    if a is None or a.org_id != user.org_id:
        raise HTTPException(404, "Application not found.")
    return a


class UserLogin(BaseModel):
    email: str
    password: str


class EmailIn(BaseModel):
    send: bool = True
    subject: str = Field(max_length=200)
    body: str = Field(max_length=5000)


class DecisionIn(BaseModel):
    decision: str
    note: str = ""
    email: EmailIn | None = None          # shortlist / reject email reviewed by the recruiter


def _check(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())


# ---------- auth ----------
@app.post("/api/login")
def login(body: UserLogin, request: Request, db: Session = Depends(get_db)):
    """Single HR sign-in (one company). Records still carry org_id, so more companies can be added later."""
    r = db.scalar(select(Recruiter).where(Recruiter.email == body.email.strip().lower()))
    if r is None or not _check(body.password, r.password_hash):
        raise HTTPException(401, "Invalid email or password.")
    request.session.clear()
    request.session["recruiter_id"] = r.id
    request.session["sid"] = secrets.token_hex(8)
    return {"name": r.name}


@app.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/me")
def me(user: Recruiter = Depends(current), db: Session = Depends(get_db)):
    org = db.get(Organization, user.org_id)
    return {"name": user.name, "email": user.email, "org": org.name, "org_code": org.code,
            "decisions": list(DECISIONS)}


# ---------- jobs and applications ----------
@app.get("/api/jobs")
def jobs(user: Recruiter = Depends(current), db: Session = Depends(get_db)):
    out = []
    for j in db.scalars(select(Job).where(Job.org_id == user.org_id).order_by(Job.code)):
        rows = db.execute(select(Application.decision, func.count(), func.max(Application.score))
                          .where(Application.job_id == j.id).group_by(Application.decision)).all()
        counts = {d: c for d, c, _ in rows}
        out.append({"code": j.code, "title": j.title, "min_years": j.min_years, "status": j.status,
                    "must_have": [[display(x) for x in g] for g in j.must_have],
                    "nice_to_have": [display(x) for x in j.nice_to_have], "description": j.description,
                    "total": sum(counts.values()), "new": counts.get("NEW", 0),
                    "shortlisted": counts.get("SHORTLISTED", 0),
                    "top_score": max((m for *_, m in rows if m is not None), default=None)})
    return out


def _row(a: Application) -> dict:
    return {"id": a.id, "name": a.candidate_name, "score": a.score, "decision": a.decision, "source": a.source,
            "experience_years": a.breakdown.get("experience_years"),
            "missing": a.breakdown.get("missing_must_have", []),
            "flags": [f["type"] for f in a.flags], "one_line": (a.summary or {}).get("one_line", ""),
            "criteria": [{"name": c["name"], "points": c["points"], "max": c["max_points"]}
                         for c in a.breakdown.get("criteria", [])],
            "received": a.created_at.strftime("%d %b %Y")}


@app.get("/api/jobs/{code}/applications")
def applications(code: str, user: Recruiter = Depends(current), db: Session = Depends(get_db)):
    job = own_job(db, user, code)
    apps = db.scalars(select(Application).where(Application.job_id == job.id)
                      .order_by(Application.score.desc(), Application.created_at))
    return [_row(a) for a in apps]


@app.get("/api/applications/{app_id}")
def application(app_id: int, user: Recruiter = Depends(current), db: Session = Depends(get_db)):
    a = own_application(db, user, app_id)
    return {**_row(a), "job": {"code": a.job.code, "title": a.job.title}, "email": a.candidate_email,
            "file_name": a.file_name, "breakdown": a.breakdown, "summary": a.summary, "flag_details": a.flags,
            "profile": a.profile, "resume_text": a.resume_text, "routing": a.routing,
            "emails": _emails(db, a.id)}


def _emails(db: Session, app_id: int) -> list[dict]:
    return [{"id": e.id, "kind": e.kind, "to": e.to_address, "subject": e.subject, "status": e.status,
             "error": e.error, "at": e.created_at.strftime("%d %b %Y, %H:%M")}
            for e in db.scalars(select(OutboundEmail).where(OutboundEmail.application_id == app_id)
                                .order_by(OutboundEmail.id.desc()))]


@app.get("/api/applications/{app_id}/email-preview")
def email_preview(app_id: int, decision: str, user: Recruiter = Depends(current), db: Session = Depends(get_db)):
    if decision not in mailer.EMAIL_KINDS:
        raise HTTPException(400, "Emails exist only for shortlist and reject.")
    a = own_application(db, user, app_id)
    org = db.get(Organization, user.org_id)
    draft = mailer.render(decision, candidate_name=a.candidate_name, title=a.job.title, code=a.job.code,
                          org=org.name, recruiter=user.name)
    already = [e for e in _emails(db, a.id) if e["kind"] == decision and e["status"] in ("SENT", "LOGGED")]
    return {**draft, "to": a.candidate_email, "valid_to": bool(a.candidate_email and mailer.EMAIL_RE.match(a.candidate_email)),
            "smtp": mailer.sending_configured(), "already_sent": bool(already)}


@app.post("/api/applications/{app_id}/decision")
def decide(app_id: int, body: DecisionIn, user: Recruiter = Depends(current), db: Session = Depends(get_db)):
    if body.decision not in DECISIONS:
        raise HTTPException(400, f"Decision must be one of {', '.join(DECISIONS)}.")
    a = own_application(db, user, app_id)
    old = a.decision
    a.decision, a.decided_by = body.decision, user.id
    db.add(AuditLog(org_id=user.org_id, actor_id=user.id, action="decision",
                    details={"application_id": a.id, "from": old, "to": body.decision, "note": body.note[:300]}))
    db.commit()

    email_status = None
    if body.email and body.email.send and body.decision in mailer.EMAIL_KINDS:
        to = a.candidate_email or ""
        if not mailer.EMAIL_RE.match(to):
            email_status = {"status": "FAILED", "error": "The candidate has no valid email address."}
        else:
            record = OutboundEmail(org_id=user.org_id, application_id=a.id, kind=body.decision, to_address=to,
                                   subject=body.email.subject.strip()[:200], body=body.email.body.strip(),
                                   status="LOGGED", sent_by=user.id)
            if mailer.sending_configured():
                try:
                    mailer.deliver(to, record.subject, record.body, reply_to=user.email)
                    record.status = "SENT"
                except Exception as e:            # SMTP problems are reported, the decision itself stays saved
                    record.status, record.error = "FAILED", f"{type(e).__name__}: {e}"[:300]
            db.add(record)
            db.add(AuditLog(org_id=user.org_id, actor_id=user.id, action="email_" + record.status.lower(),
                            details={"application_id": a.id, "kind": record.kind, "to": to}))
            db.commit()
            email_status = {"status": record.status, "error": record.error}
    return {"ok": True, "decision": a.decision, "email": email_status}


@app.post("/api/jobs/{code}/upload")
async def upload(code: str, request: Request, files: list[UploadFile] = File(...), user: Recruiter = Depends(current),
                 db: Session = Depends(get_db)):
    job = own_job(db, user, code)
    # Public demo protection: each signed-in session may screen UPLOADS_PER_HOUR resumes per hour
    now = time.time()
    sid = request.session.get("sid") or str(user.id)
    recent = [t for t in UPLOAD_LOG.get(sid, []) if now - t < 3600]
    if len(recent) + len(files) > UPLOADS_PER_HOUR:
        raise HTTPException(429, f"Demo limit: {UPLOADS_PER_HOUR} resumes per hour. Try again later.")
    UPLOAD_LOG[sid] = recent + [now] * len(files)
    results = []
    for f in files[:10]:
        data = await f.read()
        if len(data) > MAX_UPLOAD_BYTES:
            results.append({"file": f.filename, "error": "File is larger than 5 MB."})
            continue
        try:
            a = screen(db, job, data, f.filename or "resume", source="upload", actor_id=user.id)
            results.append({"file": f.filename, "id": a.id, "name": a.candidate_name, "score": a.score})
        except UnsupportedFile as e:
            results.append({"file": f.filename, "error": str(e)})
        except RateLimitError:
            db.rollback()
            results.append({"file": f.filename, "error": "AI quota reached (free tier). Try again later."})
    return results


# ---------- careers inbox ----------
class RouteIn(BaseModel):
    job_code: str


@app.get("/api/inbox")
def inbox(user: Recruiter = Depends(current), db: Session = Depends(get_db)):
    rows = db.scalars(select(EmailLog).where(EmailLog.org_id == user.org_id)
                      .order_by(EmailLog.received_at.desc()).limit(50))
    return {"connected": gmail.configured(),
            "mailbox": os.getenv("INTAKE_MAILBOX_LABEL", ""),
            "items": [{"id": e.id, "from": e.sender, "subject": e.subject, "status": e.status, "outcome": e.outcome,
                       "routing": e.routing, "file": e.file_name, "applications": e.application_ids,
                       "at": e.received_at.strftime("%d %b, %H:%M")} for e in rows]}


class ProcessIn(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=50)


@app.get("/api/inbox/new")
def new_emails(user: Recruiter = Depends(current), db: Session = Depends(get_db)):
    """Step 1: show HR what has arrived. Reads only: nothing is scored, labelled or saved."""
    if not gmail.configured():
        raise HTTPException(400, "Gmail is not connected. Run scripts/gmail_auth.py first.")
    return intake.peek_inbox(db)


@app.post("/api/inbox/check")
def check_inbox(body: ProcessIn, user: Recruiter = Depends(current), db: Session = Depends(get_db)):
    """Step 2: process only the emails HR acknowledged."""
    if not gmail.configured():
        raise HTTPException(400, "Gmail is not connected. Run scripts/gmail_auth.py first.")
    try:
        return intake.process_inbox(db, only_ids=body.ids or None)      # no ids: everything new
    except RateLimitError:
        raise HTTPException(429, "AI quota reached (free tier). Emails stay unread-for-us and will be retried.")


@app.get("/api/inbox/unseen")
def unseen(user: Recruiter = Depends(current), db: Session = Depends(get_db)):
    """Lightweight poll for the dashboard: emails that arrived since HR last opened the inbox."""
    rows = list(db.scalars(select(EmailLog).where(EmailLog.org_id == user.org_id, EmailLog.seen_by_hr.is_(False))))
    count = lambda st: sum(1 for r in rows if r.status == st)
    return {"unseen": len(rows), "screened": count("PROCESSED"), "needs_routing": count("NEEDS_ROUTING"),
            "skipped": count("SKIPPED"), "ids": [r.id for r in rows]}


@app.post("/api/inbox/seen")
def mark_seen(user: Recruiter = Depends(current), db: Session = Depends(get_db)):
    """HR acknowledges the new arrivals (called when the inbox is opened)."""
    rows = list(db.scalars(select(EmailLog).where(EmailLog.org_id == user.org_id, EmailLog.seen_by_hr.is_(False))))
    for r in rows:
        r.seen_by_hr = True
    if rows:
        db.add(AuditLog(org_id=user.org_id, actor_id=user.id, action="inbox_acknowledged",
                        details={"email_log_ids": [r.id for r in rows]}))
    db.commit()
    return {"acknowledged": len(rows)}


@app.post("/api/inbox/{log_id}/route")
def route_email(log_id: int, body: RouteIn, user: Recruiter = Depends(current), db: Session = Depends(get_db)):
    log = db.get(EmailLog, log_id)
    if log is None or log.org_id != user.org_id or log.status != "NEEDS_ROUTING" or not log.resume_text:
        raise HTTPException(404, "Nothing to route for this email.")
    job = own_job(db, user, body.job_code)
    try:
        app_id = intake.route_manually(db, log, job, actor_id=user.id)
    except RateLimitError:
        raise HTTPException(429, "AI quota reached (free tier). Try again later.")
    return {"ok": True, "application_id": app_id}


# ---------- frontend ----------
app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")
