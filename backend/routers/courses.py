import shutil
import boto3
import uuid
import os
import httpx
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    File,
    UploadFile,
    BackgroundTasks,
    Form,
)
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
import database, models, schemas, auth
import json
from schemas import CourseUpdate

router = APIRouter(prefix="/courses", tags=["Courses"])


def _attach_rating(course: models.Course, db: Session):
    """Blended rating: (sum(user_ratings) + admin_rating) / (count(user_ratings) + 1)"""
    rating_sum, user_count = (
        db.query(func.sum(models.CourseRating.rating), func.count(models.CourseRating.id))
        .filter(models.CourseRating.course_id == course.id)
        .first()
    )
    rating_sum = rating_sum or 0
    user_count = user_count or 0
    admin_r = course.admin_rating or 0

    course.display_rating = round((rating_sum + admin_r) / (user_count + 1), 1)
    course.display_learners_count = user_count + (course.admin_learners_count or 0)
    return course


def _delete_r2_prefix(prefix: str, label: str = ""):
    """Delete all R2 objects under a given key prefix. Safe to call even when no objects exist."""
    try:
        s3_client = boto3.client(
            "s3",
            endpoint_url=os.getenv("R2_ENDPOINT_URL"),
            aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
            region_name="auto",
        )
        bucket = os.getenv("R2_BUCKET_NAME", "evolveu-content")
        paginator = s3_client.get_paginator("list_objects_v2")

        objects = []
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj.get("Key", "")
                if key:  # never include empty keys
                    objects.append({"Key": key})

        if not objects:
            print(f"[r2] Nothing to delete for {label or prefix}")
            return

        # R2/S3 DeleteObjects accepts 1–1000 keys per request — batch if needed
        for i in range(0, len(objects), 1000):
            batch = objects[i : i + 1000]
            s3_client.delete_objects(Bucket=bucket, Delete={"Objects": batch})
            print(f"[r2] Deleted {len(batch)} object(s) for {label or prefix}")

    except Exception as e:
        print(f"[r2] Failed to delete R2 files for {label or prefix}: {e}")


# GET ALL COURSES
@router.get("/", response_model=schemas.CoursesPage)
def get_courses(
    topic: Optional[str] = None,
    level: Optional[str] = None,
    page: int = 1,
    page_size: int = 12,
    db: Session = Depends(database.get_db),
):
    query = db.query(models.Course)
    if topic:
        query = query.filter(models.Course.topic == topic)
    if level:
        query = query.filter(models.Course.level == level)
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    for course in items:
        _attach_rating(course, db)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


# GET UPCOMING LIVE MASTERCLASSES
@router.get("/live", response_model=List[schemas.CourseOut])
def get_live_courses(db: Session = Depends(database.get_db)):
    from datetime import datetime

    now = datetime.utcnow().isoformat()
    courses = (
        db.query(models.Course)
        .filter(models.Course.is_live_class == True, models.Course.start_time >= now)
        .order_by(models.Course.start_time.asc())
        .all()
    )
    return courses


# GET SINGLE COURSE
@router.get("/{course_id}", response_model=schemas.CourseOut)
def get_course(course_id: int, db: Session = Depends(database.get_db)):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    _attach_rating(course, db)
    return course


# DELETE SINGLE COURSE
@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(
    course_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):

    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to delete courses")

    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    db.delete(course)
    db.commit()

    # Delete R2 bucket files for the entire course prefix
    _delete_r2_prefix(f"courses/course-{course_id}", label=f"course {course_id}")


# Helper function used by create_course and update_course
async def upload_image(file: UploadFile, course_id: int):
    try:
        R2_BUCKET = os.getenv("R2_BUCKET_NAME", "evolveu-content")
        # Use course_id in the path
        Prefix = f"courses/course-{course_id}/{file.filename}"

        s3_client = boto3.client(
            "s3",
            endpoint_url=os.getenv("R2_ENDPOINT_URL"),
            aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
            region_name="auto",
        )

        # Reset file pointer if it was read previously
        await file.seek(0)

        # boto3 upload_fileobj requires a file-like object
        s3_client.upload_fileobj(file.file, R2_BUCKET, Prefix)
        image_url = f"{os.getenv('R2_MEDIA_URL')}/{Prefix}"
        return image_url
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# CREATE COURSE
@router.post("/", response_model=schemas.CourseOut)
async def create_course(
    title: str = Form(..., min_length=3, max_length=200),
    description: Optional[str] = Form(None, max_length=2000),
    selling_price: float = Form(0.0, ge=0),
    original_price: float = Form(0.0, ge=0),
    lessons_count: int = Form(0),
    quiz_count: int = Form(0),
    topic: Optional[str] = Form(None),
    level: Optional[str] = Form(None),
    is_live_class: bool = Form(False),
    start_time: Optional[str] = Form(None),
    duration: Optional[int] = Form(None),
    instructor_name: Optional[str] = Form(None),
    assigned_instructor_id: Optional[int] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to create courses")

    # Validate prices
    if original_price < selling_price:
        raise HTTPException(
            status_code=400, detail="Original price cannot be less than selling price"
        )

    # Validate instructor if provided
    if assigned_instructor_id is not None:
        instructor = db.query(models.User).filter(
            models.User.id == assigned_instructor_id,
            models.User.role == models.UserRole.INSTRUCTOR,
        ).first()
        if not instructor:
            raise HTTPException(status_code=404, detail="Instructor not found")

    # Create course first
    new_course = models.Course(
        title=title,
        description=description,
        selling_price=selling_price,
        original_price=original_price,
        instructor_id=current_user.id,
        image_url=None,
        topic=topic,
        level=level,
        is_live_class=is_live_class,
        start_time=start_time,
        duration=duration,
        instructor_name=instructor_name,
        assigned_instructor_id=assigned_instructor_id,
    )

    db.add(new_course)
    db.commit()
    db.refresh(new_course)

    if file:
        image_url = await upload_image(file, new_course.id)
        new_course.image_url = image_url
        db.commit()
        db.refresh(new_course)

    return new_course


# UPDATE COURSE
@router.put("/{course_id}", response_model=schemas.CourseOut)
async def update_course(
    course_id: int,
    title: str = Form(..., min_length=3, max_length=200),
    description: Optional[str] = Form(None, max_length=2000),
    selling_price: float = Form(0.0, ge=0),
    original_price: float = Form(0.0, ge=0),
    lessons_count: int = Form(0),
    quiz_count: int = Form(0),
    topic: Optional[str] = Form(None),
    level: Optional[str] = Form(None),
    duration: Optional[int] = Form(None),
    is_live_class: Optional[bool] = Form(None),
    start_time: Optional[str] = Form(None),
    instructor_name: Optional[str] = Form(None),
    assigned_instructor_id: Optional[int] = Form(None),
    image_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to update courses")

    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    # Validate prices
    if original_price < selling_price:
        raise HTTPException(
            status_code=400, detail="Original price cannot be less than selling price"
        )

    # Update basic fields
    course.title = title
    course.description = description
    course.selling_price = selling_price
    course.original_price = original_price
    course.topic = topic
    course.level = level
    if duration is not None:
        course.duration = duration
    if is_live_class is not None:
        course.is_live_class = is_live_class
        # Ensure that if it's not a live class, we clean up the schedule
        if is_live_class is False:
            course.start_time = None
            # We might want to keep duration/instructor if valid for normal courses?
            # But let's assume they are specific to live class context in this UI.
            # However, duration is used for generic courses too in some contexts (e.g. "20 hours").
            # But for now, let's just handle start_time cleanup.

    if start_time is not None:
        # Only update start_time if we didn't just clear it via is_live_class=False
        # But if is_live_class=False, we set it to None above.
        # If start_time comes as "", we set it to None.
        # If start_time comes as "Value", we set it.
        # If we just set it to None because is_live_class=False, we should respect that?
        # Form data might send is_live_class=False AND start_time="".
        # So setting it to None here is consistent.
        course.start_time = start_time if start_time != "" else None

    if instructor_name is not None:
        course.instructor_name = instructor_name if instructor_name != "" else None

    if assigned_instructor_id is not None:
        instructor = db.query(models.User).filter(
            models.User.id == assigned_instructor_id,
            models.User.role == models.UserRole.INSTRUCTOR,
        ).first()
        if not instructor:
            raise HTTPException(status_code=404, detail="Instructor not found")
        course.assigned_instructor_id = assigned_instructor_id

    # Handle Image: File upload takes precedence over image_url
    if file:
        uploaded_url = await upload_image(file, course_id)
        course.image_url = uploaded_url
    elif image_url is not None:
        # If no file uploaded, but image_url is provided (could be same or different)
        course.image_url = image_url

    db.commit()
    db.refresh(course)
    return course


# ENROLL IN COURSE
@router.post("/{course_id}/enroll", response_model=schemas.EnrollmentOut)
async def enroll_course(
    course_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    # Check if course exists
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    # Paid courses must be enrolled through the payment flow (POST /payment/verify).
    # Only free courses (selling_price == 0) or admin users may use this endpoint directly.
    if (course.selling_price or 0) > 0 and current_user.role != models.UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Payment required. Please complete your purchase through checkout.",
        )

    # Check if already enrolled
    enrollment = (
        db.query(models.Enrollment)
        .filter(
            models.Enrollment.user_id == current_user.id,
            models.Enrollment.course_id == course_id,
        )
        .first()
    )

    if enrollment:
        raise HTTPException(status_code=400, detail="Already enrolled")

    new_enrollment = models.Enrollment(user_id=current_user.id, course_id=course_id)
    db.add(new_enrollment)
    db.commit()
    db.refresh(new_enrollment)
    return new_enrollment


# MANUAL PROGRESS OVERRIDE — admin only (M1 fix)
# Students cannot self-report arbitrary completion values.
# Lesson-level completion tracking will drive student progress in a future update.
@router.post("/{course_id}/progress", response_model=schemas.EnrollmentOut)
def update_progress(
    course_id: int,
    progress: float,
    user_id: int,  # which student's enrollment to update
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    # M1: block regular users from self-setting arbitrary progress
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Progress is updated automatically through lesson completion.",
        )

    if not (0.0 <= progress <= 100.0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Progress must be between 0 and 100.",
        )

    enrollment = (
        db.query(models.Enrollment)
        .filter(
            models.Enrollment.user_id == user_id,
            models.Enrollment.course_id == course_id,
        )
        .first()
    )

    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    enrollment.progress = progress
    if progress >= 100:
        enrollment.completed = True
        enrollment.progress = 100.0

    db.commit()
    db.refresh(enrollment)
    return enrollment


# MARK A LESSON COMPLETE — any enrolled student can call this
@router.post("/{course_id}/lessons/{lesson_id}/complete", response_model=schemas.EnrollmentOut)
def mark_lesson_complete(
    course_id: int,
    lesson_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    enrollment = (
        db.query(models.Enrollment)
        .filter(
            models.Enrollment.user_id == current_user.id,
            models.Enrollment.course_id == course_id,
        )
        .first()
    )
    if not enrollment:
        raise HTTPException(status_code=404, detail="Not enrolled in this course")

    # Ensure the lesson actually belongs to this course
    lesson = (
        db.query(models.Lesson)
        .filter(models.Lesson.id == lesson_id, models.Lesson.course_id == course_id)
        .first()
    )
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found in this course")

    # Idempotent — add only if not already present
    completed = list(enrollment.completed_lesson_ids or [])
    if lesson_id not in completed:
        completed.append(lesson_id)
        enrollment.completed_lesson_ids = completed

        # Recalculate progress from ratio of completed lessons to total lessons
        total_lessons = (
            db.query(models.Lesson)
            .filter(models.Lesson.course_id == course_id)
            .count()
        )
        if total_lessons > 0:
            enrollment.progress = round(len(completed) / total_lessons * 100, 1)
        if enrollment.progress >= 100:
            enrollment.progress = 100.0
            enrollment.completed = True

        db.commit()
        db.refresh(enrollment)

    return enrollment


async def trigger_transcoding_service(course_id: int, lesson_id: int, Prefix: str):
    # Call Transcoding Service
    TRANSCODING_SERVICE_URL = os.getenv("TRANSCODING_SERVICE_URL")

    payload = {
        "Prefix": Prefix,
        "lesson_id": lesson_id,
        "course_id": course_id,
    }

    async with httpx.AsyncClient() as client:
        try:
            await client.post(f"{TRANSCODING_SERVICE_URL}/transcode", json=payload)
        except Exception as e:
            print(f"Failed to trigger transcoding for lesson {lesson_id}: {e}")


# UPLOAD VIDEO
@router.post("/upload-video")
async def upload_video(
    background_tasks: BackgroundTasks,
    course_id: int = Form(...),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    file: UploadFile = File(...),
    type: str = Form("video"),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role not in [models.UserRole.ADMIN, models.UserRole.INSTRUCTOR]:
        raise HTTPException(status_code=403, detail="Not authorized")

    # 1. Validation
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="No Match Found for the course id")

    try:
        # 2. Create Lesson Entry First
        new_lesson = models.Lesson(
            course_id=course_id,
            title=title,
            description=description,
            type=schemas.LessonTypeEnum.VIDEO,
            processing_status="PROCESSING",
            order=len(course.lessons) + 1,
        )
        db.add(new_lesson)
        db.commit()
        db.refresh(new_lesson)

        lesson_id = new_lesson.id

        # 3. Upload Original video to R2
        s3_client = boto3.client(
            "s3",
            endpoint_url=os.getenv("R2_ENDPOINT_URL"),
            aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
            region_name="auto",
        )

        if file and course_id and lesson_id:
            R2_BUCKET = os.getenv("R2_BUCKET_NAME", "evolveu-content")
            Prefix = f"courses/course-{course_id}/lesson-{lesson_id}/{file.filename}"
            s3_client.upload_fileobj(file.file, R2_BUCKET, Prefix)
            original_video_url = f"{os.getenv('R2_MEDIA_URL')}/{Prefix}"
            new_lesson.video_url = original_video_url
            db.commit()

            # 4. Trigger Transcoding in Background
            background_tasks.add_task(
                trigger_transcoding_service,
                course_id=course_id,
                lesson_id=lesson_id,
                Prefix=Prefix,
            )

        return {
            "status": "success",
            "message": "Original video uploaded. Transcoding in progress.",
            "lesson_id": lesson_id,
        }
    except Exception as e:
        db.delete(new_lesson)
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))
