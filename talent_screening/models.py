"""Database tables (SQLAlchemy 2.0)."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from talent_screening.config import DB_URL

DECISIONS = ("NEW", "SHORTLISTED", "NEED_INFO", "REJECTED")


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(20), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))


class Recruiter(Base):
    __tablename__ = "recruiters"
    __table_args__ = (UniqueConstraint("org_id", "email"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(100))


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    code: Mapped[str] = mapped_column(String(20), unique=True)          # e.g. KST-101, quoted in emails
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    must_have: Mapped[list] = mapped_column(JSON)       # list of any-of groups: [["python"], ["power bi", "tableau"]]
    nice_to_have: Mapped[list] = mapped_column(JSON)    # list of skills
    min_years: Mapped[float] = mapped_column(Float, default=0)
    weights: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(10), default="OPEN")


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    candidate_name: Mapped[str] = mapped_column(String(120))
    candidate_email: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(20), default="upload")      # upload or email
    file_name: Mapped[str] = mapped_column(String(200))
    resume_text: Mapped[str] = mapped_column(Text)
    profile: Mapped[dict] = mapped_column(JSON)          # structured data extracted from the resume
    score: Mapped[int] = mapped_column(Integer)
    breakdown: Mapped[dict] = mapped_column(JSON)        # per-criterion points with evidence
    summary: Mapped[dict] = mapped_column(JSON)          # strengths, gaps, interview questions
    flags: Mapped[list] = mapped_column(JSON, default=list)
    routing: Mapped[dict] = mapped_column(JSON, default=dict)            # how the job was chosen (email)
    decision: Mapped[str] = mapped_column(String(12), default="NEW")
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("recruiters.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    job: Mapped[Job] = relationship()


class EmailLog(Base):
    __tablename__ = "email_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[str] = mapped_column(String(300), unique=True)   # never process the same email twice
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    sender: Mapped[str] = mapped_column(String(300))
    subject: Mapped[str] = mapped_column(String(500))
    outcome: Mapped[str] = mapped_column(String(300))
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("recruiters.id"))
    action: Mapped[str] = mapped_column(String(50))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


def make_session_factory(url: str = DB_URL):
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
