"""Google Sheets access and state persistence helpers.

This module manages the spreadsheet used by the assignment. Responsibilities:
- Ensure the required worksheet tabs exist and initialize headers on first run.
- Load persisted `messageId`s used to prevent duplicate processing.
- Append parsed email rows to the ``Emails`` tab and persist message IDs to the
    ``Processed`` tab.

Design notes and trade-offs
- State persistence: storing `messageId`s in the spreadsheet keeps state
    visible and portable across environments, which is useful for auditing.
- Sequencing: the implementation appends email rows first and then appends
    `messageId`s. While not a single transactional operation (Google Sheets
    API does not provide multi-range transactional writes here), this ordering
    plus the caller's decision to mark Gmail messages as READ only after both
    appends succeed preserves the practical idempotency required by the
    assignment.
"""
from __future__ import annotations

import logging
from typing import List, Dict

from googleapiclient.discovery import build

from config import get_credentials, APP_NAME, SPREADSHEET_ID, SHEET_EMAILS, SHEET_PROCESSED

logger = logging.getLogger(APP_NAME)


class SheetsService:
    def __init__(self):
        creds = get_credentials()
        self.service = build("sheets", "v4", credentials=creds)
        self.sheet_id = SPREADSHEET_ID
        # Accept spreadsheet ID from environment via `config.py` (SPREADSHEET_ID).
        # Guard against empty/placeholder values and provide a clear actionable error.
        if not self.sheet_id or str(self.sheet_id).strip() == "" or self.sheet_id == "REPLACE_WITH_YOUR_SPREADSHEET_ID":
            raise ValueError(
                "Spreadsheet ID not configured. Set the SPREADSHEET_ID environment variable or update `config.py` with a valid Spreadsheet ID."
            )

    def _ensure_sheets_exist(self) -> None:
        """Create required tabs and headers if they do not already exist.

        This is idempotent and safe to call on every run; it avoids a hard
        failure on first-run when the spreadsheet is empty or newly created.
        """
        sheets_metadata = self.service.spreadsheets().get(spreadsheetId=self.sheet_id).execute()
        titles = {s.get("properties", {}).get("title") for s in sheets_metadata.get("sheets", [])}
        requests: List[Dict] = []

        if SHEET_EMAILS not in titles:
            requests.append({
                "addSheet": {
                    "properties": {
                        "title": SHEET_EMAILS,
                    }
                }
            })
        if SHEET_PROCESSED not in titles:
            requests.append({
                "addSheet": {
                    "properties": {
                        "title": SHEET_PROCESSED,
                    }
                }
            })

        if requests:
            self.service.spreadsheets().batchUpdate(spreadsheetId=self.sheet_id, body={"requests": requests}).execute()
            # Write headers
            self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range=f"{SHEET_EMAILS}!A1:D1",
                valueInputOption="RAW",
                body={"values": [["From", "Subject", "Date", "Content"]]},
            ).execute()
            self.service.spreadsheets().values().update(
                spreadsheetId=self.sheet_id,
                range=f"{SHEET_PROCESSED}!A1:A1",
                valueInputOption="RAW",
                body={"values": [["messageId"]]},
            ).execute()

    def get_processed_ids(self) -> List[str]:
        """Return stored message IDs from the ``Processed`` tab.

        The range read is ``A2:A``; the header in ``A1`` is intentionally
        skipped. Empty cells are ignored. The returned list is used by the
        orchestrator to skip already-processed messages and ensure
        duplicate-free appends.
        """
        self._ensure_sheets_exist()
        resp = self.service.spreadsheets().values().get(
            spreadsheetId=self.sheet_id,
            range=f"{SHEET_PROCESSED}!A2:A",
        ).execute()
        values = resp.get("values", [])
        return [row[0] for row in values if row]

    def append_email_rows(self, rows: List[Dict[str, str]], message_ids: List[str]) -> None:
        """Append parsed email rows to ``Emails`` and persist their message IDs.

        Behaviour and error handling:
        - No operation is performed if ``rows`` is empty.
        - The method ensures the required tabs exist before writing.
        - First it appends the email data, then it appends the matching
          ``messageId`` values. If either step fails an exception is raised and
          the caller should *not* mark Gmail messages as READ.

        The caller (orchestrator) is responsible for marking messages READ only
        after this method completes successfully. This sequencing prevents the
        script from acknowledging a message without persisting its data.
        """
        if not rows:
            return
        self._ensure_sheets_exist()

        data_values = [
            [
                r.get("from", ""),
                r.get("subject", ""),
                r.get("date", ""),
                r.get("content", ""),
            ]
            for r in rows
        ]

        # Append email data (log payload for debugging)
        logger.debug("Preparing to append email rows to sheet '%s': %s", SHEET_EMAILS, data_values)
        try:
            resp_emails = self.service.spreadsheets().values().append(
                spreadsheetId=self.sheet_id,
                range=f"{SHEET_EMAILS}!A2",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": data_values},
            ).execute()
            logger.debug("Emails append response: %s", resp_emails)
            # Surface success at info level for lifecycle visibility.
            updates = resp_emails.get("updates", {})
            rows_appended = updates.get("updatedRows") if updates else None
            logger.info("Appended %s rows to '%s'", rows_appended, SHEET_EMAILS)
        except Exception:
            logger.exception("Failed to append email rows to '%s'; aborting processed IDs write.", SHEET_EMAILS)
            raise

        # Record processed IDs (one per row)
        id_values = [[mid] for mid in message_ids]
        logger.debug("Preparing to append processed IDs to sheet '%s': %s", SHEET_PROCESSED, id_values)
        try:
            resp_ids = self.service.spreadsheets().values().append(
                spreadsheetId=self.sheet_id,
                range=f"{SHEET_PROCESSED}!A2",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": id_values},
            ).execute()
            logger.debug("Processed IDs append response: %s", resp_ids)
            updates = resp_ids.get("updates", {})
            ids_appended = updates.get("updatedRows") if updates else None
            logger.info("Appended %s ids to '%s'", ids_appended, SHEET_PROCESSED)
        except Exception:
            logger.exception("Failed to append processed IDs to '%s' after emails append.", SHEET_PROCESSED)
            # At this point emails were appended but recording IDs failed; surface
            # the error so the caller does not mark messages as READ.
            raise
