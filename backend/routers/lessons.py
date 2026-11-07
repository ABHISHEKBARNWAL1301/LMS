from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
import database, models, schemas, auth
import os
import boto3

router = APIRouter(prefix="/lessons", tags=["Lessons"])


def _delete_r2_prefix(prefix: str, label: str = ""):
    """Delete all R2 objects under a given key prefix. Safe even when no objects exist."""
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
                if key:
                    objects.append({"Key": key})

        if not objects:
            print(f"[r2] Nothing to delete for {label or prefix}")
            return

        for i in range(0, len(objects), 1000):
            batch = objects[i : i + 1000]
            s3_client.delete_objects(Bucket=bucket, Delete={"Objects": batch})
            print(f"[r2] Deleted {len(batch)} object(s) for {label or prefix}")

    except Exception as e:
        print(f"[r2] Failed to delete R2 files for {label or prefix}: {e}")


# Create a lesson(Quiz)
@router.post("/{course_id}", response_model=schemas.LessonOut)
def create_lesson(
    course_id: int,
    lesson: schemas.LessonCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to create lessons")

    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    lesson_data = lesson.dict()
    # Filter out fields not in the Lesson model
    if "content" in lesson_data:
        del lesson_data["content"]

    new_lesson = models.Lesson(**lesson_data, course_id=course_id)

    # Check for video processing metadata
    if new_lesson.video_url and "uploads/" in new_lesson.video_url:
        import os
        import json

        # Extract filename from URL
        try:
            filename = new_lesson.video_url.split("/")[-1]
            unique_id = filename.split(".")[0]
            metadata_path = f"uploads/{unique_id}_metadata.json"

            if os.path.exists(metadata_path):
                with open(metadata_path, "r") as f:
                    metadata = json.load(f)
                    if metadata.get("status") == "COMPLETED":
                        new_lesson.transcoded_urls = json.dumps(metadata.get("urls"))
                        new_lesson.processing_status = "COMPLETED"
                        # Update to R2 URL
                        if "original" in metadata["urls"]:
                            new_lesson.video_url = metadata["urls"]["original"]
        except Exception as e:
            print(f"Error checking video metadata: {e}")

    db.add(new_lesson)
    db.commit()
    db.refresh(new_lesson)
    return new_lesson


@router.put("/{course_id}/reorder")
def reorder_lessons(
    course_id: int,
    reorder_data: schemas.LessonReorder,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to reorder lessons")

    # Verify course exists
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    # Fetch all lessons for this course
    lessons = db.query(models.Lesson).filter(models.Lesson.course_id == course_id).all()
    lesson_map = {lesson.id: lesson for lesson in lessons}

    # Verify all IDs belongs to the course
    for lesson_id in reorder_data.lesson_ids:
        if lesson_id not in lesson_map:
            raise HTTPException(
                status_code=400,
                detail=f"Lesson ID {lesson_id} does not belong to course {course_id}",
            )

    # Update order
    for index, lesson_id in enumerate(reorder_data.lesson_ids):
        lesson = lesson_map[lesson_id]
        lesson.order = index

    db.commit()
    return {"message": "Lessons reordered successfully"}


@router.put("/{lesson_id}", response_model=schemas.LessonOut)
def update_lesson(
    course_id: int,
    lesson_id: int,
    lesson_update: schemas.LessonCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to update lessons")

    lesson = (
        db.query(models.Lesson)
        .filter(
            models.Lesson.id == lesson_id,
            models.Lesson.course_id == course_id,
        )
        .first()
    )
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    for key, value in lesson_update.dict().items():
        setattr(lesson, key, value)

    # Check for video processing metadata upon update
    if (
        lesson.video_url
        and "uploads/" in lesson.video_url
        and lesson.processing_status != "COMPLETED"
    ):
        import os
        import json

        try:
            filename = lesson.video_url.split("/")[-1]
            unique_id = filename.split(".")[0]
            metadata_path = f"uploads/{unique_id}_metadata.json"

            if os.path.exists(metadata_path):
                with open(metadata_path, "r") as f:
                    metadata = json.load(f)
                    if metadata.get("status") == "COMPLETED":
                        lesson.transcoded_urls = json.dumps(metadata.get("urls"))
                        lesson.processing_status = "COMPLETED"
                        # Update to R2 URL
                        if "original" in metadata["urls"]:
                            lesson.video_url = metadata["urls"]["original"]
        except Exception as e:
            print(f"Error checking video metadata in update: {e}")

    db.commit()
    db.refresh(lesson)
    return lesson


@router.delete("/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lesson(
    course_id: int,
    lesson_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to delete lessons")
    print(course_id, lesson_id)
    lesson = (
        db.query(models.Lesson)
        .filter(
            models.Lesson.id == lesson_id,
            models.Lesson.course_id == course_id,
        )
        .first()
    )
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    db.delete(lesson)
    db.commit()

    # Delete R2 bucket files for this lesson
    _delete_r2_prefix(
        f"courses/course-{course_id}/lesson-{lesson_id}",
        label=f"lesson {lesson_id}",
    )

    return {"message": "Lesson deleted successfully", "status_code": 204}


@router.post("/{lesson_id}/questions", response_model=schemas.QuestionOut)
def create_question(
    lesson_id: int,
    question: schemas.QuestionCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized to add questions")

    lesson = db.query(models.Lesson).filter(models.Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    if lesson.type != schemas.LessonTypeEnum.QUIZ:
        raise HTTPException(
            status_code=400, detail="Cannot add questions to non-quiz lesson"
        )

    new_question = models.Question(**question.dict(), lesson_id=lesson_id)
    db.add(new_question)
    db.commit()
    db.refresh(new_question)
    return new_question


# Transcoding Integration
import httpx
import os
import json

TRANSCODING_SERVICE_URL = os.getenv("TRANSCODING_SERVICE_URL", "http://localhost:8001")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


@router.post("/{lesson_id}/transcode")
async def trigger_transcoding(
    lesson_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    lesson = db.query(models.Lesson).filter(models.Lesson.id == lesson_id).first()
    if not lesson or not lesson.video_url:
        raise HTTPException(status_code=404, detail="Lesson or video not found")

    # Determine input key from video_url
    # Assuming video_url might be a full URL or just a key
    # For R2 implementation, we need the object key.
    # If it's a full URL `https://..../key`, extract key.
    input_key = lesson.video_url
    if lesson.video_url.startswith("http"):
        # Very naive extraction, assumes standard structure or user provided logic
        # If it's the R2 public URL, we might need to parse.
        # But per seed_r2.py, keys are "courses/..."
        # Let's try to find "courses/" in the string for now, or just send it as is if logic allows.
        # For robustness, let's assume video_url IS the key or relative path if it doesn't look like a clear URL.
        # Check design.txt: "2. UPLOAD PHASE ... FastAPI --[stream to R2]--> R2/original"
        pass

    payload = {
        "video_id": f"lesson_{lesson.id}",
        "input_key": input_key,
        "callback_url": f"{API_BASE_URL}/lessons/callback",
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{TRANSCODING_SERVICE_URL}/transcode", json=payload
            )
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=500, detail=f"Transcoding service error: {resp.text}"
                )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to connect to transcoding service: {e}"
        )

    lesson.processing_status = "PROCESSING"
    db.commit()
    return {"message": "Transcoding started", "status": "PROCESSING"}


from pydantic import BaseModel


class TranscodeCallback(BaseModel):
    video_id: str
    status: str
    master_playlist_key: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration: Optional[int] = None
    qualities: Optional[List[str]] = None
    error: Optional[str] = None


@router.post("/callback")
def transcoding_callback(
    data: TranscodeCallback, db: Session = Depends(database.get_db)
):
    # video_id format: "lesson_{id}"
    try:
        lesson_id = int(data.video_id.split("_")[1])
    except:
        raise HTTPException(status_code=400, detail="Invalid video_id format")

    lesson = db.query(models.Lesson).filter(models.Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    if data.status == "COMPLETED":
        lesson.processing_status = "COMPLETED"
        urls = {"master": data.master_playlist_key}
        if data.qualities:
            urls["qualities"] = data.qualities
        lesson.transcoded_urls = json.dumps(urls)

        if data.thumbnail_url:
            lesson.thumbnail_url = data.thumbnail_url
        if data.duration:
            lesson.duration = data.duration
    else:
        lesson.processing_status = "FAILED"
        print(f"Transcoding failed for lesson {lesson_id}: {data.error}")

    db.commit()
    return {"status": "ok"}


@router.patch("/{course_id}/{lesson_id}/free", response_model=schemas.LessonOut)
def set_lesson_free(
    course_id: int,
    lesson_id: int,
    is_free: bool,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    """Admin toggles whether a lesson is freely accessible without enrollment."""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    lesson = db.query(models.Lesson).filter(
        models.Lesson.id == lesson_id,
        models.Lesson.course_id == course_id,
    ).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found in this course")

    lesson.is_free = is_free
    db.commit()
    db.refresh(lesson)
    return lesson


# GET SINGLE LESSON
@router.get("/{lesson_id}", response_model=schemas.LessonOut)
def get_lesson(lesson_id: int, db: Session = Depends(database.get_db)):
    lesson = db.query(models.Lesson).filter(models.Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return lesson


# DELETE QUESTION
@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(
    question_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(
            status_code=403, detail="Not authorized to delete questions"
        )

    question = (
        db.query(models.Question).filter(models.Question.id == question_id).first()
    )
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    db.delete(question)
    db.commit()
    return {"message": "Question deleted successfully"}
