from __future__ import annotations
import logging
import os

logger = logging.getLogger(__name__)


class GoogleSync:
    """Google Calendar and Sheets integration via official API.

    Requires google-auth and google-api-python-client packages.
    Gracefully degrades if credentials are not configured or packages not installed.
    """

    def __init__(self, credentials_path: str | None = None):
        from jarvis import config
        self._creds_path = credentials_path or os.path.join(
            config.DATA_DIR, "google_credentials.json"
        )
        self._service_cache: dict = {}

    def is_configured(self) -> bool:
        """Check if Google credentials file exists."""
        return os.path.exists(self._creds_path)

    def sync_calendar(self, max_results: int = 50) -> list[dict]:
        """Fetch upcoming calendar events. Returns empty list if not configured."""
        if not self.is_configured():
            logger.debug("Google Calendar not configured — skipping sync")
            return []
        try:
            service = self._get_service("calendar", "v3")
            logger.info("Google Calendar sync: credentials found but OAuth flow not yet implemented")
            return []
        except Exception as exc:
            logger.warning("Google Calendar sync failed: %s", exc)
            return []

    def sync_sheets(self, sheet_id: str, range_name: str = "A1:Z1000") -> list[dict]:
        """Fetch data from a Google Sheet. Returns empty list if not configured."""
        if not self.is_configured():
            return []
        try:
            service = self._get_service("sheets", "v4")
            logger.info("Google Sheets sync: credentials found but OAuth flow not yet implemented")
            return []
        except Exception as exc:
            logger.warning("Google Sheets sync failed: %s", exc)
            return []

    def _get_service(self, api: str, version: str):
        """Get or create a cached Google API service object."""
        key = f"{api}_{version}"
        if key not in self._service_cache:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            creds = Credentials.from_authorized_user_file(self._creds_path)
            self._service_cache[key] = build(api, version, credentials=creds)
        return self._service_cache[key]
