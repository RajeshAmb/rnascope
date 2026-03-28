"""Slack and email notification utilities."""

from __future__ import annotations

import logging
from typing import Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from rnascope.config import settings
from rnascope.infra.aws import send_email as ses_send_email

logger = logging.getLogger(__name__)


def send_slack(channel: str, message: str, attachments: list[str] | None = None) -> dict:
    """Send a message to a Slack channel."""
    if not settings.slack_bot_token:
        logger.warning("Slack bot token not configured, skipping notification")
        return {"status": "skipped", "reason": "no_token"}

    client = WebClient(token=settings.slack_bot_token)
    try:
        resp = client.chat_postMessage(channel=channel, text=message)
        logger.info("Slack message sent to %s", channel)
        return {"status": "sent", "ts": resp["ts"], "channel": channel}
    except SlackApiError as e:
        logger.error("Slack error: %s", e.response["error"])
        return {"status": "error", "error": e.response["error"]}


def send_email(recipient: str, subject: str, body: str) -> dict:
    """Send an email via AWS SES."""
    try:
        ses_send_email(recipient=recipient, subject=subject, body=body)
        logger.info("Email sent to %s", recipient)
        return {"status": "sent", "recipient": recipient}
    except Exception as e:
        logger.error("Email error: %s", e)
        return {"status": "error", "error": str(e)}


def notify_job_started(job_id: str, project: str, n_samples: int, channel: str, email: str) -> None:
    msg = (
        f"*RNAscope Pipeline Started*\n"
        f"Job: `{job_id}` | Project: {project}\n"
        f"Samples: {n_samples}\n"
        f"I'll notify you here when results are ready."
    )
    if channel:
        send_slack(channel, msg)
    if email:
        send_email(email, f"RNAscope: Pipeline started ({project})", msg)


def notify_job_completed(
    job_id: str,
    project: str,
    summary: str,
    report_url: str,
    channel: str,
    email: str,
) -> None:
    msg = (
        f"*RNAscope Pipeline Complete*\n"
        f"Job: `{job_id}` | Project: {project}\n\n"
        f"{summary}\n\n"
        f"Report: {report_url}"
    )
    if channel:
        send_slack(channel, msg)
    if email:
        send_email(
            email,
            f"RNAscope: Results ready ({project})",
            f"{summary}\n\nDownload report: {report_url}",
        )


def notify_job_error(job_id: str, project: str, error: str, channel: str, email: str) -> None:
    msg = (
        f"*RNAscope Pipeline Error*\n"
        f"Job: `{job_id}` | Project: {project}\n"
        f"Error: {error}\n"
        f"The pipeline will attempt to recover automatically."
    )
    if channel:
        send_slack(channel, msg)
    if email:
        send_email(email, f"RNAscope: Error in pipeline ({project})", msg)
