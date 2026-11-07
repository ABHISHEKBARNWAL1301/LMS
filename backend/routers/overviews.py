from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
import database, models, schemas, auth

router = APIRouter(prefix="/courses/{course_id}/overview", tags=["Course Overview"])


def _next_order(db: Session, course_id: int) -> int:
    result = (
        db.query(func.max(models.CourseOverview.order))
        .filter(models.CourseOverview.course_id == course_id)
        .scalar()
    )
    return (result or 0) + 1


def _get_course_or_404(course_id: int, db: Session):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.get("/", response_model=List[schemas.CourseOverviewOut])
def get_overview(course_id: int, db: Session = Depends(database.get_db)):
    _get_course_or_404(course_id, db)
    return (
        db.query(models.CourseOverview)
        .filter(models.CourseOverview.course_id == course_id)
        .order_by(models.CourseOverview.order)
        .all()
    )


@router.post("/", response_model=schemas.CourseOverviewOut, status_code=status.HTTP_201_CREATED)
def create_overview(
    course_id: int,
    payload: schemas.CourseOverviewCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    _get_course_or_404(course_id, db)

    if payload.week_start >= payload.week_end:
        raise HTTPException(status_code=400, detail="week_start must be less than week_end")

    item = models.CourseOverview(
        course_id=course_id,
        week_start=payload.week_start,
        week_end=payload.week_end,
        title=payload.title,
        description=payload.description,
        order=_next_order(db, course_id),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/reorder", response_model=List[schemas.CourseOverviewOut])
def reorder_overview(
    course_id: int,
    payload: schemas.CourseOverviewReorder,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    items = (
        db.query(models.CourseOverview)
        .filter(models.CourseOverview.id.in_(payload.overview_ids))
        .all()
    )
    if len(items) != len(payload.overview_ids):
        raise HTTPException(status_code=404, detail="One or more overview IDs not found")

    item_map = {item.id: item for item in items}
    for i, oid in enumerate(payload.overview_ids):
        item_map[oid].order = i

    db.commit()
    return [item_map[oid] for oid in payload.overview_ids]


@router.put("/{overview_id}", response_model=schemas.CourseOverviewOut)
def update_overview(
    course_id: int,
    overview_id: int,
    payload: schemas.CourseOverviewUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    item = (
        db.query(models.CourseOverview)
        .filter(models.CourseOverview.id == overview_id, models.CourseOverview.course_id == course_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Overview item not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)

    db.commit()
    db.refresh(item)
    return item


@router.delete("/{overview_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_overview(
    course_id: int,
    overview_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    item = (
        db.query(models.CourseOverview)
        .filter(models.CourseOverview.id == overview_id, models.CourseOverview.course_id == course_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Overview item not found")

    db.delete(item)
    db.commit()
