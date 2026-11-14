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


def login(c, email="priya@kestrel.test", pw="Welcome@123"):
    assert c.post("/api/login", json={"email": email, "password": pw}).status_code == 200


def test_requires_login(client):
    assert client.get("/api/jobs").status_code == 401


def test_wrong_password_rejected(client):
    assert client.post("/api/login", json={"email": "priya@kestrel.test", "password": "nope"}).status_code == 401


def test_jobs_listed(client):
    login(client)
    assert [j["code"] for j in client.get("/api/jobs").json()] == ["KST-101", "KST-102", "KST-103", "KST-104", "KST-105"]
    assert client.get("/api/jobs/XYZ-999/applications").status_code == 404


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


def test_decision_saved_and_validated(client):
    login(client)
    app_id = client.get("/api/jobs/KST-101/applications").json()[0]["id"]
    assert client.post(f"/api/applications/{app_id}/decision", json={"decision": "SHORTLISTED"}).json()["ok"]
    assert client.post(f"/api/applications/{app_id}/decision", json={"decision": "HIRED!!"}).status_code == 400
    client.post("/api/logout")
    assert client.get(f"/api/applications/{app_id}").status_code == 401


def test_frontend_served(client):
    assert "Sieve" in client.get("/").text


def test_shortlist_preview_and_email_logged_without_smtp(client, monkeypatch):
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.setattr(api.mailer, "sending_configured", lambda: False)
    login(client)
    app_id = next(r["id"] for r in client.get("/api/jobs/KST-101/applications").json() if r["name"] == "Aarav Mehta")
    p = client.get(f"/api/applications/{app_id}/email-preview?decision=SHORTLISTED").json()
    assert p["to"] == "aarav.mehta@example.com" and "Hi Aarav" in p["body"] and not p["smtp"]
    r = client.post(f"/api/applications/{app_id}/decision",
                    json={"decision": "SHORTLISTED", "email": {"send": True, "subject": p["subject"], "body": p["body"]}}).json()
    assert r["email"]["status"] == "LOGGED"
    card = client.get(f"/api/applications/{app_id}").json()
    assert card["decision"] == "SHORTLISTED" and card["emails"][0]["kind"] == "SHORTLISTED"
    assert client.get(f"/api/applications/{app_id}/email-preview?decision=SHORTLISTED").json()["already_sent"]


def test_reject_email_sent_through_smtp(client, monkeypatch):
    sent = []
    monkeypatch.setenv("SMTP_USER", "kestrel.careers.demo@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setattr(api.mailer, "deliver", lambda to, subject, body, reply_to=None: sent.append((to, subject)) or "<id>")
    login(client)
    app_id = next(r["id"] for r in client.get("/api/jobs/KST-101/applications").json() if r["name"] == "Arjun Patel")
    r = client.post(f"/api/applications/{app_id}/decision",
                    json={"decision": "REJECTED", "email": {"send": True, "subject": "Your application", "body": "Thanks"}}).json()
    assert r["email"]["status"] == "SENT" and sent == [("arjun.patel@example.com", "Your application")]


def test_no_email_when_unticked_and_none_for_need_info(client):
    login(client)
    app_id = client.get("/api/jobs/KST-101/applications").json()[0]["id"]
    r = client.post(f"/api/applications/{app_id}/decision",
                    json={"decision": "REJECTED", "email": {"send": False, "subject": "x", "body": "y"}}).json()
    assert r["email"] is None
    assert client.get(f"/api/applications/{app_id}/email-preview?decision=NEED_INFO").status_code == 400


def test_rejection_template_has_no_score():
    from talent_screening.mailer import render
    m = render("REJECTED", candidate_name="Arjun Patel", title="Backend Engineer", code="KST-101",
               org="Kestrel Systems", recruiter="Priya Nair")
    assert m["body"].startswith("Hi Arjun,") and "score" not in m["body"].lower()
