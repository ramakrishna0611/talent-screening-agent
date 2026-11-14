"""Gmail API over HTTPS with OAuth (no mailbox password stored anywhere).

One-time setup creates token.json (see scripts/gmail_auth.py). On a server, put the contents of
token.json in the GMAIL_TOKEN_JSON environment variable instead.
Plain REST calls through google-auth's AuthorizedSession keep dependencies small and work behind
networks that intercept SMTP/IMAP but allow HTTPS.
"""
import base64
import json
import os
from email.message import EmailMessage
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials

from talent_screening.config import ROOT

SCOPES = ["https://www.googleapis.com/auth/gmail.send",       # send shortlist / rejection emails
          "https://www.googleapis.com/auth/gmail.modify"]     # read new applications and label them as processed
TOKEN_FILE = ROOT / "token.json"
API = "https://gmail.googleapis.com/gmail/v1/users/me"


def _credentials() -> Credentials | None:
    raw = os.getenv("GMAIL_TOKEN_JSON")
    if raw:
        info, from_file = json.loads(raw), False
    elif TOKEN_FILE.exists():
        info, from_file = json.loads(TOKEN_FILE.read_text(encoding="utf-8")), True
    else:
        return None
    creds = Credentials.from_authorized_user_info(info, SCOPES)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        if from_file:
            TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return creds


def configured() -> bool:
    return bool(os.getenv("GMAIL_TOKEN_JSON") or Path(TOKEN_FILE).exists())


def session() -> AuthorizedSession:
    creds = _credentials()
    if creds is None:
        raise RuntimeError("Gmail is not connected. Run: python scripts/gmail_auth.py")
    return AuthorizedSession(creds)


def mailbox_address() -> str:
    r = session().get(f"{API}/profile", timeout=30)
    r.raise_for_status()
    return r.json()["emailAddress"]


def send(to: str, subject: str, body: str, reply_to: str | None = None) -> str:
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = " ".join(subject.splitlines()).strip()[:200]     # no header injection through the subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    r = session().post(f"{API}/messages/send", json={"raw": raw}, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"Gmail API {r.status_code}: {r.text[:200]}")
    return r.json()["id"]
