from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
import database, models, schemas, auth

router = APIRouter(prefix="/faqs", tags=["FAQs"])


def _next_order(db: Session, course_id: Optional[int]) -> int:
    """Returns max(order) + 1 for the given scope (general or course-specific)."""
    result = (
        db.query(func.max(models.FAQ.order))
        .filter(models.FAQ.course_id == course_id)
        .scalar()
    )
    return (result or 0) + 1


@router.get("/", response_model=List[schemas.FAQOut])
def get_faqs(
    course_id: Optional[int] = None,
    db: Session = Depends(database.get_db),
):
    """
    - ?course_id=5  → FAQs for that course
    - no param      → general FAQs (course_id IS NULL)
    """
    return (
        db.query(models.FAQ)
        .filter(models.FAQ.course_id == course_id)
        .order_by(models.FAQ.order)
        .all()
    )


@router.post("/", response_model=schemas.FAQOut, status_code=status.HTTP_201_CREATED)
def create_faq(
    payload: schemas.FAQCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    if payload.course_id is not None:
        course = db.query(models.Course).filter(models.Course.id == payload.course_id).first()
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

    faq = models.FAQ(
        question=payload.question,
        answer=payload.answer,
        course_id=payload.course_id,
        order=_next_order(db, payload.course_id),
    )
    db.add(faq)
    db.commit()
    db.refresh(faq)
    return faq


@router.put("/reorder", response_model=List[schemas.FAQOut])
def reorder_faqs(
    payload: schemas.FAQReorder,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    """
    Pass an ordered list of FAQ IDs → they get assigned order 0, 1, 2, ...
    All IDs must belong to the same scope (general or same course).
    """
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    faqs = db.query(models.FAQ).filter(models.FAQ.id.in_(payload.faq_ids)).all()
    if len(faqs) != len(payload.faq_ids):
        raise HTTPException(status_code=404, detail="One or more FAQ IDs not found")

    faq_map = {faq.id: faq for faq in faqs}
    for i, faq_id in enumerate(payload.faq_ids):
        faq_map[faq_id].order = i

    db.commit()
    return [faq_map[faq_id] for faq_id in payload.faq_ids]


@router.put("/{faq_id}", response_model=schemas.FAQOut)
def update_faq(
    faq_id: int,
    payload: schemas.FAQUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    faq = db.query(models.FAQ).filter(models.FAQ.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(faq, field, value)

    db.commit()
    db.refresh(faq)
    return faq


@router.delete("/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_faq(
    faq_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")

    faq = db.query(models.FAQ).filter(models.FAQ.id == faq_id).first()
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")

    db.delete(faq)
    db.commit()
