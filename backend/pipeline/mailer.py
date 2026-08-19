"""
Email dispatch for the AI advisory — the "act" step of the agentic workflow.

Sends the generated report to a recipient via Gmail SMTP. Gated behind the USER's
OWN credentials (an app password), and only ever sends when the user triggers it to
a recipient they supply. Nothing is sent autonomously without a user action.

Configure (the user's own Gmail + an App Password, not their normal password):
    GMAIL_ADDRESS=you@gmail.com
    GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx   (Google Account -> Security -> App passwords)

An app password requires 2-Step Verification enabled on the account. We never store
or log the password; it is read from the environment at send time.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage


def configured() -> bool:
    return bool(os.environ.get("GMAIL_ADDRESS") and os.environ.get("GMAIL_APP_PASSWORD"))


def status() -> dict:
    if configured():
        return {"available": True, "sender": os.environ.get("GMAIL_ADDRESS")}
    return {
        "available": False,
        "reason": "Email sending isn't configured on the backend.",
        "how_to_enable": (
            "Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD (a Google App Password, created "
            "under Google Account → Security → App passwords, with 2-Step Verification "
            "on). Then the workflow can email the advisory."
        ),
    }


def send(recipient: str, subject: str, body: str) -> dict:
    """Send a plaintext advisory email. Returns {'sent': bool, ...}."""
    if not configured():
        return {"sent": False, "reason": "Email not configured (GMAIL_ADDRESS / GMAIL_APP_PASSWORD)."}
    if not recipient or "@" not in recipient:
        return {"sent": False, "reason": "A valid recipient email is required."}

    sender = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=30) as server:
            server.login(sender, password)
            server.send_message(msg)
        return {"sent": True, "recipient": recipient, "sender": sender}
    except Exception as e:
        return {"sent": False, "reason": f"SMTP send failed: {e}"}
