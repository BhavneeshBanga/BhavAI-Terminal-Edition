"""
bhavai/agents/calendar/auth.py
────────────────────────────────
Google OAuth 2.0 helper for the Calendar agent.

How credentials work
--------------------
1. Download credentials.json from Google Cloud Console:
     console.cloud.google.com → APIs & Services → Credentials
     → Create OAuth 2.0 Client ID → Desktop App → Download JSON
2. Place credentials.json in the BhavAI project root  (same folder as .env).
3. On the FIRST call to get_calendar_service(), a browser window opens —
   log in with your Google account and grant Calendar access.
4. token.json is auto-created next to credentials.json and reused on every
   subsequent call (no browser needed again unless the token expires).

Environment variables (in .env)
--------------------------------
  GOOGLE_CREDENTIALS_PATH=credentials.json   (relative to project root, or absolute)
  USER_TIMEZONE=Asia/Kolkata
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (3 levels up: calendar/ → agents/ → bhavai/ → root)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=True)

# ── Paths ────────────────────────────────────────────────────────────────────

_CREDS_ENV = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")

# If the path in .env is relative, resolve it from project root
_CREDENTIALS_FILE: Path = (
    Path(_CREDS_ENV)
    if Path(_CREDS_ENV).is_absolute()
    else _PROJECT_ROOT / _CREDS_ENV
)
_TOKEN_FILE: Path = _CREDENTIALS_FILE.parent / "token.json"

# Google Calendar API scopes required
_SCOPES = [
    "https://www.googleapis.com/auth/calendar",          # full read/write
    "https://www.googleapis.com/auth/calendar.events",   # events only
]


# ── Public API ────────────────────────────────────────────────────────────────

class CalendarAuthError(Exception):
    """Raised when Google auth fails and user action is needed."""


def get_calendar_service():
    """
    Returns an authenticated Google Calendar API service object (v3).

    Workflow:
      - If token.json exists and is valid → use it directly.
      - If token.json is expired → refresh automatically (no browser).
      - If no token.json → open browser for first-time OAuth consent.
      - If credentials.json is missing → raise CalendarAuthError with
        clear instructions.

    Raises
    ------
    CalendarAuthError : credentials.json not found, or auth flow failed.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise CalendarAuthError(
            "Google client libraries not installed.\n"
            "Run: pip install google-auth google-auth-oauthlib "
            "google-auth-httplib2 google-api-python-client"
        ) from exc

    if not _CREDENTIALS_FILE.exists():
        raise CalendarAuthError(
            f"credentials.json not found at: {_CREDENTIALS_FILE}\n\n"
            "Steps to fix:\n"
            "  1. Go to https://console.cloud.google.com\n"
            "  2. APIs & Services → Enable 'Google Calendar API'\n"
            "  3. Credentials → Create → OAuth 2.0 Client ID → Desktop App\n"
            "  4. Download JSON → rename to 'credentials.json'\n"
            "  5. Place it in the project root: " + str(_PROJECT_ROOT) + "\n"
            "  6. Try again — browser will open for first-time login."
        )

    creds: Credentials | None = None

    # Load existing token
    if _TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), _SCOPES)
        except Exception:
            creds = None  # corrupted token — will re-auth

    # Refresh or run first-time consent flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None  # refresh failed — re-auth

        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(_CREDENTIALS_FILE), _SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save token for next run
        _TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    return build("calendar", "v3", credentials=creds)


def clear_token() -> str:
    """Delete token.json so next call triggers a fresh OAuth login."""
    if _TOKEN_FILE.exists():
        _TOKEN_FILE.unlink()
        return f"✅ token.json deleted. Next calendar call will re-authenticate."
    return "ℹ️ No token.json found — already clean."
