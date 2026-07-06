# ruff: noqa
"""One-time Gmail authorization for MedNav.

Run ONCE, from the repo root, after downloading your OAuth client file from
Google Cloud (APIs & Services > Credentials > "Create credentials" > OAuth client
ID > Application type: "Desktop app" > Download JSON):

    GMAIL_CREDENTIALS_PATH=/absolute/path/to/credentials.json python authorize_gmail.py

It opens a browser for consent (sign in as the PATIENT account, e.g. yyguyduy@gmail.com,
grant read + send), then writes token.json next to the repo (path from GMAIL_TOKEN_PATH,
default ./token.json). The agent then loads that cached token and refreshes it silently.

NEVER commit credentials.json or token.json — both are gitignored.
"""
import os

from google_auth_oauthlib.flow import InstalledAppFlow

# Must match GMAIL_SCOPES in care_navigator/agent.py
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


def main() -> None:
    cred_path = os.environ.get("GMAIL_CREDENTIALS_PATH", "credentials.json")
    token_path = os.environ.get("GMAIL_TOKEN_PATH", "token.json")
    if not os.path.exists(cred_path):
        raise SystemExit(
            f"Missing OAuth client file at '{cred_path}'. Download it from Google Cloud "
            "(APIs & Services > Credentials > OAuth client ID, type 'Desktop app'), then set "
            "GMAIL_CREDENTIALS_PATH to its path and re-run."
        )
    flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)
    creds = flow.run_local_server(port=0)  # opens the browser consent screen
    with open(token_path, "w", encoding="utf-8") as fh:
        fh.write(creds.to_json())
    print(f"Authorized. Wrote {token_path}. You can now run the agent (adk web).")


if __name__ == "__main__":
    main()
