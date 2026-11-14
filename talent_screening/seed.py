"""Demo data: one fictional company (Kestrel Systems), one HR user and five open roles.

Run:  python -m talent_screening.seed
"""
import bcrypt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from talent_screening.config import DB_URL
from talent_screening.models import Base, Job, Organization, Recruiter, make_session_factory

PASSWORD = "Welcome@123"

ORGS = [
    {"name": "Kestrel Systems", "code": "KSTL01", "password": "kestrel@2026",
     "recruiters": [("Priya Nair", "priya@kestrel.test")],
     "jobs": [
         {"code": "KST-101", "title": "Backend Engineer (Python)", "min_years": 2,
          "must_have": [["python"], ["fastapi", "django", "flask"], ["sql"], ["rest apis"]],
          "nice_to_have": ["docker", "aws", "redis"],
          "description": "Build and run the Python APIs behind Kestrel's CRM products. You will design REST "
                         "endpoints with FastAPI, model data in PostgreSQL, write tests, and ship with Docker on AWS. "
                         "2+ years building production backends."},
         {"code": "KST-102", "title": "Salesforce Developer", "min_years": 1,
          "must_have": [["apex"], ["lwc"], ["soql"], ["salesforce flows"]],
          "nice_to_have": ["agentforce", "salesforce integration", "data cloud"],
          "description": "Develop Sales Cloud and Service Cloud features: Apex triggers and classes, Lightning Web "
                         "Components, SOQL, record-triggered flows, and integrations with external systems. "
                         "Agentforce experience is a plus. 1+ year on the platform."},
         {"code": "KST-103", "title": "AI Engineer (LLM Applications)", "min_years": 1,
          "must_have": [["python"], ["llm apis"], ["rag"], ["prompt engineering"]],
          "nice_to_have": ["langchain", "vector databases", "llm evaluation", "fastapi"],
          "description": "Build LLM features for customers: retrieval-augmented generation over company documents, "
                         "tool-using agents, evaluation pipelines and guardrails. Python, LLM APIs, prompt "
                         "engineering and vector search. 1+ year building with LLMs."},
         {"code": "KST-104", "title": "Data Analyst", "min_years": 1,
          "must_have": [["sql"], ["excel"], ["pandas", "python"], ["power bi", "tableau"]],
          "nice_to_have": ["statistics", "python"],
          "description": "Turn product and billing data into decisions: SQL queries, Excel models, Python/pandas "
                         "analysis and Power BI or Tableau dashboards for leadership. 1+ year in analytics."},
         {"code": "KST-105", "title": "Frontend Engineer (React)", "min_years": 2,
          "must_have": [["javascript"], ["react"], ["html"], ["css"]],
          "nice_to_have": ["typescript", "next.js", "frontend testing"],
          "description": "Own Kestrel's customer console: React components, accessible HTML and CSS, TypeScript, "
                         "Next.js and automated UI tests. 2+ years shipping web frontends."},
     ]},
]


def seed(db: Session) -> None:
    pw = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()
    for spec in ORGS:
        org = Organization(name=spec["name"], code=spec["code"],
                           password_hash=bcrypt.hashpw(spec["password"].encode(), bcrypt.gensalt()).decode())
        db.add(org)
        db.flush()
        for name, email in spec["recruiters"]:
            db.add(Recruiter(org_id=org.id, name=name, email=email, password_hash=pw))
        for j in spec["jobs"]:
            db.add(Job(org_id=org.id, **j, weights={}))
    db.commit()


# Which sample candidates applied to which job (fictional)
DEMO_APPLICATIONS = {
    "KST-101": ["aarav_mehta", "arjun_patel", "rohit_sharma", "keyword_stuffer", "injection_attempt"],
    "KST-102": ["neha_kulkarni", "kunal_desai"],
    "KST-103": ["fatima_sheikh", "meghana_rao", "keyword_stuffer"],
    "KST-104": ["vivek_iyer", "rohit_sharma"],
    "KST-105": ["sanya_gupta"],
}


def seed_demo_applications(db: Session, today=None) -> int:
    """Create applications from pre-extracted profiles (data/demo_profiles.json), so the demo needs no LLM calls.
    Scores are computed by the normal scoring code; summaries come from data/demo_summaries.json if present."""
    import json
    from talent_screening.config import DATA
    from talent_screening.extract import Profile
    from talent_screening.models import Application
    from talent_screening.parsing import suspicious_phrases
    from talent_screening.scoring import score

    profiles = json.loads((DATA / "demo_profiles.json").read_text(encoding="utf-8"))
    sums_path = DATA / "demo_summaries.json"
    summaries = json.loads(sums_path.read_text(encoding="utf-8")) if sums_path.exists() else {}
    n = 0
    for code, names in DEMO_APPLICATIONS.items():
        job = db.query(Job).filter_by(code=code).one()
        for name in names:
            text = (DATA / "resumes" / f"{name}.txt").read_text(encoding="utf-8")
            profile = Profile.model_validate(profiles[name])
            breakdown = score(profile, text, job, today)
            flags = []
            if phrases := suspicious_phrases(text):
                flags.append({"type": "possible_prompt_injection", "examples": phrases,
                              "message": "The resume contains text that tries to instruct an AI screener. "
                                         "It had no effect on the score, which is computed by code."})
            if breakdown["missing_must_have"]:
                flags.append({"type": "missing_must_have",
                              "message": "Missing required: " + ", ".join(breakdown["missing_must_have"])})
            db.add(Application(org_id=job.org_id, job_id=job.id, candidate_name=profile.name,
                               candidate_email=profile.email, source="demo", file_name=f"{name}.txt",
                               resume_text=text, profile=profile.model_dump(), score=breakdown["score"],
                               breakdown=breakdown, summary=summaries.get(f"{code}:{name}", {}), flags=flags))
            n += 1
    db.commit()
    return n


def main() -> None:
    engine = create_engine(DB_URL)
    Base.metadata.drop_all(engine)
    with make_session_factory(DB_URL)() as db:
        seed(db)
        n = seed_demo_applications(db)
    print(f"Seeded Kestrel Systems with 5 open roles and {n} demo applications. HR login: priya@kestrel.test / "
          + PASSWORD)


if __name__ == "__main__":
    main()
