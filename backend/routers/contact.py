from fastapi import APIRouter, BackgroundTasks, HTTPException, status
import schemas
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

router = APIRouter(prefix="/contact", tags=["contact"])

MAIL_TO = "info@evolveu.in"


def send_email_background(name: str, email: str, phone: str):
    """
    Sends an email in the background.
    Reads SMTP credentials fresh from env each time so load_dotenv() in main.py
    is guaranteed to have run before these are used.
    If SMTP creds are missing, logs to console.
    """
    sender = os.getenv("SUPPORT_MAIL_SENDER")
    password = os.getenv("SUPPORT_MAIL_SENDER_PASSWORD")

    subject = f"New Counselling Request from {name}"
    body = f"""
    New Counselling Request Received:

    Name: {name}
    Email: {email}
    Phone: {phone}

    Please reach out to them soon.
    """

    if not sender or not password:
        print("--------------------------------------------------")
        print("WARNING: SMTP credentials not set. Logging email instead.")
        print(f"  SUPPORT_MAIL_SENDER set: {bool(sender)}")
        print(f"  SUPPORT_MAIL_SENDER_PASSWORD set: {bool(password)}")
        print(f"  To: {MAIL_TO}")
        print(f"  Subject: {subject}")
        print("--------------------------------------------------")
        return

    try:
        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = MAIL_TO
        msg["Subject"] = subject
        msg["Reply-To"] = email  # replies go back to the user

        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, MAIL_TO, msg.as_string())
        server.quit()
        print(f"[contact] Email sent successfully to {MAIL_TO}")
    except smtplib.SMTPAuthenticationError as e:
        print(f"[contact] SMTP Authentication failed — check Gmail App Password: {e}")
    except smtplib.SMTPException as e:
        print(f"[contact] SMTP error: {e}")
    except Exception as e:
        print(f"[contact] Unexpected error sending email: {e}")


@router.post("/counselling")
def request_counselling(
    request: schemas.CounsellingRequest, background_tasks: BackgroundTasks
):
    """
    Receives counselling request and queues an email notification.
    """
    background_tasks.add_task(
        send_email_background, request.name, request.email, request.phone
    )
    return {"status": "success", "message": "Request received"}
