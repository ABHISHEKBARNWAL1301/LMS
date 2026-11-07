import database
import models
import schemas
import auth
import httpx
import os
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from dotenv import load_dotenv

router = APIRouter(prefix="/auth", tags=["Authentication"])


load_dotenv()

SUPPORT_MAIL_SENDER = os.getenv("SUPPORT_MAIL_SENDER")
SUPPORT_MAIL_SENDER_PASSWORD = os.getenv("SUPPORT_MAIL_SENDER_PASSWORD")
NOTIFY_EMAIL = "info@evolveu.in"

MSG91_AUTH_TOKEN = os.getenv("MSG91_AUTH_TOKEN")

if not MSG91_AUTH_TOKEN:
    print("WARNING: MSG91_AUTH_TOKEN not found in environment variables!")


async def verify_msg91_access_token(access_token: str) -> dict:
    """
    Verify the JWT access token returned by MSG91 widget after OTP verification.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.msg91.com/api/v5/widget/verifyAccessToken",
                headers={
                    "content-type": "application/json",
                    "authkey": MSG91_AUTH_TOKEN,
                },
                json={"access-token": access_token},
            )

        print(f"[msg91] verifyAccessToken status={resp.status_code} body={resp.text}")
        data = resp.json()

        # Success path
        if resp.status_code == 200 and data.get("type") != "error":
            return data

        raise HTTPException(
            status_code=401,
            detail=f"MSG91 token invalid: {data.get('message', 'Unknown error')}",
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[msg91] verifyAccessToken request failed ({e}) — falling back to local JWT decode")
        raise HTTPException(
            status_code=401,
            detail=f"MSG91 token invalid: {e}",
        )


def _send_new_student_notification(full_name: str, phone: str, email: str | None):
    """Fire-and-forget: email info@evolveu.in when a new student registers."""
    if not SUPPORT_MAIL_SENDER or not SUPPORT_MAIL_SENDER_PASSWORD:
        print(f"[NEW STUDENT] {full_name} | {phone} | {email or 'no email'} (SMTP not configured)")
        return

    subject = f"New Student Registered: {full_name}"
    registered_at = datetime.utcnow().strftime("%d %b %Y, %H:%M UTC")

    body = f"""\
        New student registration on EvolveU!

        Name    : {full_name}
        Phone   : {phone}
        Email   : {email or '—'}
        Joined  : {registered_at}

        Log in to the admin dashboard to view full details.
        """

    try:
        msg = MIMEMultipart()
        msg["From"] = SUPPORT_MAIL_SENDER
        msg["To"] = NOTIFY_EMAIL
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SUPPORT_MAIL_SENDER, SUPPORT_MAIL_SENDER_PASSWORD)
        server.sendmail(SUPPORT_MAIL_SENDER, NOTIFY_EMAIL, msg.as_string())
        server.quit()
        print(f"[NEW STUDENT] Notification sent for {full_name} ({phone})")
    except Exception as exc:
        print(f"[NEW STUDENT] Failed to send notification email: {exc}")


@router.post("/check-phone")
def check_phone_exists(
    request: schemas.CheckPhoneRequest, db: Session = Depends(database.get_db)
):
    """Check if a phone number is already registered"""
    user = (
        db.query(models.User)
        .filter(models.User.phone_number == request.phone_number)
        .first()
    )
    return {"exists": user is not None}


@router.post("/check-email")
def check_email_exists(
    request: schemas.CheckEmailRequest, db: Session = Depends(database.get_db)
):
    """Check if an email is already registered"""
    user = db.query(models.User).filter(func.lower(models.User.email) == request.email.lower()).first()
    return {"exists": user is not None}


@router.post("/register", response_model=schemas.Token)
async def register(background_tasks: BackgroundTasks, user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    """
    Register a new user.
    Requires a valid MSG91 access_token proving phone OTP was completed (H3).
    Role is always STUDENT — callers cannot self-assign ADMIN (H1).
    Email is optional and stored unverified.
    Returns JWT token for auto-login.
    """
    # H3: Verify the MSG91 access token before trusting the phone number
    await verify_msg91_access_token(user.msg91_access_token)

    # Check phone uniqueness
    db_user_phone = (
        db.query(models.User)
        .filter(models.User.phone_number == user.phone_number)
        .first()
    )
    if db_user_phone:
        raise HTTPException(status_code=400, detail="Phone number already registered")

    # Check email uniqueness if provided
    if user.email:
        db_user_email = (
            db.query(models.User).filter(func.lower(models.User.email) == user.email.lower()).first()
        )
        if db_user_email:
            raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = auth.get_password_hash(user.password)
    new_user = models.User(
        email=user.email.lower() if user.email else None,
        phone_number=user.phone_number,
        hashed_password=hashed_password,
        full_name=user.full_name,
        role=models.UserRole.STUDENT,  # H1: always STUDENT, never trust client-supplied role
        is_phone_verified=True,
        is_email_verified=False,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Notify info@evolveu.in about the new student (runs in background, non-blocking)
    background_tasks.add_task(
        _send_new_student_notification,
        new_user.full_name,
        new_user.phone_number,
        new_user.email,
    )

    # Return JWT for auto-login
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": str(new_user.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login", response_model=schemas.Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(database.get_db),
):
    # Try to find user by email (case-insensitive)
    user = db.query(models.User).filter(func.lower(models.User.email) == form_data.username.lower()).first()
    if not user:
        # Check if it's a phone number
        user = (
            db.query(models.User)
            .filter(models.User.phone_number == form_data.username)
            .first()
        )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found. Please register first",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.hashed_password or not auth.verify_password(
        form_data.password, user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login-otp", response_model=schemas.Token)
async def login_with_otp(
    body: schemas.OTPLoginRequest, db: Session = Depends(database.get_db)
):
    """
    Login with phone OTP.
    1. Takes MSG91 access_token (JWT from verifyOtp response) as proof of verification
    2. Uses phone_number from request body (MSG91 token doesn't contain phone)
    3. Finds EXISTING user by phone - if not found, returns error (no auto-create)
    4. Returns app JWT token
    """
    # Validate that the MSG91 token is a legitimate JWT (proof that OTP was verified)
    await verify_msg91_access_token(body.access_token)

    user_phone = body.phone_number.strip()

    if not user_phone:
        raise HTTPException(
            status_code=400, detail="Phone number is required"
        )

    # Find existing user - NO auto-creation
    user = db.query(models.User).filter(models.User.phone_number == user_phone).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="No account found with this phone number. Please register first.",
        )

    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


def _send_reset_email(email: str, token: str):
    """Sends a password reset link to the user's email."""
    sender = os.getenv("SUPPORT_MAIL_SENDER")
    password = os.getenv("SUPPORT_MAIL_SENDER_PASSWORD")
    frontend_url = os.getenv("FRONTEND_URL", "https://evolveu.in")
    reset_link = f"{frontend_url}/reset-password?token={token}"

    subject = "Reset Your EvolveU Password"
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto;">
        <div style="background: #0b1a3a; padding: 24px 32px; border-radius: 12px 12px 0 0; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 24px;">EvolveU</h1>
        </div>
        <div style="background: #ffffff; padding: 32px; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 12px 12px;">
            <h2 style="color: #0b1a3a; margin-top: 0;">Reset Your Password</h2>
            <p>We received a request to reset the password for your EvolveU account associated with <strong>{email}</strong>.</p>
            <p>Click the button below to set a new password. This link will expire in <strong>30 minutes</strong>.</p>
            <div style="text-align: center; margin: 32px 0;">
                <a href="{reset_link}"
                   style="background: #f97316; color: white; padding: 14px 32px; border-radius: 8px;
                          text-decoration: none; font-weight: bold; font-size: 16px; display: inline-block;">
                    Reset Password
                </a>
            </div>
            <p style="color: #6b7280; font-size: 13px;">
                If you didn't request a password reset, you can safely ignore this email.
            </p>
            <p style="color: #6b7280; font-size: 13px;">
                Or copy this link:<br/>
                <a href="{reset_link}" style="color: #3274d1; word-break: break-all;">{reset_link}</a>
            </p>
            <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;" />
            <p style="color: #9ca3af; font-size: 12px; text-align: center;">— Team EvolveU</p>
        </div>
    </body>
    </html>
    """

    if not sender or not password:
        print(f"[forgot-password] SMTP not configured. Reset link for {email}: {reset_link}")
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = sender
        msg["To"] = email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html"))
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, email, msg.as_string())
        server.quit()
        print(f"[forgot-password] Reset email sent to {email}")
    except smtplib.SMTPAuthenticationError as e:
        print(f"[forgot-password] SMTP Auth failed: {e}")
    except Exception as e:
        print(f"[forgot-password] Failed to send reset email: {e}")


@router.post("/forgot-password")
def forgot_password(
    request: schemas.ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
):
    """
    Generate a reset token and email a reset link.
    Always returns 200 to prevent email enumeration attacks.
    """
    user = db.query(models.User).filter(func.lower(models.User.email) == request.email.lower()).first()

    if user:
        # Invalidate any existing unused reset tokens for this email
        existing = (
            db.query(models.VerificationCode)
            .filter(
                models.VerificationCode.contact == request.email,
                models.VerificationCode.type == models.VerificationType.EMAIL,
                models.VerificationCode.is_used == False,
            )
            .all()
        )
        for code in existing:
            code.is_used = True
        db.commit()

        # Secure token, expires in 30 min
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.utcnow() + timedelta(minutes=30)).isoformat()

        reset_code = models.VerificationCode(
            contact=request.email,
            code=token,
            type=models.VerificationType.EMAIL,
            expires_at=expires_at,
            is_used=False,
        )
        db.add(reset_code)
        db.commit()

        background_tasks.add_task(_send_reset_email, request.email, token)

    return {"status": "success", "message": "If this email is registered, a reset link has been sent."}


@router.post("/reset-password")
def reset_password(
    request: schemas.ResetPasswordRequest,
    db: Session = Depends(database.get_db),
):
    """Validate the reset token and update the user's password."""
    now = datetime.utcnow().isoformat()

    reset_code = (
        db.query(models.VerificationCode)
        .filter(
            models.VerificationCode.code == request.token,
            models.VerificationCode.type == models.VerificationType.EMAIL,
            models.VerificationCode.is_used == False,
        )
        .first()
    )

    if not reset_code:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link. Please request a new one.")

    if reset_code.expires_at < now:
        reset_code.is_used = True
        db.commit()
        raise HTTPException(status_code=400, detail="This reset link has expired. Please request a new one.")

    user = db.query(models.User).filter(models.User.email == reset_code.contact).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.hashed_password = auth.get_password_hash(request.new_password)
    reset_code.is_used = True
    db.commit()

    return {"status": "success", "message": "Password updated successfully. You can now log in."}

