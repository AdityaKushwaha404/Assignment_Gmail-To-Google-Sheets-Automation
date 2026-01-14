# Gmail → Google Sheets Automation

## Overview

Small, safe Python tool that idempotently syncs unread Gmail Inbox messages into a Google Sheet, preventing duplicates by persisting `messageId`s and only marking messages read after successful persistence. It is auditable: rows are appended to an `Emails` sheet and processed `messageId`s are recorded in a `Processed` sheet.

Core guarantees:
- Processes unread Inbox messages (optional subject filtering).
- Prevents duplicates using persisted `messageId` state in the spreadsheet.
- Marks messages READ only after rows and IDs are persisted.

## High-level architecture

```
           +-----------+        +----------------+        +-------------+
           |  src/main.py | -----> | gmail_service  | -----> | Gmail API   |
           +-----------+        +----------------+        +-------------+
                 |                      |
                 |                      v
                 |                +-------------+
                 |                | email_parser|
                 |                +-------------+
                 v
           +----------------+
           | sheets_service | -----> Google Sheets (Emails, Processed)
           +----------------+
```

## Project structure

```
gmail-to-sheets/
├── src/
│   ├── gmail_service.py
│   ├── email_parser.py
│   ├── sheets_service.py
│   └── main.py
├── credentials/        # credentials.json (DO NOT COMMIT) + token.json
├── proof/              # screenshots + demo video
├── requirements.txt
├── config.py
└── README.md
```

## Setup (step-by-step)

1. Create a Google Cloud project and enable the **Gmail API** and **Google Sheets API**.
2. Create OAuth client credentials (Application type: Desktop app). Download JSON and place it at `credentials/credentials.json`.

      The OAuth client must be created as a "Desktop app" to support the Installed App flow used by this tool.
3. Create a Google Spreadsheet and copy its Spreadsheet ID.
4. Create a virtual environment and install dependencies:

```bash
cd gmail-to-sheets
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

5. Set environment variables (example):

```bash
export SPREADSHEET_ID="your_spreadsheet_id_here"
export SUBJECT_INCLUDE="Invoice,Bill,Payment"  # optional; empty = disabled
export LOG_LEVEL=INFO
```

6. Run the sync:

```bash
python -m src.main
```

On first run the browser opens for OAuth consent; `token.json` is saved to `credentials/token.json`.

## OAuth flow explanation

This project uses the OAuth 2.0 Installed App (desktop) flow:
- Place `credentials/credentials.json` (OAuth client) in the `credentials/` directory.
- On first run the app opens a browser to obtain user consent; the resulting token is persisted to `credentials/token.json` and refreshed when possible.

Why not a service account: service accounts cannot access personal Gmail mailboxes without domain-wide delegation; the installed app flow provides explicit user consent for a single account and is appropriate for this CLI-style tool.

## Duplicate prevention & state persistence

- `Processed` sheet stores canonical Gmail `messageId`s. The script loads these IDs at start and skips any already-seen messages.
- Append order: first append rows to `Emails`, then append `messageId`s to `Processed`. Only after both appends succeed are messages marked READ.
- This sequence prevents acknowledging messages that were not persisted and ensures idempotency across runs and machines.

## Bonus features implemented (optional)

- Subject-based server-side filtering via `SUBJECT_INCLUDE` (comma-separated keywords).
- HTML → plain-text fallback using BeautifulSoup when `text/plain` is absent; content is normalized to a single spreadsheet-friendly line.
- Structured timestamped logging with configurable `LOG_LEVEL`.
- Exponential-backoff retry logic for transient Gmail API errors (HTTP 429 and 5xx).

## One challenge + solution

Challenge: avoiding duplicate rows if the script is interrupted between persistence and acknowledging messages.

Solution: only mark messages READ after both the `Emails` row and the `Processed` `messageId` have been successfully appended. If a run fails mid-way the message remains unread and will be retried; `Processed` prevents duplicates.

## Limitations

- Attachments are not processed; only message bodies are captured.
- `Processed` IDs are loaded into memory; extremely large histories may require a different store.
- HTML-to-text conversion is best-effort; complex formatting may be lost.
- The sync targets Inbox unread messages by design.

## Proof of execution (mandatory)

Place required artifacts (screenshots and a short demo video) in the `proof/` directory. See [proof/README.md](proof/README.md) for filenames and a short checklist.

Download video file from proof folder to see demo.

<img width="3360" height="1924" alt="image" src="https://github.com/user-attachments/assets/1e02ada5-8516-4fc5-999a-49841f45c2b7" />

<img width="3360" height="1304" alt="image" src="https://github.com/user-attachments/assets/52773dbd-74e4-4675-980f-fcd60c37c143" />

<img width="3360" height="1924" alt="image" src="https://github.com/user-attachments/assets/8b0a468b-4b79-903c-0d28b24bad51" />

<img width="3360" height="2018" alt="image" src="https://github.com/user-attachments/assets/0c210460-6041-40b5-bd80-7f071dee68e7" />

<img width="1726" height="422" alt="image" src="https://github.com/user-attachments/assets/8a236221-8584-4bd4-8cf2-f1392c34f65a" />

<img width="3360" height="1924" alt="image" src="https://github.com/user-attachments/assets/5c330362-fc43-4615-821a-b756cd747cd7" />

<img width="3360" height="1918" alt="image" src="https://github.com/user-attachments/assets/72ac64a4-0e46-4569-bb05-66c74870ee06" />

<img width="3360" height="1048" alt="image" src="https://github.com/user-attachments/assets/f9e0ac91-b78d-485f-9958-d883b51854cf" />

<img width="1876" height="710" alt="image" src="https://github.com/user-attachments/assets/f9fac17b-beff-4df1-8b38-e8822b80dcbb" />


## Author

Aditya Kushwaha
