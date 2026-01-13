# 📩 Gmail → Google Sheets Automation

## Overview

This project synchronizes UNREAD messages from a Gmail Inbox into a Google
Sheet in an idempotent, auditable, and explainable way. It is safe to run
repeatedly and is designed to be easy to demonstrate for evaluation.

Key guarantees:
- Processes only unread Inbox messages (subject filtering optional).
- Prevents duplicate rows via persisted `messageId` state in the spreadsheet.
- Marks messages as READ only after successful persistence of data and IDs.
- Uses OAuth 2.0 Installed App flow (no service accounts).
- Normalizes email bodies to produce clean, single-line spreadsheet cells.

---

## Quick links

- Entry point: `src/main.py`
- Gmail helpers: `src/gmail_service.py`
- Parsing + cleanup: `src/email_parser.py`
- Sheets helpers: `src/sheets_service.py`
- Config & OAuth: `config.py`

---

## Setup (short)

1. Create a Google Cloud project and enable:
   - Gmail API
   - Google Sheets API

2. Create OAuth credentials (Application type: Desktop app) and place the
   downloaded JSON at:

```
credentials/credentials.json
```

> ⚠️ Never commit credentials to version control.

3. Create a Google Sheet and copy its Spreadsheet ID.

4. Create and activate a Python virtual environment, then install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

5. Configure environment variables (example):

```bash
export SPREADSHEET_ID="your_spreadsheet_id_here"
export SUBJECT_INCLUDE="Invoice,Bill,Payment"  # optional; set empty to process all unread
export LOG_LEVEL=INFO
```

6. Run the sync:

```bash
python -m src.main
```

On first run the Installed App flow opens a browser for consent; a token is
saved to `credentials/token.json` for subsequent non-interactive runs.

---

## Detailed workflow & rationale

1. Authenticate (OAuth) using `config.get_credentials()`.
2. Ensure the Google Sheet contains the `Emails` and `Processed` tabs (the
   code creates them with headers on first run).
3. Load processed `messageId`s from `Processed!A2:A` to build the dedupe set.
4. Query Gmail for unread Inbox IDs. If `SUBJECT_INCLUDE` is set, the Gmail
   query includes `subject:(...)` so filtering happens server-side for
   efficiency.
5. For each unseen message ID: fetch the full message, parse headers and
   body, normalize the body into a single-line string, and collect rows.
6. Append all rows to the `Emails` tab and then append their `messageId`s to
   the `Processed` tab. Only after both appends succeed are messages marked
   READ via the Gmail API.

Why this ordering?
- Appending rows first then persisting IDs, combined with marking READ only
  after both operations, keeps the run idempotent and recoverable from
  mid-run failures.

---

## Parsing & spreadsheet formatting

- The parser prefers `text/plain` content. If missing it falls back to
  `text/html` which is cleaned using BeautifulSoup:
  - removes `<script>` and `<style>` tags
  - extracts visible text and collapses whitespace
- For `text/plain` bodies we collapse newlines and excessive whitespace so
  each message content fits in a single spreadsheet cell without embedded
  line breaks.

This makes the sheet easier to scan and avoids breaking row formatting.

---

## Subject-based filtering

- Default keywords (configurable): `Invoice, Bill, Payment`.
- Set `SUBJECT_INCLUDE` as a comma-separated env var to change behavior.
- To process all unread emails, unset or set `SUBJECT_INCLUDE` to an empty
  string.

Server-side filtering is preferred because it reduces the number of API
calls and the amount of data the script needs to process.

---

## Retry & error handling

- Gmail API calls use an exponential backoff retry decorator. Retries are
  attempted only for transient errors (HTTP 429 and 5xx). Authentication and
  permission errors (401, 403) are NOT retried and are surfaced immediately.

---

## Logging & observability

- Logs are structured to include timestamp, level and module name.
- The app logs key lifecycle events: auth success/refresh, query used,
  counts of processed/unread messages, rows appended, IDs appended, messages
  marked READ, and retry attempts/errors.
- Enable verbose logs with:

```bash
export LOG_LEVEL=DEBUG
```

---

## Docker (optional)

A minimal `Dockerfile` is included for reproducible runs. Do **not** bake
credentials into images. Use a volume mount to provide `credentials/` at
runtime:

```bash
docker build -t gmail-to-sheets .
docker run --rm -v "$PWD/credentials":/app/credentials:rw gmail-to-sheets
```

---

## Proof of execution (what to include under `proof/`)

- `gmail_unread.png` — Gmail inbox screenshot showing unread messages used in the demo.
- `sheet_rows.png` — Google Sheet screenshot showing rows added by the script.
- `oauth_consent.png` — OAuth consent screen (optional: blur personal info).
- `demo.mp4` — 2–3 minute screen recording demonstrating the flow,
  duplicate prevention, and running the script twice to show idempotency.

Place these artifacts inside the `proof/` directory before submission.

---

## Limitations & future work

- Attachments are not processed; only message bodies are captured.
- `Processed` IDs are loaded in memory; for very large histories consider a
  different backing store.
- Future improvements: time-based filters, label-based filtering, scheduled
  execution (Cloud Run / cron), and unit tests that mock API clients.

---

## Author

Aditya Kushwaha

---

If you paste this README into the repository and upload the `proof/`
artifacts, the repository is submission-ready.
# Gmail → Google Sheets Automation (OAuth 2.0)

**Full Name (required for submission):** REPLACE_WITH_YOUR_FULL_NAME

## High-level architecture diagram (mandatory)

```
     ┌─────────────────────────────┐
     │           main.py           │
     │ orchestrates end-to-end run │
     └──────────────┬──────────────┘
        │
  ┌───────────────────────┼────────────────────────┐
  │                       │                        │
┌───────▼────────┐     ┌────────▼─────────┐     ┌────────▼──────────┐
│ gmail_service.py│     │ email_parser.py  │     │ sheets_service.py  │
│ Gmail API        │     │ payload → fields │     │ Sheets API         │
│ list/get/modify  │     │ plain/html body  │     │ append + state      │
└───────┬────────┘     └────────┬─────────┘     └────────┬──────────┘
  │                       │                        │
  │ OAuth (user)          │                        │ OAuth (user)
  │ via config.py         │                        │ via config.py
  │                       │                        │
  ▼                       ▼                        ▼
  Gmail Inbox (UNREAD)     Parsed Email Fields     Google Sheet
  query: in:inbox          (From/Subject/Date/     - Emails tab
  is:unread                Content)                - Processed tab
```

## High-level architecture

This project syncs **UNREAD Inbox emails** from Gmail into a Google Sheet.

**Modules**
- `src/gmail_service.py`: Gmail API access (OAuth, list unread inbox, fetch full message, mark read).
- `src/email_parser.py`: Parses Gmail message payloads into `{from, subject, date, content}`.
- `src/sheets_service.py`: Google Sheets API access (ensure tabs exist, load processed IDs, append new rows, persist IDs).
- `src/main.py`: Orchestrates the end-to-end flow and enforces idempotency.
- `config.py`: Central config + shared OAuth credential loader.

## Project structure

```
gmail-to-sheets/
├── src/
│   ├── gmail_service.py
│   ├── sheets_service.py
│   ├── email_parser.py
│   └── main.py
├── credentials/
│   └── credentials.json (DO NOT COMMIT)
├── proof/
│   ├── README.md
│   └── (screenshots + video go here)
├── .gitignore
├── requirements.txt
├── README.md
└── config.py
```

## Setup (step-by-step)

### 1) Create a Google Cloud project + enable APIs
Enable:
- **Gmail API**
- **Google Sheets API**

### 2) Configure OAuth consent screen
- Choose **External** (typical for personal Gmail) or **Internal** (Workspace).
- Add your test user email if the app is in testing.

### 3) Create OAuth 2.0 credentials (NO service accounts)
- Create **OAuth client ID** → Application type: **Desktop app**.
- Download the JSON and place it at:

`gmail-to-sheets/credentials/credentials.json`

> This file is ignored by `.gitignore` and must never be committed.

### 4) Create a Google Sheet
- Create a spreadsheet and copy its **Spreadsheet ID** from the URL.

Set it via env var:

```bash
export SPREADSHEET_ID="your_spreadsheet_id_here"
```

Or replace the placeholder in `config.py`.

### 5) Install dependencies

```bash
cd gmail-to-sheets
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 6) Run

```bash
python -m src.main
```

On first run, your browser will open for OAuth login/consent.

## OAuth flow explanation

This app uses the **OAuth 2.0 Installed App** flow (desktop app style):
- Place the OAuth client file at ``credentials/credentials.json`` (downloaded
  from Google Cloud Console).
- On first run, :func:`config.get_credentials` starts a browser-based consent
  flow and saves the resulting token to ``credentials/token.json``.
- Subsequent runs reuse and refresh the token when possible, avoiding repeated
  interactive consent.

Rationale: Gmail mailbox access requires user OAuth consent. The installed
app flow is appropriate for this CLI-style tool and keeps the token under
the user's control (no service account is used).

## Docker (optional)

You can run the app inside Docker. The image deliberately does not include
your OAuth credentials. Mount the local ``credentials/`` directory into the
container at runtime so the app can access ``credentials/credentials.json``
and persist ``credentials/token.json``.

Example:

```bash
docker build -t gmail-to-sheets .
docker run --rm -v "$PWD/credentials":/app/credentials:rw gmail-to-sheets
```

Do not bake secrets into the image; use volume mounts or an external secret
management system for production deployments.

## Duplicate prevention logic (STRICT)

Requirement: "Append ONLY new emails since previous run" and "Prevent duplicates strictly".

This project uses Gmail ``messageId`` as the canonical unique key:
- All processed message IDs are stored in the spreadsheet tab ``Processed``.
- Before appending, the script loads those IDs and skips any already-seen
  messages, ensuring strict de-duplication even across machines.

Why store IDs in Sheets:
- Visible and auditable state; helpful during evaluation.
- Portable across environments and users; avoids hidden local state.

## State persistence explanation

State is kept in the spreadsheet:
- ``Emails`` tab: human-friendly rows (``From``, ``Subject``, ``Date``, ``Content``).
- ``Processed`` tab: one column of persisted ``messageId`` values.

Processing order (idempotent):
1. Load processed IDs from ``Processed``.
2. List Gmail messages matching ``in:inbox is:unread``.
3. For each unread message: skip if already-processed; otherwise parse and
  collect for append.
4. Append collected rows to ``Emails`` and append their IDs to ``Processed``.
5. After both appends succeed, mark the corresponding Gmail messages as READ.

Sequencing ensures we do not acknowledge (mark READ) messages until their
data and IDs have been safely persisted.

## Bonus features included

- **Subject-based filtering**:
  - `SUBJECT_INCLUDE` env var: comma-separated keywords; only keep matching subjects.
  - `SUBJECT_EXCLUDE` env var: comma-separated keywords; exclude matching subjects.

Example:

```bash
export SUBJECT_INCLUDE="Invoice,Receipt"
export SUBJECT_EXCLUDE="Spam"
```

- **HTML → plain text fallback**:
  - If a message has no `text/plain`, `src/email_parser.py` converts `text/html` to plain text using BeautifulSoup.

- **Logging with timestamps**:
  - `src/main.py` configures logging with timestamps.

- **Retry logic**:
  - `src/gmail_service.py` retries transient `HttpError` failures with exponential backoff.

## One challenge + solution

**Challenge:** Preventing duplicates reliably when the script is interrupted.

**Solution:** The script only marks messages as **READ** *after* it successfully appends both:
- the email row to `Emails`, and
- the messageId to `Processed`.

This ensures that if the run fails mid-way, unread messages remain unread and will be picked up again, but duplicates are still prevented by the `Processed` state.

## Limitations

- `Processed` IDs are loaded into memory; for extremely large histories you may need batching or a different lookup strategy.
- The parser uses a simple HTML-to-text conversion; complex HTML emails may lose formatting.
- This sync only reads **Inbox** and only **Unread** by design (per assignment requirements).

## Proof of execution (mandatory)

Put required screenshots and the short demo video in [proof/](proof/):
- Gmail inbox showing unread emails
- Google Sheet with at least 5 rows populated by the script
- OAuth consent screen
- 2–3 minute video explaining flow + dedupe + running twice behavior

See [proof/README.md](proof/README.md) for a checklist and suggested filenames.

## Submission checklist (per assignment)

- Repository is public (GitHub/GitLab)
- No secrets committed (credentials/tokens are ignored by `.gitignore`)
- README includes: architecture diagram, setup, OAuth flow, dedupe, state persistence, challenge+solution, limitations
- [proof/](proof/) contains screenshots + video

## Post-submission change readiness

The code is modular (Gmail API, parsing, Sheets API are separated) so typical follow-up requests like:
- “only emails from last 24 hours”
- “add a new column for labels”
- “exclude no-reply senders”

can be implemented with localized changes in `gmail_service.py` / `email_parser.py` / `sheets_service.py`.
