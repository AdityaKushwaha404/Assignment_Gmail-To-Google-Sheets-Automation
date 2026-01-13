"""Central configuration and shared OAuth handling for the Gmail → Sheets app.

This module centralizes configuration constants and the OAuth login/refresh
logic so all modules can obtain authenticated credentials without duplicating
code.

Security and persistence notes
- Do not commit ``credentials/credentials.json`` or ``credentials/token.json``.
- A locally persisted ``token.json`` enables smooth re-runs and token
    refresh without repeated browser prompts. Consider file-system permissions
    on ``credentials/`` in shared environments.
"""
from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


# App constants
APP_NAME = "gmail-to-sheets"

# OAuth scopes
# - gmail.modify: required to mark messages as READ after processing
# - spreadsheets: read/write access to manage state and append rows
SCOPES: Sequence[str] = (
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/spreadsheets",
)


# Base paths
BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_DIR = BASE_DIR / "credentials"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials.json"
TOKEN_FILE = CREDENTIALS_DIR / "token.json"


# Sheets config
# IMPORTANT: You can override this at runtime with env var SPREADSHEET_ID.
# Keeping the env override allows easy switching across spreadsheets/environments.
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1QowCnfwb7XugQsJitoPiD0gKhNkXj3Ae5g_UBwMxaaE")

# Sheet/tab names
SHEET_EMAILS = "Emails"       # User-facing data (From, Subject, Date, Content)
SHEET_PROCESSED = "Processed"  # Internal state: Gmail messageIds for dedupe


# Optional subject filtering (bonus). Provide comma-separated keywords via env vars.
SUBJECT_INCLUDE = tuple(
    s.strip() for s in os.environ.get("SUBJECT_INCLUDE", "").split(",") if s.strip()
)
SUBJECT_EXCLUDE = tuple(
    s.strip() for s in os.environ.get("SUBJECT_EXCLUDE", "").split(",") if s.strip()
)

# Default subject include keywords (used when no env var provided). These
# focus the sync on likely billing-related messages as a sensible default for
# the assignment; they remain configurable via the SUBJECT_INCLUDE env var.
if not SUBJECT_INCLUDE:
    SUBJECT_INCLUDE = ("invoice", "receipt", "payment", "bill")


# Basic logging setup; main will configure handlers/level.
DEFAULT_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()


@dataclass
class OAuthFiles:
    credentials_file: Path = CREDENTIALS_FILE
    token_file: Path = TOKEN_FILE


def get_credentials(scopes: Sequence[str] = SCOPES, files: OAuthFiles | None = None) -> Credentials:
    """
    Load or obtain OAuth user credentials for the provided scopes.

    Why this approach:
    - Uses OAuth 2.0 InstalledAppFlow (no service accounts) to align with
      Gmail access rules for user mailboxes.
    - Persists token.json to enable seamless re-runs and idempotent behavior.
    """
    files = files or OAuthFiles()

    creds: Credentials | None = None
    if files.token_file.exists():
        # Load existing user credentials (includes refresh token if present).
        creds = Credentials.from_authorized_user_file(str(files.token_file), scopes)
        logging.getLogger(APP_NAME).debug("Loaded OAuth credentials from %s", files.token_file)

    # Refresh existing credentials or run the interactive flow when necessary.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logging.getLogger(APP_NAME).debug("Refreshing OAuth token...")
            creds.refresh(Request())
            logging.getLogger(APP_NAME).info("OAuth token refreshed")
        else:
            if not files.credentials_file.exists():
                raise FileNotFoundError(
                    f"Missing OAuth client secrets file at {files.credentials_file}. "
                    "Download it from Google Cloud Console and save as 'credentials.json'."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(files.credentials_file), scopes)
            # Runs a local server flow that opens a browser for user consent.
            creds = flow.run_local_server(port=0)
            logging.getLogger(APP_NAME).info("Obtained new OAuth credentials via user consent")

        # Persist the refreshed/new token for subsequent runs. This is useful
        # for unattended re-runs during evaluation; consider locking the
        # credentials directory if multiple users share the machine.
        files.token_file.parent.mkdir(parents=True, exist_ok=True)
        with open(files.token_file, "w") as token:
            token.write(creds.to_json())

    return creds
