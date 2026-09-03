"""Gmail API Email Backend for Django.

Delivers transactional emails over HTTPS (port 443) via the Google Gmail REST API.
Solves the issue of blocked outbound SMTP ports (25, 465, 587) on cloud platforms
like Railway (Free & Hobby tiers).
"""

from __future__ import annotations

import base64
import logging
import time
from typing import List, Optional

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMessage

logger = logging.getLogger(__name__)


class GmailApiEmailBackend(BaseEmailBackend):
    """Django Email Backend delivering via Gmail REST API."""

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        fail_silently: bool = False,
        **kwargs,
    ):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.client_id = client_id or getattr(settings, "GMAIL_CLIENT_ID", "")
        self.client_secret = client_secret or getattr(settings, "GMAIL_CLIENT_SECRET", "")
        self.refresh_token = refresh_token or getattr(settings, "GMAIL_REFRESH_TOKEN", "")
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0

    def _get_access_token(self) -> Optional[str]:
        """Obtain a valid access token using the OAuth2 refresh token."""
        # Reuse existing token if it has at least 60 seconds of validity remaining
        if self._access_token and time.time() < (self._token_expiry - 60):
            return self._access_token

        if not (self.client_id and self.client_secret and self.refresh_token):
            err_msg = (
                "Gmail API Email Backend is missing credentials. "
                "Ensure GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, and GMAIL_REFRESH_TOKEN are configured."
            )
            logger.error(err_msg)
            if not self.fail_silently:
                raise ValueError(err_msg)
            return None

        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token",
        }

        try:
            resp = requests.post(self.TOKEN_URL, data=payload, timeout=12)
            if resp.status_code != 200:
                err_msg = f"Failed to refresh Gmail API OAuth token ({resp.status_code}): {resp.text}"
                logger.error(err_msg)
                if not self.fail_silently:
                    raise RuntimeError(err_msg)
                return None

            data = resp.json()
            self._access_token = data.get("access_token")
            expires_in = int(data.get("expires_in", 3600))
            self._token_expiry = time.time() + expires_in
            return self._access_token
        except Exception as exc:
            logger.error("Exception during Gmail API OAuth token refresh: %s", exc)
            if not self.fail_silently:
                raise
            return None

    def send_messages(self, email_messages: List[EmailMessage]) -> int:
        """Send a list of EmailMessage instances through the Gmail API."""
        if not email_messages:
            return 0

        access_token = self._get_access_token()
        if not access_token:
            return 0

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        sent_count = 0

        for message in email_messages:
            try:
                # Convert message (including HTML alternative and attachments) to RFC 2822 MIME bytes
                mime_msg = message.message()
                raw_bytes = mime_msg.as_bytes()
                # Gmail API expects base64url encoded string
                raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("ascii")

                body = {"raw": raw_b64}
                resp = requests.post(self.SEND_URL, headers=headers, json=body, timeout=20)

                if resp.status_code in (200, 202):
                    sent_count += 1
                    logger.info("Successfully sent email to %s via Gmail API", message.to)
                else:
                    err = f"Gmail API send failed ({resp.status_code}): {resp.text}"
                    logger.error(err)
                    if not self.fail_silently:
                        raise RuntimeError(err)
            except Exception as err:
                logger.error("Error sending email via Gmail API: %s", err)
                if not self.fail_silently:
                    raise

        return sent_count
