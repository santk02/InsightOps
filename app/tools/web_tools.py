"""Web fetch tools."""

from __future__ import annotations

import re

import httpx


def _html_to_markdown(html: str) -> str:
    """Strip scripts/styles/tags down to plain text, capped so it fits comfortably in a prompt."""
    text = re.sub(
        r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)  # drop remaining tags
    text = re.sub(r"\s+", " ", text).strip()  # collapse whitespace
    return text[:8000]


def fetch_page(url: str, timeout: float = 15.0) -> str:
    """Fetch a web page (safe, read-only) and return markdown-ish text for supporting context."""
    if not url.startswith(("http://", "https://")):
        raise ValueError("URL must start with http:// or https://")

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(url, headers={"User-Agent": "InsightOps/0.1"})
        response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    if "html" in content_type:
        return _html_to_markdown(response.text)
    return response.text[:8000]  # non-HTML (e.g. plain text/JSON) — just cap the length


def send_email(to: str, subject: str, body: str) -> dict[str, str]:
    """Represent an external send; the graph must approve it before calling — RISKY."""
    if not to.strip() or "@" not in to:
        raise ValueError("A valid recipient is required")
    if not subject.strip() or not body.strip():
        raise ValueError("Email subject and body are required")
    return {"status": "queued", "to": to, "subject": subject}
