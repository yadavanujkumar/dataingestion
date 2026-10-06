from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error


def get_notification_log_dir() -> Path:
    out = Path.cwd() / "outputs" / "notifications"
    out.mkdir(parents=True, exist_ok=True)
    return out


def send_slack_message(
    text: str,
    blocks: Optional[List[Dict[str, Any]]] = None,
    channel: str = "#marketing-reports",
    webhook_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sends or records a Slack notification.
    If SLACK_WEBHOOK_URL is configured (or webhook_url provided), dispatches via HTTP.
    Always records in outputs/notifications/slack_history.jsonl for audit.
    """
    url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
    payload = {
        "channel": channel,
        "text": text,
        "blocks": blocks or [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    sent = False
    error = None

    if url:
        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                sent = resp.status == 200
        except Exception as e:
            error = str(e)
            sent = False
    else:
        # Mock mode when webhook is not set
        sent = True

    # Audit log
    log_dir = get_notification_log_dir()
    history_file = log_dir / "slack_history.jsonl"
    record = {
        "id": str(uuid.uuid4()),
        "channel": channel,
        "text": text,
        "sent": sent,
        "mock": not bool(url),
        "error": error,
        "timestamp": payload["timestamp"],
    }
    with open(history_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    return record


def create_email_draft(
    brand_id: str,
    subject: str,
    body_text: str,
    recipients: Optional[List[str]] = None,
    attachments: Optional[List[str | Path]] = None,
) -> Dict[str, Any]:
    """
    Creates an email draft file for review.
    Draft creation only — never auto-sent to external clients without human verification.
    """
    drafts_dir = Path.cwd() / "outputs" / "email_drafts" / brand_id.capitalize()
    drafts_dir.mkdir(parents=True, exist_ok=True)

    draft_id = f"draft_{uuid.uuid4().hex[:8]}"
    eml_file = drafts_dir / f"{draft_id}.eml"
    json_file = drafts_dir / f"{draft_id}.json"

    recipients_list = recipients or ["marketing-ops@howl.internal"]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "reports-bot@howl.internal"
    msg["To"] = ", ".join(recipients_list)
    msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    msg.set_content(body_text)

    # Attach file references if present and exist
    attached_files = []
    if attachments:
        for att in attachments:
            att_path = Path(att)
            if att_path.is_file():
                with open(att_path, "rb") as f:
                    file_data = f.read()
                msg.add_attachment(
                    file_data,
                    maintype="application",
                    subtype="octet-stream",
                    filename=att_path.name,
                )
                attached_files.append(str(att_path.resolve()))

    # Save .eml
    with open(eml_file, "wb") as f:
        f.write(msg.as_bytes())

    # Save summary metadata .json
    meta = {
        "draft_id": draft_id,
        "brand_id": brand_id,
        "subject": subject,
        "to": recipients_list,
        "eml_path": str(eml_file.resolve()),
        "attachments": attached_files,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    return meta


def notify_review_gate_blocked(
    brand_id: str,
    run_id: str,
    deliverable: str,
    period: str,
    gate_status: Dict[str, Any],
) -> Dict[str, Any]:
    """Send alert when review gate pauses a run."""
    unres_share_pct = gate_status.get("unresolved_share", 0.0) * 100
    threshold_pct = gate_status.get("blocking_share", 0.02) * 100
    count = gate_status.get("unresolved_count", 0)

    text = (
        f"[PAUSED] Run `{run_id}` for {brand_id.upper()} ({deliverable}, {period}) "
        f"paused at Review Gate. {count} items unresolved ({unres_share_pct:.2f}% impact, "
        f"blocking threshold: {threshold_pct:.2f}%). Action needed: `python cli.py review-list --brand {brand_id}`"
    )

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Run Paused: Review Gate Blocked*\n{text}",
            },
        }
    ]

    return send_slack_message(text=text, blocks=blocks, channel="#data-reviewers")


def notify_run_completed(
    brand_id: str,
    run_id: str,
    deliverable: str,
    period: str,
    delivered_files: List[Dict[str, str]],
) -> Dict[str, Any]:
    """Alert and prepare draft when run finishes successfully."""
    files_str = "\n".join([f"- {f.get('file_name', '')}: {f.get('delivered_to', '')}" for f in delivered_files])
    slack_text = (
        f"[COMPLETED] Deliverable `{deliverable}` for {brand_id.upper()} ({period}) generated successfully! "
        f"(Run: `{run_id}`). Output files:\n{files_str}"
    )

    slack_res = send_slack_message(text=slack_text, channel="#marketing-reports")

    # Also create internal email draft for account manager review
    email_body = (
        f"Hello Team,\n\n"
        f"The {deliverable} report for {brand_id.capitalize()} ({period}) has been generated and is ready for QA.\n\n"
        f"Run ID: {run_id}\n"
        f"Delivered Files:\n{files_str}\n\n"
        f"Please inspect the outputs before sharing with the client.\n\n"
        f"-- HOWL Platform Automations"
    )
    file_paths = [f.get("delivered_to") for f in delivered_files if f.get("delivered_to")]
    email_res = create_email_draft(
        brand_id=brand_id,
        subject=f"[{brand_id.upper()}] {deliverable} Ready for Review ({period})",
        body_text=email_body,
        attachments=file_paths,
    )

    return {"slack": slack_res, "email_draft": email_res}


def notify_run_failed(
    brand_id: str,
    run_id: str,
    deliverable: str,
    period: str,
    error_message: str,
) -> Dict[str, Any]:
    """Send alert on run failure."""
    text = (
        f"[ERROR] Run `{run_id}` for {brand_id.upper()} ({deliverable}, {period}) FAILED!\n"
        f"Error details: {error_message}"
    )
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Run Failed*\n{text}",
            },
        }
    ]
    return send_slack_message(text=text, blocks=blocks, channel="#ops-alerts")
