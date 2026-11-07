from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import database, models, schemas, auth
from datetime import datetime

router = APIRouter(prefix="/packages", tags=["Packages"])


def _require_admin(current_user: models.User):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Not authorized")


def _sync_courses(package: models.Package, course_ids: List[int], db: Session):
    """Replace package courses with the given course_ids."""
    # Validate all course IDs exist
    for cid in course_ids:
        if not db.query(models.Course).filter(models.Course.id == cid).first():
            raise HTTPException(status_code=404, detail=f"Course {cid} not found")

    # Remove existing and re-add
    db.query(models.PackageCourse).filter(models.PackageCourse.package_id == package.id).delete()
    for cid in course_ids:
        db.add(models.PackageCourse(package_id=package.id, course_id=cid))


@router.get("/", response_model=List[schemas.PackageOut])
def list_packages(
    active_only: bool = True,
    db: Session = Depends(database.get_db),
):
    query = db.query(models.Package)
    if active_only:
        query = query.filter(models.Package.is_active == True)
    return query.all()


@router.get("/{package_id}", response_model=schemas.PackageOut)
def get_package(package_id: int, db: Session = Depends(database.get_db)):
    package = db.query(models.Package).filter(models.Package.id == package_id).first()
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")
    return package


@router.post("/", response_model=schemas.PackageOut, status_code=status.HTTP_201_CREATED)
def create_package(
    payload: schemas.PackageCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    _require_admin(current_user)

    package = models.Package(
        name=payload.name,
        tag=payload.tag,
        price=payload.price,
        description=payload.description,
        features=payload.features,
        is_popular=payload.is_popular,
        created_at=datetime.utcnow().isoformat(),
    )
    db.add(package)
    db.commit()
    db.refresh(package)

    if payload.course_ids:
        _sync_courses(package, payload.course_ids, db)
        db.commit()
        db.refresh(package)

    return package


@router.put("/{package_id}", response_model=schemas.PackageOut)
def update_package(
    package_id: int,
    payload: schemas.PackageUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    _require_admin(current_user)

    package = db.query(models.Package).filter(models.Package.id == package_id).first()
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    for field, value in payload.model_dump(exclude_unset=True, exclude={"course_ids"}).items():
        setattr(package, field, value)

    if payload.course_ids is not None:
        _sync_courses(package, payload.course_ids, db)

    db.commit()
    db.refresh(package)
    return package


@router.delete("/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_package(
    package_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    _require_admin(current_user)

    package = db.query(models.Package).filter(models.Package.id == package_id).first()
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    db.delete(package)
    db.commit()
