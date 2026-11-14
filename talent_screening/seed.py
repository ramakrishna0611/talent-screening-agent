"""Demo data: the same two fictional companies as the leave tracker, with open roles and recruiters.

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
     ]},
    {"name": "Saffron Cloudworks", "code": "SAFR02", "password": "saffron@2026",
     "recruiters": [("Rahul Menon", "rahul@saffron.test")],
     "jobs": [
         {"code": "SAF-201", "title": "Data Analyst", "min_years": 1,
          "must_have": [["sql"], ["excel"], ["pandas", "python"], ["power bi", "tableau"]],
          "nice_to_have": ["statistics", "python"],
          "description": "Turn product and billing data into decisions: SQL queries, Excel models, Python/pandas "
                         "analysis and Power BI or Tableau dashboards for leadership. 1+ year in analytics."},
         {"code": "SAF-202", "title": "Frontend Engineer (React)", "min_years": 2,
          "must_have": [["javascript"], ["react"], ["html"], ["css"]],
          "nice_to_have": ["typescript", "next.js", "frontend testing"],
          "description": "Own Saffron's customer console: React components, accessible HTML and CSS, TypeScript, "
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


def main() -> None:
    engine = create_engine(DB_URL)
    Base.metadata.drop_all(engine)
    with make_session_factory(DB_URL)() as db:
        seed(db)
    print("Seeded 2 companies, 5 open jobs. Recruiters: priya@kestrel.test, rahul@saffron.test / " + PASSWORD)


if __name__ == "__main__":
    main()
