#!/usr/bin/env python
import sys
import warnings

from email_assistant.agents import EmailAssistant
from email_assistant.core import fetch_emails, format_email

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")


def run():
    try:
        emails = fetch_emails()
    except Exception as e:
        print(f"Error fetching emails: {e}")
        return

    if not emails:
        print("No emails fetched.")
        return

    for index, email in enumerate(emails, start=1):
        print(f"\n{'='*60}")
        print(f"Processing email {index}/{len(emails)}")
        print(f"From: {email['sender']}")
        print(f"Subject: {email['subject']}")
        print(f"{'='*60}")

        inputs = {"email_content": format_email(email)}

        try:
            EmailAssistant().crew().kickoff(inputs=inputs)
        except Exception as e:
            print(f"Error processing email: {e}")


def train():
    emails = fetch_emails()
    inputs = {"email_content": format_email(emails[0])}
    try:
        EmailAssistant().crew().train(
            n_iterations=int(sys.argv[1]),
            filename=sys.argv[2],
            inputs=inputs,
        )
    except Exception as e:
        raise Exception(f"An error occurred while training the crew: {e}")


def replay():
    try:
        EmailAssistant().crew().replay(task_id=sys.argv[1])
    except Exception as e:
        raise Exception(f"An error occurred while replaying the crew: {e}")


def test():
    emails = fetch_emails()
    inputs = {"email_content": format_email(emails[0])}
    try:
        EmailAssistant().crew().test(
            n_iterations=int(sys.argv[1]),
            eval_llm=sys.argv[2],
            inputs=inputs,
        )
    except Exception as e:
        raise Exception(f"An error occurred while testing the crew: {e}")


def run_with_trigger():
    import json

    if len(sys.argv) < 2:
        raise Exception(
            "No trigger payload provided. Please provide JSON payload as argument."
        )

    try:
        trigger_payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        raise Exception("Invalid JSON payload provided as argument")

    inputs = {
        "email_content": trigger_payload.get("email_content", ""),
    }

    try:
        return EmailAssistant().crew().kickoff(inputs=inputs)
    except Exception as e:
        raise Exception(f"An error occurred while running the crew with trigger: {e}")
