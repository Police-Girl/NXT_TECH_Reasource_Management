# Handles sending email notifications to staff
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path='.env')

MAIL_EMAIL = os.getenv('MAIL_EMAIL')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')

def send_notification(to_email, staff_name, request_type, status):
    # Build the email subject and body based on status
    status_word = "approved" if status == "approved" else "rejected"
    subject = f"NTL Resource Request {status_word.capitalize()}"

    body = f"""
Dear {staff_name},

Your resource request for {request_type.replace('_', ' ').title()} has been {status_word}.

{"Your request has been granted. The relevant team will follow up shortly." if status == "approved" else "Unfortunately your request was not approved at this time. Please contact the admin team for more information."}

This is an automated notification from the NTL Resource Management Portal.

Regards,
NTL Admin Team
    """.strip()

    # Set up the email
    msg = MIMEMultipart()
    msg['From'] = MAIL_EMAIL
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    # Send via Gmail SMTP
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(MAIL_EMAIL, MAIL_PASSWORD)
            server.sendmail(MAIL_EMAIL, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False