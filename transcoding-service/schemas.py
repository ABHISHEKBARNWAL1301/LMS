from pydantic import BaseModel
from typing import Optional


class TranscodeRequest(BaseModel):
    Prefix: str
    lesson_id: Optional[int] = -1
    course_id: Optional[int] = -1
