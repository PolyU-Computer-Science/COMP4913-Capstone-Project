"""Built-in default mailbox seed.

Seeds one mailbox from the developer's Gmail configuration plus a
study/work-oriented topic & field template, so a fresh database is usable
without manual re-entry. Seed-once: never runs when any mailbox exists.

The IMAP/SMTP password is seeded from ``EMAIL_PASSWORD`` (the env fallback
configured in ``.env``) when available; otherwise it must be entered in the
UI once.
"""

from __future__ import annotations

import os
from typing import Any

def _env_password() -> str:
    return os.environ.get("EMAIL_PASSWORD", "").strip()


MAILBOX_SEED: dict[str, Any] = {
    "name": "Ken Cheng",
    "address": "chiwacheng1231@gmail.com",
    "purpose": "Academic and work mailbox",
    "status": "active",
    "imap_host": "imap.gmail.com",
    "imap_port": 993,
    "imap_security": "ssl",
    "imap_folder": "INBOX",
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "smtp_security": "starttls",
    "max_emails": 50,
    "auto_process": True,
    "generate_drafts": True,
    "use_knowledge": False,
    "instructions": "",
}

# Topics for academic + work email triage.
TOPIC_SEEDS: list[dict[str, str]] = [
    {
        "name": "Course Administration",
        "description": "Course enrollment, add/drop deadlines, class schedules, and academic regulations.",
    },
    {
        "name": "Assignment & Coursework",
        "description": "Assignment submissions, deadline extensions, grading enquiries, and feedback requests.",
    },
    {
        "name": "Career & Internship",
        "description": "Job applications, internship offers, interview invitations, and recruitment communications.",
    },
    {
        "name": "Meetings & Events",
        "description": "Meeting invitations, seminar announcements, event RSVPs, and calendar coordination.",
    },
    {
        "name": "Project Collaboration",
        "description": "Group project coordination, supervisor/advisor communications, and research discussions.",
    },
    {
        "name": "IT & Account Support",
        "description": "Account access, password resets, university IT services, and software licences.",
    },
    {
        "name": "Administrative & Finance",
        "description": "Tuition fees, scholarships, transcripts, certificates, and other administrative requests.",
    },
]

# Fields the classifier should try to extract alongside the topic.
FIELD_SEEDS: list[dict[str, str]] = [
    {
        "name": "Deadline",
        "type": "text",
        "options": "",
        "prompt": "Any date or deadline mentioned that requires action, in ISO format (YYYY-MM-DD) if possible.",
    },
    {
        "name": "Action Required",
        "type": "select",
        "options": "reply,submit,pay,attend,decide,none",
        "prompt": "The primary action the sender expects from the recipient.",
    },
    {
        "name": "Organization",
        "type": "text",
        "options": "",
        "prompt": "The university, company, or organization the email is from.",
    },
]
