"""Gmail integration helpers.

This module encapsulates all Gmail API interactions required by the assignment:
- Authenticate using OAuth credentials from :mod:`config`.
- List unread messages scoped to the Inbox.
- Fetch full message payloads (headers + body) for parsing.
- Modify message labels (used here to remove ``UNREAD`` after successful
    processing).

Design notes
- Separation of concerns: keeping Gmail API logic in one module makes the
    orchestration in :mod:`src.main` straightforward and easier to test.
- Idempotency: messages are only marked as READ after downstream state has
    been persisted (see :mod:`src.sheets_service`). This preserves a clear
    recovery path if the process fails mid-run.
"""
from __future__ import annotations

import time
import logging
from typing import Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import get_credentials, APP_NAME


logger = logging.getLogger(APP_NAME)


def retry(max_attempts: int = 3, base_delay: float = 0.5, factor: float = 2.0):
    """Return a decorator that retries on transient Gmail API failures.

    This decorator retries only on ``HttpError`` (transient server / network
    failures). It uses exponential backoff to avoid hammering the API during
    intermittent outages. Caller code relies on this behaviour to be robust
    against short-lived service errors without adding retry logic throughout
    the codebase.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except HttpError as e:
                    # Attempt to inspect HTTP status code to decide whether to
                    # retry. We only retry on transient errors (429, 5xx). Do
                    # not retry on auth/permission errors (401, 403).
                    status = None
                    try:
                        status = int(getattr(e, "status_code", None) or getattr(e, "resp", {}).get("status"))
                    except Exception:
                        # If we cannot determine status, conservatively retry.
                        status = None

                    # Do not retry on auth failures
                    if status in (401, 403):
                        raise

                    should_retry = False
                    if status is None:
                        # Unknown status; treat as transient
                        should_retry = True
                    elif status == 429 or 500 <= status < 600:
                        should_retry = True

                    attempt += 1
                    if not should_retry or attempt >= max_attempts:
                        raise

                    delay = base_delay * (factor ** (attempt - 1))
                    logger.warning(
                        "HttpError (status=%s): retrying in %.1fs (attempt %d/%d)",
                        status,
                        delay,
                        attempt,
                        max_attempts,
                    )
                    time.sleep(delay)
        return wrapper
    return decorator


class GmailService:
    def __init__(self):
        creds = get_credentials()
        # Using official google-api-python-client
        self.service = build("gmail", "v1", credentials=creds)
        self.user_id = "me"  # Authenticated user

    @retry()
    def list_unread_inbox_ids(self, max_results: Optional[int] = None) -> List[str]:
        """Return message IDs for unread messages in the Inbox.

        We intentionally use the Gmail query ``in:inbox is:unread`` to strictly
        limit the scope to candidate messages for processing. Only IDs are
        returned here because fetching full payloads is a separate step and
        allows callers to implement filtering or batching.

        Pagination is handled so the caller receives a complete list.
        """
        # Base query limits scope to unread messages in the Inbox. When
        # subject filters are configured we prefer to push them into the
        # Gmail search query so the API does server-side filtering and we
        # fetch fewer message IDs.
        from config import SUBJECT_INCLUDE  # local import to avoid cycle

        base_q = "in:inbox is:unread"
        if SUBJECT_INCLUDE:
            # Construct a subject-focused query like: subject:(Invoice OR Bill)
            keywords = " OR ".join(SUBJECT_INCLUDE)
            subject_q = f"subject:({keywords})"
            q = f"{base_q} {subject_q}"
            logger.debug("Using Gmail query with subject filter: %s", q)
        else:
            q = base_q

        params = {"userId": self.user_id, "q": q}
        if max_results:
            params["maxResults"] = max_results

        ids: List[str] = []
        while True:
            resp = self.service.users().messages().list(**params).execute()
            messages = resp.get("messages", [])
            ids.extend(m["id"] for m in messages)
            token = resp.get("nextPageToken")
            if not token:
                break
            params["pageToken"] = token
        return ids

    @retry()
    def get_message_full(self, message_id: str) -> Dict:
        """Fetch the full message payload for the given ``message_id``.

        Returning the full payload (headers + body parts) lets the parser
        decide which MIME part to prefer (``text/plain`` vs ``text/html``)
        without coupling parsing decisions to fetching.
        """
        return (
            self.service.users()
            .messages()
            .get(userId=self.user_id, id=message_id, format="full")
            .execute()
        )

    @retry()
    def mark_as_read(self, message_id: str) -> None:
        """Remove the ``UNREAD`` label to mark a message as read.

        This change is performed only after the caller has successfully
        appended the parsed data to Google Sheets and recorded the
        `messageId` in persistent state. Sequencing the operations this way
        ensures the script is idempotent and recoverable: if failure occurs
        before state is persisted, the message remains UNREAD and will be
        retried on the next run.
        """
        body = {"removeLabelIds": ["UNREAD"]}
        self.service.users().messages().modify(userId=self.user_id, id=message_id, body=body).execute()
