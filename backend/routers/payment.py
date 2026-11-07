from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from database import get_db
from models import User, Order, Course, Enrollment, Coupon, Package, PackageCourse, UserPackage
from schemas import OrderCreate, OrderOut, PaymentVerification
from auth import get_current_user
import razorpay
import os
from typing import List
import json
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

router = APIRouter(prefix="/payment", tags=["payment"])

# Initialize Razorpay client
# Make sure to set these in your .env file
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    print("WARNING: Razorpay keys not found in environment variables")

client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

ADMIN_MAIL = "info@evolveu.in"


def _smtp_send(to: str, subject: str, body: str, is_html: bool = False):
    """
    Shared helper — reads credentials fresh each call (after load_dotenv in main.py).
    Sends via Gmail SMTP. Logs to console if creds are missing.
    """
    sender = os.getenv("SUPPORT_MAIL_SENDER")
    password = os.getenv("SUPPORT_MAIL_SENDER_PASSWORD")

    if not sender or not password:
        print("--------------------------------------------------")
        print(f"[MOCK EMAIL] To: {to} | Subject: {subject}")
        print(f"  SUPPORT_MAIL_SENDER set: {bool(sender)}")
        print(f"  SUPPORT_MAIL_SENDER_PASSWORD set: {bool(password)}")
        print("--------------------------------------------------")
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html" if is_html else "plain"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, to, msg.as_string())
        server.quit()
        print(f"[payment] Email sent → {to} | {subject}")
    except smtplib.SMTPAuthenticationError as e:
        print(f"[payment] SMTP Auth failed — check Gmail App Password: {e}")
    except smtplib.SMTPException as e:
        print(f"[payment] SMTP error: {e}")
    except Exception as e:
        print(f"[payment] Unexpected email error: {e}")


def send_live_class_registration_email(user_email: str, user_name: str, course: Course):
    """Sends registration confirmation to the buyer."""
    start_time_display = course.start_time or "To be announced"
    instructor = course.instructor_name or "Our expert instructor"
    duration = f"{course.duration_minutes} minutes" if course.duration_minutes else "To be announced"

    subject = f"Registration Confirmed: {course.title}"
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #0b1a3a;">Registration Confirmed!</h2>
        <p>Hi {user_name},</p>
        <p>You have successfully registered for the upcoming live masterclass:</p>
        <div style="background: #f0f4ff; padding: 20px; border-radius: 10px; margin: 20px 0;">
            <h3 style="margin-top: 0; color: #0b1a3a;">{course.title}</h3>
            <p><strong>Date &amp; Time:</strong> {start_time_display}</p>
            <p><strong>Duration:</strong> {duration}</p>
            <p><strong>Instructor:</strong> {instructor}</p>
        </div>
        <p>You will be added to a WhatsApp group shortly where you'll get all the class details and updates.</p>
        <p>Thank you for choosing EvolveU!</p>
        <p style="color: #666; font-size: 12px;">— Team EvolveU</p>
    </body>
    </html>
    """
    _smtp_send(user_email, subject, body, is_html=True)


def send_admin_live_class_notification(user_email: str, user_name: str, user_phone: str, course: Course, amount: float):
    """Notifies info@evolveu.in when someone buys a live class."""
    start_time_display = course.start_time or "To be announced"
    subject = f"🎉 New Live Class Purchase — {course.title}"
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #0b1a3a;">New Live Class Purchase</h2>
        <p>Someone just enrolled in a live masterclass. Here are their details:</p>

        <div style="background: #fff7ed; border-left: 4px solid #f97316; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <h3 style="margin-top: 0; color: #0b1a3a;">Buyer Details</h3>
            <p><strong>Name:</strong> {user_name}</p>
            <p><strong>Email:</strong> {user_email}</p>
            <p><strong>Phone:</strong> {user_phone or "Not provided"}</p>
        </div>

        <div style="background: #f0f4ff; border-left: 4px solid #3274d1; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <h3 style="margin-top: 0; color: #0b1a3a;">Course Details</h3>
            <p><strong>Course:</strong> {course.title}</p>
            <p><strong>Amount Paid:</strong> ₹{amount}</p>
            <p><strong>Scheduled:</strong> {start_time_display}</p>
            <p><strong>Instructor:</strong> {course.instructor_name or "TBD"}</p>
        </div>

        <p>Please add them to the WhatsApp group and follow up as needed.</p>
        <p style="color: #666; font-size: 12px;">— EvolveU Automated Notification</p>
    </body>
    </html>
    """
    _smtp_send(ADMIN_MAIL, subject, body, is_html=True)


@router.post("/orders", response_model=OrderOut)
def create_order(
    order_data: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a Razorpay order for the given courses.
    """
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Payment gateway configuration missing",
        )

    # 1. Calculate total amount
    total_amount = 0
    course_ids_to_store = None
    package_id_to_store = None

    if order_data.package_id is not None:
        # --- Package purchase ---
        package = db.query(Package).filter(
            Package.id == order_data.package_id,
            Package.is_active == True,
        ).first()
        if not package:
            raise HTTPException(status_code=404, detail="Package not found")
        total_amount = package.price
        package_id_to_store = package.id
    else:
        # --- Individual course purchase ---
        courses_to_buy = []
        for course_id in order_data.course_ids:
            course = db.query(Course).filter(Course.id == course_id).first()
            if not course:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Course with id {course_id} not found",
                )
            courses_to_buy.append(course)
            if course.selling_price:
                total_amount += course.selling_price
        course_ids_to_store = order_data.course_ids

    # Apply coupon discount if provided
    discount_applied = 0.0
    if order_data.coupon_code:
        coupon = (
            db.query(Coupon)
            .filter(
                Coupon.code == order_data.coupon_code.strip().upper(),
                Coupon.is_active == True,
            )
            .first()
        )
        if coupon:
            discount_applied = total_amount * (coupon.discount_percent / 100)
            total_amount = max(0.0, total_amount - discount_applied)

    # Razorpay amount is in paise (1 INR = 100 paise)
    amount_in_paise = int(total_amount * 100)

    # 2. Create Razorpay Order
    try:
        data = {
            "amount": amount_in_paise,
            "currency": "INR",
            "receipt": f"receipt_{current_user.id}_{datetime.now().timestamp()}",
            "notes": {"user_id": current_user.id, "email": current_user.email},
        }
        razorpay_order = client.order.create(data=data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating Razorpay order: {str(e)}",
        )

    # 3. Save Order to Database
    db_order = Order(
        user_id=current_user.id,
        razorpay_order_id=razorpay_order["id"],
        amount=total_amount,
        status="CREATED",
        course_ids=json.dumps(course_ids_to_store) if course_ids_to_store else None,
        package_id=package_id_to_store,
    )
    db.add(db_order)
    db.commit()
    db.refresh(db_order)

    return db_order


@router.post("/verify")
def verify_payment(
    payment_data: PaymentVerification,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Verify the payment signature and enroll the user in courses.
    """
    # 1. Verify Signature
    try:
        params_dict = {
            "razorpay_order_id": payment_data.razorpay_order_id,
            "razorpay_payment_id": payment_data.razorpay_payment_id,
            "razorpay_signature": payment_data.razorpay_signature,
        }
        client.utility.verify_payment_signature(params_dict)
    except razorpay.errors.SignatureVerificationError:
        # Update order status to FAILED ? Or just raise error
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payment signature"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error verifying payment: {str(e)}",
        )

    # 2. Update Order Status
    order = (
        db.query(Order)
        .filter(Order.razorpay_order_id == payment_data.razorpay_order_id)
        .first()
    )
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )

    if order.status == "PAID":
        return {"status": "success", "message": "Payment already verified"}

    order.status = "PAID"
    db.commit()

    # 3. Resolve course_ids — from package or direct
    if order.package_id:
        package = db.query(Package).filter(Package.id == order.package_id).first()
        course_ids = [pc.course_id for pc in package.course_packages] if package else []
        # Record the package purchase
        already_owns = db.query(UserPackage).filter(
            UserPackage.user_id == current_user.id,
            UserPackage.package_id == order.package_id,
        ).first()
        if not already_owns:
            db.add(UserPackage(user_id=current_user.id, package_id=order.package_id))
    else:
        course_ids = json.loads(order.course_ids) if order.course_ids else []

    enrollments_created = 0
    for course_id in course_ids:
        # Check if already enrolled
        existing_enrollment = (
            db.query(Enrollment)
            .filter(
                Enrollment.user_id == current_user.id, Enrollment.course_id == course_id
            )
            .first()
        )

        if not existing_enrollment:
            new_enrollment = Enrollment(
                user_id=current_user.id,
                course_id=course_id,
                progress=0.0,
                completed=False,
            )
            db.add(new_enrollment)
            enrollments_created += 1

    db.commit()

    # Send emails for live class purchases
    for course_id in course_ids:
        course = db.query(Course).filter(Course.id == course_id).first()
        if course and course.is_live_class:
            # 1. Confirmation email → buyer
            background_tasks.add_task(
                send_live_class_registration_email,
                current_user.email,
                current_user.full_name or "Student",
                course,
            )
            # 2. Notification email → info@evolveu.in with buyer details
            background_tasks.add_task(
                send_admin_live_class_notification,
                current_user.email,
                current_user.full_name or "Student",
                getattr(current_user, "phone_number", None) or "",
                course,
                order.amount,
            )

    return {
        "status": "success",
        "message": "Payment verified and courses enrolled",
        "enrollments_created": enrollments_created,
    }
