"""HTTP tests for the recruiter dashboard (in-memory DB, LLM calls replaced by a stub)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from talent_screening import api, pipeline
from talent_screening.extract import Profile, Role
from talent_screening.models import Base
from talent_screening.seed import seed, seed_demo_applications

RESUME = ("Asha Rao\nasha@example.com\nEXPERIENCE\nBackend Engineer, Quillstack Labs (Jan 2022 - Present)\n"
          "- Built REST APIs in FastAPI with Python and PostgreSQL SQL.\n- Shipped with Docker on AWS.\n")


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    with Session() as s:
        seed(s)
        seed_demo_applications(s)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    # no LLM in tests: fixed extraction and summary
    monkeypatch.setattr(pipeline, "extract_profile", lambda text: Profile(
        name="Asha Rao", email="asha@example.com",
        roles=[Role(title="Backend Engineer", company="Quillstack Labs", start="2022-01", end="present",
                    highlights=["Built REST APIs in FastAPI with Python and PostgreSQL SQL.", "Shipped with Docker on AWS."])]))
    monkeypatch.setattr(pipeline, "summarize", lambda job, profile, breakdown: {"one_line": "Strong backend fit."})
    api.app.dependency_overrides[api.get_db] = override
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()


def login(c, code="KSTL01", pw="kestrel@2026", email="priya@kestrel.test"):
    assert c.post("/api/login/org", json={"code": code, "password": pw}).status_code == 200
    assert c.post("/api/login/user", json={"email": email, "password": "Welcome@123"}).status_code == 200


def test_requires_login(client):
    assert client.get("/api/jobs").status_code == 401


def test_jobs_are_company_scoped(client):
    login(client)
    codes = [j["code"] for j in client.get("/api/jobs").json()]
    assert codes == ["KST-101", "KST-102", "KST-103"]
    assert client.get("/api/jobs/SAF-201/applications").status_code == 404     # other company's job


def test_ranked_candidates_and_scorecard(client):
    login(client)
    rows = client.get("/api/jobs/KST-101/applications").json()
    assert [r["score"] for r in rows] == sorted((r["score"] for r in rows), reverse=True)
    assert rows[0]["name"] == "Aarav Mehta"
    card = client.get(f"/api/applications/{rows[0]['id']}").json()
    assert len(card["breakdown"]["criteria"]) == 4 and card["breakdown"]["criteria"][0]["evidence"]


def test_injection_resume_is_flagged_and_ranked_low(client):
    login(client)
    rows = client.get("/api/jobs/KST-101/applications").json()
    inj = next(r for r in rows if r["name"] == "Sameer Khan")
    assert "possible_prompt_injection" in inj["flags"] and inj["score"] < 30


def test_upload_scores_with_pipeline(client):
    login(client)
    r = client.post("/api/jobs/KST-101/upload", files={"files": ("asha.txt", RESUME.encode(), "text/plain")}).json()
    assert r[0]["name"] == "Asha Rao" and r[0]["score"] >= 80
    bad = client.post("/api/jobs/KST-101/upload", files={"files": ("x.exe", b"x" * 300, "application/octet-stream")}).json()
    assert "Unsupported" in bad[0]["error"]


def test_decision_and_isolation(client):
    login(client)
    app_id = client.get("/api/jobs/KST-101/applications").json()[0]["id"]
    assert client.post(f"/api/applications/{app_id}/decision", json={"decision": "SHORTLISTED"}).json()["ok"]
    assert client.post(f"/api/applications/{app_id}/decision", json={"decision": "HIRED!!"}).status_code == 400
    client.post("/api/logout")
    login(client, "SAFR02", "saffron@2026", "rahul@saffron.test")
    assert client.get(f"/api/applications/{app_id}").status_code == 404
    assert client.post(f"/api/applications/{app_id}/decision", json={"decision": "REJECTED"}).status_code == 404


def test_frontend_served(client):
    assert "Sieve" in client.get("/").text
