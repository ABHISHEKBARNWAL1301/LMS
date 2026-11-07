import os
import shutil
import uuid
import r2_utils
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from sqlalchemy.orm import Session
from typing import List
import database, models, schemas, auth

router = APIRouter(prefix="/gallery", tags=["Gallery"])


@router.get("/", response_model=List[schemas.GalleryVideoOut])
def get_gallery_videos(
    skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)
):
    videos = (
        db.query(models.GalleryVideo)
        .order_by(models.GalleryVideo.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return videos


@router.post("/", response_model=schemas.GalleryVideoOut)
def add_gallery_video(
    title: str = Form(...),
    category: str = Form("General"),
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(
            status_code=403, detail="Not authorized to add gallery videos"
        )

    # Save file locally temporarily
    upload_dir = "temp_uploads"
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)

    # Create a unique filename
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = f"{upload_dir}/{unique_filename}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Upload to R2
    object_name = f"website/gallery/videos/{unique_filename}"
    video_url = r2_utils.upload_file_to_r2(file_path, object_name)

    # Cleanup temp file
    if os.path.exists(file_path):
        os.remove(file_path)

    if not video_url:
        raise HTTPException(status_code=500, detail="Failed to upload video to storage")

    new_video = models.GalleryVideo(
        title=title,
        category=category,
        video_url=video_url,
        # thumbnail_url logic could be added here if we generate thumbnails
    )
    db.add(new_video)
    db.commit()
    db.refresh(new_video)
    return new_video


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_gallery_video(
    video_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(
            status_code=403, detail="Not authorized to delete gallery videos"
        )

    video = (
        db.query(models.GalleryVideo).filter(models.GalleryVideo.id == video_id).first()
    )
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    db.delete(video)
    db.commit()
    return None


# --- Gallery Images ---


@router.get("/images", response_model=List[schemas.GalleryImageOut])
def get_gallery_images(
    skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)
):
    images = (
        db.query(models.GalleryImage)
        .order_by(models.GalleryImage.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return images


@router.post("/images", response_model=schemas.GalleryImageOut)
def add_gallery_image(
    file: UploadFile = File(...),
    caption: str = Form(None),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(
            status_code=403, detail="Not authorized to add gallery images"
        )

    # Save file locally temporarily
    upload_dir = "temp_uploads"
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)

    # Create a unique filename to avoid collisions
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = f"{upload_dir}/{unique_filename}"

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Upload to R2
    # Requirement: upload to evolveu-content/website/gallery
    object_name = f"website/gallery/{unique_filename}"
    image_url = r2_utils.upload_file_to_r2(file_path, object_name)

    # Cleanup temp file
    if os.path.exists(file_path):
        os.remove(file_path)

    if not image_url:
        print(f"FAILED TO UPLOAD: {unique_filename}")
        raise HTTPException(status_code=500, detail="Failed to upload image to storage")

    new_image = models.GalleryImage(image_url=image_url, caption=caption)
    db.add(new_image)
    db.commit()
    db.refresh(new_image)
    print(f"SUCCESS: Added image {new_image.id} with URL {image_url}")
    return new_image


@router.delete("/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_gallery_image(
    image_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(database.get_db),
):
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(
            status_code=403, detail="Not authorized to delete gallery images"
        )

    image = (
        db.query(models.GalleryImage).filter(models.GalleryImage.id == image_id).first()
    )
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Optional: Delete the actual file from disk
    # For safety, skipping this to avoid accidental data loss issues, but strictly speaking we should.

    db.delete(image)
    db.commit()
    return None
