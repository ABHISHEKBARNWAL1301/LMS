from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session, selectinload
import database
import models
import schemas 
import auth
from typing import List
import random
import string
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

router = APIRouter(
    prefix="/users",
    tags=["Users"]
)

SUPPORT_MAIL_SENDER = os.getenv("SUPPORT_MAIL_SENDER")
SUPPORT_MAIL_SENDER_PASSWORD = os.getenv("SUPPORT_MAIL_SENDER_PASSWORD")


def _send_verification_email(to_email: str, code: str, name: str):
    subject = "Your EvolveU Email Verification Code"
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #16a34a;">Verify Your Email</h2>
        <p>Hi {name},</p>
        <p>Use the code below to verify your email address on EvolveU:</p>
        <div style="text-align:center; margin: 24px 0;">
            <span style="font-size: 36px; font-weight: bold; letter-spacing: 10px;
                         background: #f0fdf4; padding: 16px 24px; border-radius: 8px;
                         border: 2px dashed #16a34a; color: #15803d;">
                {code}
            </span>
        </div>
        <p style="color:#666; font-size:13px;">This code expires in 15 minutes. If you didn't request this, you can ignore this email.</p>
        <p style="color:#666; font-size:12px;">— Team EvolveU</p>
    </body>
    </html>
    """

    if not SUPPORT_MAIL_SENDER or not SUPPORT_MAIL_SENDER_PASSWORD:
        print(f"[MOCK EMAIL] Verification code for {to_email}: {code}")
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = SUPPORT_MAIL_SENDER
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html"))
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SUPPORT_MAIL_SENDER, SUPPORT_MAIL_SENDER_PASSWORD)
        server.sendmail(SUPPORT_MAIL_SENDER, to_email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"Failed to send verification email: {e}")


@router.get("/me", response_model=schemas.UserOut)
def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@router.patch("/me", response_model=schemas.UserOut)
def update_profile(
    update: schemas.UserUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Update profile fields. Email changes now go through request-email-change (H4)."""
    if update.full_name is not None:
        current_user.full_name = update.full_name

    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/me/request-email-change", response_model=schemas.UserOut)
def request_email_change(
    payload: schemas.EmailChangeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    H4 fix: Stage a new email as pending_email and send verification code to it.
    The actual User.email is only updated after /confirm-email-change succeeds.
    """
    new_email = payload.new_email.lower().strip()

    # Reject if this email already belongs to a different confirmed account
    conflict = (
        db.query(models.User)
        .filter(
            models.User.email == new_email,
            models.User.id != current_user.id,
        )
        .first()
    )
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists.",
        )

    # Stage the new email — don't touch User.email yet
    current_user.pending_email = new_email
    current_user.is_email_verified = False

    # Invalidate any old pending codes for this address
    db.query(models.VerificationCode).filter(
        models.VerificationCode.contact == new_email,
        models.VerificationCode.type == models.VerificationType.EMAIL,
        models.VerificationCode.is_used == False,
    ).update({"is_used": True})

    # Generate fresh 6-digit code
    code = "".join(random.choices(string.digits, k=6))
    expires_at = (datetime.utcnow() + timedelta(minutes=15)).isoformat()

    db.add(
        models.VerificationCode(
            contact=new_email,
            code=code,
            type=models.VerificationType.EMAIL,
            expires_at=expires_at,
            is_used=False,
            created_at=datetime.utcnow().isoformat(),
        )
    )
    db.commit()
    db.refresh(current_user)

    background_tasks.add_task(
        _send_verification_email,
        new_email,
        code,
        current_user.full_name or "there",
    )

    return current_user


@router.post("/me/confirm-email-change", response_model=schemas.UserOut)
def confirm_email_change(
    request: schemas.EmailVerifyRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    H4 fix: Verify the OTP sent to pending_email then move it to User.email.
    Until this succeeds, the old User.email stays intact.
    """
    if not current_user.pending_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No email change in progress. Use /request-email-change first.",
        )

    record = (
        db.query(models.VerificationCode)
        .filter(
            models.VerificationCode.contact == current_user.pending_email,
            models.VerificationCode.code == request.code.strip(),
            models.VerificationCode.type == models.VerificationType.EMAIL,
            models.VerificationCode.is_used == False,
        )
        .order_by(models.VerificationCode.id.desc())
        .first()
    )

    if not record:
        raise HTTPException(status_code=400, detail="Invalid verification code.")

    if datetime.utcnow() > datetime.fromisoformat(record.expires_at):
        raise HTTPException(status_code=400, detail="Code has expired. Please request a new one.")

    # Commit the email change now that ownership is proven
    record.is_used = True
    current_user.email = current_user.pending_email
    current_user.pending_email = None
    current_user.is_email_verified = True
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/me/send-email-verification")
def send_email_verification(
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    if not current_user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No email address on file. Add an email first.",
        )
    if current_user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already verified.",
        )

    # Invalidate any previous unused codes for this email
    db.query(models.VerificationCode).filter(
        models.VerificationCode.contact == current_user.email,
        models.VerificationCode.type == models.VerificationType.EMAIL,
        models.VerificationCode.is_used == False,
    ).update({"is_used": True})
    db.commit()

    # Generate a fresh 6-digit code
    code = "".join(random.choices(string.digits, k=6))
    expires_at = (datetime.utcnow() + timedelta(minutes=15)).isoformat()

    db_code = models.VerificationCode(
        contact=current_user.email,
        code=code,
        type=models.VerificationType.EMAIL,
        expires_at=expires_at,
        is_used=False,
        created_at=datetime.utcnow().isoformat(),
    )
    db.add(db_code)
    db.commit()

    background_tasks.add_task(
        _send_verification_email,
        current_user.email,
        code,
        current_user.full_name or "there",
    )

    return {"message": f"Verification code sent to {current_user.email}"}


@router.post("/me/verify-email", response_model=schemas.UserOut)
def verify_email(
    request: schemas.EmailVerifyRequest,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    if not current_user.email:
        raise HTTPException(status_code=400, detail="No email address on file.")
    if current_user.is_email_verified:
        raise HTTPException(status_code=400, detail="Email is already verified.")

    record = (
        db.query(models.VerificationCode)
        .filter(
            models.VerificationCode.contact == current_user.email,
            models.VerificationCode.code == request.code.strip(),
            models.VerificationCode.type == models.VerificationType.EMAIL,
            models.VerificationCode.is_used == False,
        )
        .order_by(models.VerificationCode.id.desc())
        .first()
    )

    if not record:
        raise HTTPException(status_code=400, detail="Invalid verification code.")

    # Check expiry
    if datetime.utcnow() > datetime.fromisoformat(record.expires_at):
        raise HTTPException(status_code=400, detail="Code has expired. Please request a new one.")

    # Mark code used and user verified
    record.is_used = True
    current_user.is_email_verified = True
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/public", response_model=List[schemas.UserPublic])
def read_public_students(skip: int = 0, limit: int = 3, db: Session = Depends(database.get_db)):
    users = db.query(models.User).filter(models.User.role == models.UserRole.STUDENT).offset(skip).limit(limit).all()
    return users


@router.get("/me/enrollments", response_model=List[schemas.EnrollmentOut])
def read_my_enrollments(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    enrollments = (
        db.query(models.Enrollment)
        .options(selectinload(models.Enrollment.course))
        .filter(models.Enrollment.user_id == current_user.id)
        .all()
    )
    return enrollments
