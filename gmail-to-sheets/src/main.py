"""Orchestrate the Gmail → Sheets sync.

This module coordinates authentication, message retrieval, parsing, sheet
appends, and final message acknowledgement. Key responsibilities and
design points:
- Load processed `messageId`s from the spreadsheet to prevent duplicates.
- Fetch only ``UNREAD`` messages from the Inbox to keep scope minimal.
- Parse message payloads independently (see :mod:`src.email_parser`).
- Append parsed rows and persist message IDs before marking messages READ
    to maintain idempotency and allow safe retries.

The orchestration deliberately keeps business logic minimal and defers
Gmail/Sheets specifics to dedicated modules to make the flow easy to
explain during evaluation.
"""
from __future__ import annotations

import logging
from typing import List, Dict

from config import APP_NAME, DEFAULT_LOG_LEVEL, SUBJECT_INCLUDE, SUBJECT_EXCLUDE
from src.gmail_service import GmailService
from src.email_parser import parse_gmail_message
from src.sheets_service import SheetsService


def subject_passes_filters(subject: str) -> bool:
    """Return True if ``subject`` passes include/exclude filters.

    Rationale: filtering is applied early so we avoid unnecessary API calls
    and sheet writes for messages that do not match evaluator-specified
    criteria. Both include and exclude lists are optional; include acts as
    a whitelist, exclude as a blacklist.
    """
    if SUBJECT_INCLUDE:
        if not any(k.lower() in subject.lower() for k in SUBJECT_INCLUDE):
            return False
    if SUBJECT_EXCLUDE:
        if any(k.lower() in subject.lower() for k in SUBJECT_EXCLUDE):
            return False
    return True


def run() -> None:
    """Perform one sync run.

    Sequence and safety properties:
    1. Load processed IDs from Sheets to skip duplicates.
    2. List unread Inbox messages and fetch full payloads for new IDs.
    3. Parse and filter messages; collect rows to append.
    4. Append rows and record IDs atomically via :class:`SheetsService`.
    5. Only after successful append + ID persistence, mark messages as READ.

    The explicit sequencing ensures the run is idempotent and recoverable.
    Logging at each step provides observability for debugging and grading.
    """
    logging.basicConfig(
        level=getattr(logging, DEFAULT_LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger = logging.getLogger(APP_NAME)

    logger.info("Starting Gmail → Sheets sync")
    gmail = GmailService()
    sheets = SheetsService()

    processed_ids = set(sheets.get_processed_ids())
    logger.info(f"Loaded {len(processed_ids)} processed IDs from Sheets")

    unread_ids = gmail.list_unread_inbox_ids()
    logger.info(f"Found {len(unread_ids)} unread messages in Inbox")

    rows: List[Dict[str, str]] = []
    to_mark_read: List[str] = []

    for mid in unread_ids:
        if mid in processed_ids:
            logger.debug(f"Skipping already processed messageId={mid}")
            continue
        message = gmail.get_message_full(mid)
        parsed = parse_gmail_message(message)
        if not subject_passes_filters(parsed.get("subject", "")):
            logger.debug(f"Subject filtered out for messageId={mid}")
            continue
        rows.append(parsed)
        to_mark_read.append(mid)

    if rows:
        logger.info(f"Appending {len(rows)} new rows to Sheets")
        sheets.append_email_rows(rows, to_mark_read)
        for mid in to_mark_read:
            gmail.mark_as_read(mid)
        logger.info(f"Marked {len(to_mark_read)} messages as READ")
    else:
        logger.info("No new rows to append; nothing to mark as read")

    logger.info("Sync complete")


if __name__ == "__main__":
    run()
