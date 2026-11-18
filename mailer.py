# mailer.py - Gmail notification service.
# Sends an email to a staff member when their request is approved or rejected.

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
import os
import smtplib

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


def send_notification(to_email, staff_name, request_type, status):
    """Email the staff member. Returns True if sent, False if anything went wrong."""
    sender = os.getenv("MAIL_EMAIL")
    app_password = os.getenv("MAIL_PASSWORD")
    if not sender or not app_password or not to_email:
        return False

    word = "approved" if status == "approved" else "rejected"
    pretty_type = request_type.replace("_", " ").title()
    outcome = (
        "Your request has been granted. The relevant team will follow up shortly."
        if status == "approved"
        else "Unfortunately your request was not approved at this time. "
             "Please contact the admin team for more information."
    )
    body = (
        f"Dear {staff_name},\n\n"
        f"Your resource request for {pretty_type} has been {word}.\n\n"
        f"{outcome}\n\n"
        "This is an automated notification from the NTL Resource Management Portal.\n\n"
        "Regards,\nNTL Admin Team"
    )

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = f"NTL Resource Request {word.capitalize()}"
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, app_password)
            server.sendmail(sender, to_email, msg.as_string())
        return True
    except Exception as error:
        print(f"Email error: {error}")
        return False
