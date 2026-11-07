from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
import database, models, schemas, auth

router = APIRouter(prefix="/courses/{course_id}/ratings", tags=["Ratings"])


def _get_course_or_404(course_id: int, db: Session):
    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def _compute_display(course: models.Course, db: Session) -> dict:
    """
    Blended rating: (sum(user_ratings) + admin_rating) / (count(user_ratings) + 1)
    Treats admin_rating as one bootstrapped vote so it smooths out until real ratings accumulate.
    """
    result = (
        db.query(func.sum(models.CourseRating.rating), func.count(models.CourseRating.id))
        .filter(models.CourseRating.course_id == course.id)
        .first()
    )
    rating_sum, user_count = result
    rating_sum = rating_sum or 0
    user_count = user_count or 0

    admin_r = course.admin_rating or 0
    blended = (rating_sum + admin_r) / (user_count + 1)

    return {
        "display_rating": round(blended, 1),
        "display_learners_count": user_count + (course.admin_learners_count or 0)
    }


@router.get("/", response_model=schemas.RatingSummaryOut)
def get_rating(course_id: int, db: Session = Depends(database.get_db)):
    course = _get_course_or_404(course_id, db)
    return _compute_display(course, db)


@router.post("/", response_model=schemas.RatingSummaryOut, status_code=status.HTTP_201_CREATED)
def submit_rating(
    course_id: int,
    payload: schemas.UserRatingCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    course = _get_course_or_404(course_id, db)

    existing = (
        db.query(models.CourseRating)
        .filter(
            models.CourseRating.course_id == course_id,
            models.CourseRating.user_id == current_user.id,
        )
        .first()
    )
    if existing:
        existing.rating = payload.rating
    else:
        db.add(models.CourseRating(
            course_id=course_id,
            user_id=current_user.id,
            rating=payload.rating,
        ))

    db.commit()
    return _compute_display(course, db)


@router.put("/admin", response_model=schemas.RatingSummaryOut)
def set_admin_rating(
    course_id: int,
    payload: schemas.AdminRatingUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    """Admin sets a manual rating/learner count (used before real ratings accumulate)."""
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    course = _get_course_or_404(course_id, db)

    if payload.admin_rating is not None:
        course.admin_rating = payload.admin_rating
    if payload.admin_learners_count is not None:
        course.admin_learners_count = payload.admin_learners_count

    db.commit()
    db.refresh(course)
    return _compute_display(course, db)
