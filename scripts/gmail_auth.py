"""One-time Gmail connection: opens Google's sign-in page and saves token.json (git-ignored).

Before running: put the OAuth client file from Google Cloud Console in the project folder as credentials.json.
Run:  python scripts/gmail_auth.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import truststore

truststore.inject_into_ssl()

from google_auth_oauthlib.flow import InstalledAppFlow

from talent_screening import gmail


def main() -> None:
    secrets = ROOT / "credentials.json"
    if not secrets.exists():
        sys.exit("credentials.json not found in the project folder. Download it from Google Cloud Console first.")
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets), gmail.SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent",
                                  authorization_prompt_message="Opening Google sign-in in your browser...",
                                  success_message="Connected. You can close this tab and return to the terminal.")
    gmail.TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    print("Saved token.json. Connected mailbox:", gmail.mailbox_address())


if __name__ == "__main__":
    main()
