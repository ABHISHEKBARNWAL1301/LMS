from pydantic import BaseModel
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from schemas import TranscodeCallback
import database, models
from fastapi import Depends

router = APIRouter(
    tags=["Webhooks"]
)





@router.post("/transcoding/webhook")
def transcoding_webhook(
    payload: TranscodeCallback, 
    db: Session = Depends(database.get_db)
):

    lesson = db.query(models.Lesson).filter(
        models.Lesson.id == payload.lesson_id,
        models.Lesson.course_id == payload.course_id
    ).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")

    if payload.status == "COMPLETED":
        lesson.processing_status = "COMPLETED"
        lesson.video_url = payload.master_key 
        lesson.thumbnail_url = payload.thumbnail_url
        lesson.duration = payload.duration
        lesson.transcoded_urls = {q: f"v{q}/prog_index.m3u8" for q in payload.qualities}
    elif payload.status == "FAILED":
        lesson.processing_status = "FAILED"

    db.commit()
    print(f"Transcoding {payload.status} for course {lesson.course_id} and lesson {lesson.id}")
    return {"message": f"Transcoding {payload.status} for course {lesson.course_id} and lesson {lesson.id}"}