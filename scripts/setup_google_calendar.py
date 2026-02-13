#!/usr/bin/env python3
"""
Google Calendar Setup Script
=============================
Authorizes the CAIO swarm to access your Google Calendar.

Usage:
    python scripts/setup_google_calendar.py          # Run OAuth flow
    python scripts/setup_google_calendar.py --test    # Test existing token
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).parent.parent
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
TOKEN_FILE = PROJECT_ROOT / "token.json"

# Calendar scope needed for the scheduler agent
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def check_dependencies():
    """Check that required Google libraries are installed."""
    missing = []
    try:
        from google.auth.transport.requests import Request  # noqa: F401
    except ImportError:
        missing.append("google-auth")
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: F401
    except ImportError:
        missing.append("google-auth-oauthlib")
    try:
        from googleapiclient.discovery import build  # noqa: F401
    except ImportError:
        missing.append("google-api-python-client")

    if missing:
        print(f"Missing libraries: {', '.join(missing)}")
        print(f"Install with: pip install {' '.join(missing)}")
        sys.exit(1)


def run_oauth_flow():
    """Run the Google OAuth 2.0 flow to get calendar access."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CREDENTIALS_FILE.exists():
        print(f"ERROR: {CREDENTIALS_FILE} not found.")
        print("This file contains your Google Cloud OAuth client credentials.")
        print("Download it from: https://console.cloud.google.com/apis/credentials")
        sys.exit(1)

    creds = None

    # Check for existing token
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception:
            creds = None

    # If valid credentials exist, check if they have the right scopes
    if creds and creds.valid:
        existing_scopes = set(creds.scopes or [])
        needed_scopes = set(SCOPES)
        if needed_scopes.issubset(existing_scopes):
            print("Token already valid with correct scopes.")
            print(f"Scopes: {', '.join(creds.scopes)}")
            return creds

        print("Token exists but missing calendar scope. Re-authorizing...")

    # Try to refresh expired token
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            existing_scopes = set(creds.scopes or [])
            if "https://www.googleapis.com/auth/calendar" in existing_scopes:
                # Save refreshed token
                TOKEN_FILE.write_text(creds.to_json())
                print("Token refreshed successfully.")
                return creds
            else:
                print("Refreshed token missing calendar scope. Re-authorizing...")
        except Exception as e:
            print(f"Token refresh failed: {e}. Re-authorizing...")

    # Run the full OAuth flow
    print()
    print("=" * 60)
    print("  Google Calendar Authorization")
    print("=" * 60)
    print()
    print("A browser window will open. Please:")
    print("  1. Sign in with your Google account")
    print("  2. Click 'Continue' to grant calendar access")
    print("  3. Close the browser when done")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_FILE), SCOPES
    )
    creds = flow.run_local_server(port=0)

    # Save the token
    TOKEN_FILE.write_text(creds.to_json())
    print()
    print(f"Calendar authorization successful!")
    print(f"Token saved to {TOKEN_FILE}")
    print(f"Scopes: {', '.join(creds.scopes or [])}")

    return creds


def test_calendar(creds):
    """Test the calendar connection by listing upcoming events."""
    from googleapiclient.discovery import build

    print()
    print("=" * 60)
    print("  Testing Calendar Connection")
    print("=" * 60)
    print()

    try:
        service = build("calendar", "v3", credentials=creds)

        # Get calendar info
        calendar = service.calendars().get(calendarId="primary").execute()
        print(f"Connected to calendar: {calendar.get('summary', 'Unknown')}")
        print(f"Timezone: {calendar.get('timeZone', 'Unknown')}")
        print()

        # List upcoming events
        now = datetime.utcnow().isoformat() + "Z"
        end = (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"

        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                timeMax=end,
                maxResults=10,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = events_result.get("items", [])

        if events:
            print(f"Upcoming events (next 7 days):")
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                summary = event.get("summary", "No title")
                # Format nicely
                try:
                    dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                    formatted = dt.strftime("%a %b %d, %I:%M %p")
                except Exception:
                    formatted = start
                print(f"  - {summary} ({formatted})")
        else:
            print("No upcoming events in the next 7 days.")

        print()
        print("Calendar integration is working!")
        return True

    except Exception as e:
        print(f"ERROR: Calendar test failed: {e}")
        print()
        print("Common fixes:")
        print("  - Enable Calendar API: https://console.cloud.google.com/apis/library/calendar-json.googleapis.com")
        print("  - Re-run authorization: python scripts/setup_google_calendar.py")
        return False


def main():
    parser = argparse.ArgumentParser(description="Google Calendar Setup")
    parser.add_argument(
        "--test", action="store_true", help="Test existing calendar connection"
    )
    args = parser.parse_args()

    check_dependencies()

    if args.test:
        # Test mode: load existing token
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        if not TOKEN_FILE.exists():
            print("No token.json found. Run without --test first to authorize.")
            sys.exit(1)

        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json())

        success = test_calendar(creds)
        sys.exit(0 if success else 1)
    else:
        # Authorization mode
        creds = run_oauth_flow()
        test_calendar(creds)


if __name__ == "__main__":
    main()
