"""Parsing utilities for Gmail message payloads.

This module focuses solely on extracting structured fields from the raw
Gmail message object returned by the API. Responsibilities:
- Extract sender, subject and a normalized ISO8601 receive timestamp.
- Prefer ``text/plain`` content where available; fall back to sanitized
    ``text/html`` converted to plain text to provide readable content.

Design rationale
- Parsing is separated from API calls to make unit testing straightforward
    (parsers can be tested against recorded payloads).
- The fallback strategy (plain → html) is conservative: we prefer plain text
    to avoid injecting HTML into the spreadsheet, but still capture useful
    content when only HTML is present.
"""
from __future__ import annotations

import base64
import datetime as dt
from typing import Dict, Optional

from bs4 import BeautifulSoup


def _header_value(headers, name: str) -> Optional[str]:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None


def _decode_body_data(encoded: Optional[str]) -> str:
    if not encoded:
        return ""
    # Gmail uses base64url
    data = base64.urlsafe_b64decode(encoded + "==")
    try:
        return data.decode("utf-8", errors="replace")
    except Exception:
        return data.decode("latin-1", errors="replace")


def _html_to_text(html: str) -> str:
    """Convert HTML content to plain text.

    Keeps a minimal, predictable output for storing in spreadsheets. The
    conversion intentionally strips formatting and returns a single-line
    plain-text representation to keep spreadsheet cells readable.
    """
    soup = BeautifulSoup(html, "html.parser")
    # Remove script/style tags which may contain noise or executable code.
    for bad in soup(["script", "style"]):
        bad.decompose()

    # Extract visible text and normalize whitespace to single spaces.
    text = soup.get_text(" ", strip=True)
    # Normalize excessive whitespace and line breaks to single spaces.
    normalized = " ".join(text.split())
    return normalized


def _normalize_text(text: str) -> str:
    """Normalize plain-text bodies for spreadsheet display.

    - Removes excessive line breaks and whitespace
    - Collapses all whitespace to single spaces so the cell remains readable
      without embedded newlines that break row layout.
    """
    if not text:
        return ""
    # Replace common line endings with spaces and collapse whitespace
    return " ".join(text.replace("\r", "\n").split())


def parse_gmail_message(message: Dict) -> Dict[str, str]:
    """
    Extract structured fields from a Gmail ``message`` payload.

    Returns a dict with keys: ``from``, ``subject``, ``date`` (ISO8601 UTC),
    and ``content`` (plain text). The parser walks multipart payloads to find
    a ``text/plain`` part first and falls back to a sanitized ``text/html``
    part if necessary. This behavior keeps the data stored in the sheet
    predictable while capturing useful message content.
    """
    payload = message.get("payload", {})
    headers = payload.get("headers", [])

    sender = _header_value(headers, "From") or ""
    subject = _header_value(headers, "Subject") or ""

    # internalDate is epoch millis when received. Present a compact,
    # human-friendly timestamp for spreadsheet consumption (local timezone
    # if available, falling back to UTC). The ISO string is still available
    # for debugging but the formatted value reads better in a cell.
    internal_ms = int(message.get("internalDate", "0"))
    received_dt = dt.datetime.utcfromtimestamp(internal_ms / 1000.0).replace(tzinfo=dt.timezone.utc)
    try:
        local_tz = dt.datetime.now().astimezone().tzinfo
        local_dt = received_dt.astimezone(local_tz)
        formatted_date = local_dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        # Fall back to ISO8601 UTC
        formatted_date = received_dt.strftime("%Y-%m-%d %H:%M:%S %Z")

    # Body extraction
    text_body = ""

    def find_text_part(p):
        mime = p.get("mimeType", "")
        body = p.get("body", {})
        data = body.get("data")
        if mime.startswith("text/plain") and data:
            return _normalize_text(_decode_body_data(data))
        if mime.startswith("text/html") and data:
            return _html_to_text(_decode_body_data(data))
        return None

    parts = payload.get("parts")
    if parts:
        # Walk parts recursively to find text/plain first; fallback to html
        plain = None
        html_fallback = None

        def walk(parts_list):
            nonlocal plain, html_fallback
            for part in parts_list:
                content = find_text_part(part)
                if content:
                    if part.get("mimeType", "").startswith("text/plain") and plain is None:
                        plain = content
                    elif part.get("mimeType", "").startswith("text/html") and html_fallback is None:
                        html_fallback = content
                # Nested multipart
                subparts = part.get("parts")
                if subparts:
                    walk(subparts)

        walk(parts)
        text_body = plain or html_fallback or ""
    else:
        # Single-part message
        text_body = find_text_part(payload) or _decode_body_data(payload.get("body", {}).get("data")) or ""

    return {
        "from": sender,
        "subject": subject,
        "date": formatted_date,
        "content": text_body,
    }
