"""Candidate emails: templates for shortlist and rejection, and sending through SMTP.

Delivery: the Gmail API (OAuth, preferred) if connected, otherwise SMTP if SMTP_USER / SMTP_PASSWORD are set,
otherwise emails are stored in the outbox with status LOGGED so the demo works without a mailbox.
"""
import os
import re
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

TEMPLATES = {
    "SHORTLISTED": {
        "subject": "Your application for {title} at {org}: next steps",
        "body": (
            "Hi {first_name},\n\n"
            "Thank you for applying for the {title} role ({code}) at {org}. We enjoyed reading your application "
            "and would like to invite you to the next stage: a 30-minute conversation with our team.\n\n"
            "Please reply to this email with two or three times that suit you over the next week.\n\n"
            "Best regards,\n{recruiter}\n{org} Talent Team"),
    },
    "REJECTED": {
        "subject": "Your application for {title} at {org}",
        "body": (
            "Hi {first_name},\n\n"
            "Thank you for your interest in the {title} role ({code}) at {org} and for the time you put into "
            "your application.\n\n"
            "After careful review, we have decided not to move forward with your application for this role. "
            "This was not an easy decision, and it is not a judgement of your overall ability.\n\n"
            "We will keep your details on file and may contact you about future openings that match your "
            "experience. We wish you every success in your search.\n\n"
            "Kind regards,\n{recruiter}\n{org} Talent Team"),
    },
}
EMAIL_KINDS = tuple(TEMPLATES)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def render(kind: str, *, candidate_name: str, title: str, code: str, org: str, recruiter: str) -> dict:
    t = TEMPLATES[kind]
    first = (candidate_name or "there").split()[0]
    values = dict(first_name=first, title=title, code=code, org=org, recruiter=recruiter)
    return {"subject": t["subject"].format(**values), "body": t["body"].format(**values)}


def smtp_configured() -> bool:
    return bool(os.getenv("SMTP_USER") and os.getenv("SMTP_PASSWORD"))


def send(to: str, subject: str, body: str, reply_to: str | None = None) -> str:
    """Send one plain-text email and return its Message-ID. Raises on failure."""
    user = os.environ["SMTP_USER"]
    msg = EmailMessage()
    msg["From"] = os.getenv("MAIL_FROM", user)
    msg["To"] = to
    # Strip newlines so a subject can never inject extra headers
    msg["Subject"] = " ".join(subject.splitlines()).strip()[:200]
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Message-ID"] = make_msgid(domain=user.split("@")[-1])
    msg.set_content(body)
    with smtplib.SMTP(os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", "587")), timeout=30) as s:
        s.starttls()
        s.login(user, os.environ["SMTP_PASSWORD"])
        s.send_message(msg)
    return msg["Message-ID"]


def sending_configured() -> bool:
    from talent_screening import gmail
    return gmail.configured() or smtp_configured()


def deliver(to: str, subject: str, body: str, reply_to: str | None = None) -> str:
    """Send through the Gmail API if connected, else SMTP. Returns the provider's message id."""
    from talent_screening import gmail
    if gmail.configured():
        return gmail.send(to, subject, body, reply_to=reply_to)
    return send(to, subject, body, reply_to=reply_to)
