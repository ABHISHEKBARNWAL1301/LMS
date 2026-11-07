from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
import database, models, schemas, auth

router = APIRouter(prefix="/admin/instructors", tags=["Instructors"])


def _require_admin(current_user: models.User):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")


@router.get("/", response_model=List[schemas.InstructorOut])
def list_instructors(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    _require_admin(current_user)
    return (
        db.query(models.User)
        .filter(models.User.role == models.UserRole.INSTRUCTOR)
        .all()
    )


@router.post("/", response_model=schemas.InstructorOut, status_code=status.HTTP_201_CREATED)
def create_instructor(
    payload: schemas.InstructorCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    _require_admin(current_user)

    if db.query(models.User).filter(func.lower(models.User.email) == payload.email.lower()).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    if payload.phone_number and db.query(models.User).filter(
        models.User.phone_number == payload.phone_number
    ).first():
        raise HTTPException(status_code=400, detail="Phone number already registered")

    instructor = models.User(
        full_name=payload.full_name,
        email=payload.email.lower(),
        phone_number=payload.phone_number,
        hashed_password=auth.get_password_hash(payload.password),
        role=models.UserRole.INSTRUCTOR,
        bio=payload.bio,
        is_active=True,
        is_phone_verified=False,
        is_email_verified=False,
    )
    db.add(instructor)
    db.commit()
    db.refresh(instructor)
    return instructor


@router.put("/{instructor_id}", response_model=schemas.InstructorOut)
def update_instructor(
    instructor_id: int,
    payload: schemas.InstructorUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    _require_admin(current_user)

    instructor = db.query(models.User).filter(
        models.User.id == instructor_id,
        models.User.role == models.UserRole.INSTRUCTOR,
    ).first()
    if not instructor:
        raise HTTPException(status_code=404, detail="Instructor not found")

    if payload.email:
        conflict = db.query(models.User).filter(
            func.lower(models.User.email) == payload.email.lower(),
            models.User.id != instructor_id,
        ).first()
        if conflict:
            raise HTTPException(status_code=400, detail="Email already in use")
        instructor.email = payload.email.lower()

    if payload.full_name is not None:
        instructor.full_name = payload.full_name
    if payload.phone_number is not None:
        instructor.phone_number = payload.phone_number
    if payload.bio is not None:
        instructor.bio = payload.bio
    if payload.is_active is not None:
        instructor.is_active = payload.is_active

    db.commit()
    db.refresh(instructor)
    return instructor


@router.delete("/{instructor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_instructor(
    instructor_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    _require_admin(current_user)

    instructor = db.query(models.User).filter(
        models.User.id == instructor_id,
        models.User.role == models.UserRole.INSTRUCTOR,
    ).first()
    if not instructor:
        raise HTTPException(status_code=404, detail="Instructor not found")

    # Unassign from any courses before deleting
    db.query(models.Course).filter(
        models.Course.assigned_instructor_id == instructor_id
    ).update({"assigned_instructor_id": None})

    db.delete(instructor)
    db.commit()


@router.put("/{instructor_id}/assign-course/{course_id}", response_model=schemas.CourseOut)
def assign_instructor_to_course(
    instructor_id: int,
    course_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    _require_admin(current_user)

    instructor = db.query(models.User).filter(
        models.User.id == instructor_id,
        models.User.role == models.UserRole.INSTRUCTOR,
    ).first()
    if not instructor:
        raise HTTPException(status_code=404, detail="Instructor not found")

    course = db.query(models.Course).filter(models.Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    course.assigned_instructor_id = instructor_id
    db.commit()
    db.refresh(course)
    return course


@router.delete("/{instructor_id}/unassign-course/{course_id}", response_model=schemas.CourseOut)
def unassign_instructor_from_course(
    instructor_id: int,
    course_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    _require_admin(current_user)

    course = db.query(models.Course).filter(
        models.Course.id == course_id,
        models.Course.assigned_instructor_id == instructor_id,
    ).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found or instructor not assigned")

    course.assigned_instructor_id = None
    db.commit()
    db.refresh(course)
    return course
