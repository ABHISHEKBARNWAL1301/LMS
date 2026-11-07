import os
import boto3
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy.orm import Session
from database import get_db
import models, schemas
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(
    prefix="/blogs",
    tags=["blogs"],
)


class BlogBase(BaseModel):
    title: str
    description: Optional[str] = None
    content: str
    excerpt: Optional[str] = None
    author: str
    category: Optional[str] = None  # free text
    image_url: Optional[str] = None


class BlogCreate(BlogBase):
    pass


class BlogUpdate(BlogBase):
    pass


class Blog(BlogBase):
    id: int
    created_at: str

    class Config:
        from_attributes = True


async def upload_blog_image(file: UploadFile, blog_id: int):
    try:
        R2_BUCKET = os.getenv("R2_BUCKET_NAME", "evolveu-content")
        Prefix = f"blogs/blog-{blog_id}/{file.filename}"

        s3_client = boto3.client(
            "s3",
            endpoint_url=os.getenv("R2_ENDPOINT_URL"),
            aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
            region_name="auto",
        )

        await file.seek(0)
        s3_client.upload_fileobj(file.file, R2_BUCKET, Prefix)
        image_url = f"{os.getenv('R2_MEDIA_URL')}/{Prefix}"
        return image_url
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[Blog])
def get_blogs(
    category: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    query = db.query(models.BlogPost)
    if category:
        query = query.filter(models.BlogPost.category == category)
    return query.offset(skip).limit(limit).all()


@router.post("/", response_model=Blog)
async def create_blog(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    content: str = Form(...),
    excerpt: Optional[str] = Form(None),
    author: str = Form(...),
    category: Optional[str] = Form(None),
    image_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    new_blog = models.BlogPost(
        title=title,
        description=description,
        content=content,
        excerpt=excerpt,
        author=author,
        category=category,
        image_url=image_url,
    )
    db.add(new_blog)
    db.commit()
    db.refresh(new_blog)

    if file:
        uploaded_url = await upload_blog_image(file, new_blog.id)
        new_blog.image_url = uploaded_url
        db.commit()
        db.refresh(new_blog)

    return new_blog


@router.get("/{blog_id}", response_model=Blog)
def get_blog(blog_id: int, db: Session = Depends(get_db)):
    blog = db.query(models.BlogPost).filter(models.BlogPost.id == blog_id).first()
    if blog is None:
        raise HTTPException(status_code=404, detail="Blog not found")
    return blog


@router.put("/{blog_id}", response_model=Blog)
async def update_blog(
    blog_id: int,
    title: str = Form(...),
    description: Optional[str] = Form(None),
    content: str = Form(...),
    excerpt: Optional[str] = Form(None),
    author: str = Form(...),
    category: Optional[str] = Form(None),
    image_url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    db_blog = db.query(models.BlogPost).filter(models.BlogPost.id == blog_id).first()
    if db_blog is None:
        raise HTTPException(status_code=404, detail="Blog not found")

    db_blog.title = title
    db_blog.description = description
    db_blog.content = content
    db_blog.excerpt = excerpt
    db_blog.author = author
    db_blog.category = category

    if file:
        uploaded_url = await upload_blog_image(file, blog_id)
        db_blog.image_url = uploaded_url
    elif image_url is not None:
        db_blog.image_url = image_url

    db.commit()
    db.refresh(db_blog)
    return db_blog


@router.delete("/{blog_id}")
def delete_blog(blog_id: int, db: Session = Depends(get_db)):
    db_blog = db.query(models.BlogPost).filter(models.BlogPost.id == blog_id).first()
    if db_blog is None:
        raise HTTPException(status_code=404, detail="Blog not found")

    db.delete(db_blog)
    db.commit()
    return {"message": "Blog deleted successfully"}
