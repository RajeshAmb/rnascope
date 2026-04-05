"""Send the AGENT_WORKFLOW.md via email using Gmail SMTP.

Usage:
  python send_email.py --password YOUR_GMAIL_APP_PASSWORD

You need a Gmail App Password (not your regular password).
Get one at: https://myaccount.google.com/apppasswords
"""

import argparse
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path


def send(password: str):
    sender = "rajeshreddyambavaram37@gmail.com"
    recipient = "rajeshreddyambavaram37@gmail.com"

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = "RNAscope Agent Workflow - Complete Technical Guide"

    body = """\
Hi Rajesh,

Here is the complete RNAscope Agent Workflow document.

This covers:
- System architecture (3 Claude agents + AWS infrastructure)
- User upload flow (step-by-step)
- Orchestrator agentic loop (how Claude drives the pipeline)
- All 14 pipeline steps in detail
- Species routing (25 organisms: human, plants, microbes)
- Frontend chart rendering
- Chat agent Q&A system
- Error handling & checkpoint recovery
- End-to-end data flow diagram

GitHub repo: https://github.com/RajeshAmb/rnascope
Gist (readable): https://gist.github.com/RajeshAmb/8019ac06cb72e820292a88c72dc9e892

The workflow doc is also attached as a file.

Best,
RNAscope Agent
"""
    msg.attach(MIMEText(body, "plain"))

    # Attach the file
    filepath = Path(__file__).parent / "AGENT_WORKFLOW.md"
    with open(filepath, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename=AGENT_WORKFLOW.md")
        msg.attach(part)

    # Send via Gmail SMTP
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.send_message(msg)
        print(f"Email sent to {recipient}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--password", required=True, help="Gmail App Password")
    args = parser.parse_args()
    send(args.password)
