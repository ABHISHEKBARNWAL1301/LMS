from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text, Float, Enum
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import relationship
from database import Base
import enum
from datetime import datetime
from schemas import LessonTypeEnum
from sqlalchemy import JSON


class UserRole(str, enum.Enum):
    STUDENT = "STUDENT"
    INSTRUCTOR = "INSTRUCTOR"
    ADMIN = "ADMIN"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    pending_email = Column(String, nullable=True)  # staged email — only committed after OTP verification (H4)
    hashed_password = Column(String)
    full_name = Column(String)
    phone_number = Column(String, unique=True, index=True, nullable=True)
    is_phone_verified = Column(Boolean, default=False)
    is_email_verified = Column(Boolean, default=False)
    role = Column(Enum(UserRole), default=UserRole.STUDENT)
    is_active = Column(Boolean, default=True)
    bio = Column(Text, nullable=True)

    enrollments = relationship("Enrollment", back_populates="student")
    courses_teaching = relationship("Course", foreign_keys="Course.instructor_id", back_populates="instructor")


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text)
    selling_price = Column(Float, default=0.0)  # This is the selling price
    original_price = Column(Float, nullable=True)  # Full price before discount
    image_url = Column(String, nullable=True)
    topic = Column(String, nullable=True)
    level = Column(String, nullable=True)
    is_live_class = Column(Boolean, default=False)
    start_time = Column(String, nullable=True)  # ISO format datetime for live classes
    duration = Column(Integer, nullable=True)  # Number of days
    instructor_name = Column(String, nullable=True)
    admin_rating = Column(Float, default=4.5)          # bootstrapped rating
    admin_learners_count = Column(Integer, default=10)  # bootstrapped learner count

    instructor_id = Column(Integer, ForeignKey("users.id"))
    assigned_instructor_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    instructor = relationship("User", foreign_keys=[instructor_id], back_populates="courses_teaching")
    assigned_instructor = relationship("User", foreign_keys=[assigned_instructor_id])
    enrollments = relationship("Enrollment", back_populates="course")
    lessons = relationship(
        "Lesson",
        back_populates="course",
        order_by="Lesson.order",
        cascade="all, delete-orphan",
    )
    faqs = relationship(
        "FAQ",
        back_populates="course",
        order_by="FAQ.order",
        cascade="all, delete-orphan",
    )
    overviews = relationship(
        "CourseOverview",
        back_populates="course",
        order_by="CourseOverview.order",
        cascade="all, delete-orphan",
    )
    ratings = relationship(
        "CourseRating",
        back_populates="course",
        cascade="all, delete-orphan",
    )


class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    course_id = Column(Integer, ForeignKey("courses.id"))
    progress = Column(Float, default=0.0)  # Percentage 0–100
    completed = Column(Boolean, default=False)
    enrolled_at = Column(String, default=datetime.utcnow().isoformat())
    completed_lesson_ids = Column(MutableList.as_mutable(JSON), default=list)  # tracks per-lesson completion

    student = relationship("User", back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")


class Lesson(Base):
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)

    title = Column(String, nullable=False)
    type = Column(
        Enum(LessonTypeEnum, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )

    order = Column(Integer, index=True, default=0, nullable=False)

    course = relationship("Course", back_populates="lessons")
    questions = relationship(
        "Question", back_populates="lesson", cascade="all, delete-orphan"
    )

    # --------------------
    # VIDEO-specific data
    # --------------------
    description = Column(Text, nullable=True)
    duration = Column(Integer, nullable=True)  # seconds
    video_url = Column(String, nullable=True)  # master.m3u8 (CDN / R2)
    transcoded_urls = Column(JSON, nullable=True)

    is_free = Column(Boolean, default=False)  # True = accessible without enrollment

    processing_status = Column(
        String, default="PENDING"
    )  # PENDING | PROCESSING | COMPLETED | FAILED

    thumbnail_url = Column(String, nullable=True)

    # --------------------
    # QUIZ-specific data
    # --------------------
    quiz_data = Column(JSON, nullable=True)
    # example:
    # {
    #   "mcqs": [
    #     {
    #       "question": "What is FastAPI?",
    #       "options": ["Framework", "Database", "Server"],
    #       "correct_option": 0
    #     }
    #   ]
    # }


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id"))
    text = Column(Text)
    options = Column(Text)  # JSON string of options
    correct_option_index = Column(Integer)

    lesson = relationship("Lesson", back_populates="questions")


class BlogPost(Base):
    __tablename__ = "blog_posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(Text, nullable=True)
    content = Column(Text)
    excerpt = Column(Text, nullable=True)
    author = Column(String)
    category = Column(String, nullable=True, index=True)  # free text, no enum
    image_url = Column(String, nullable=True)
    created_at = Column(String, default=datetime.utcnow().isoformat())


class GalleryVideo(Base):
    __tablename__ = "gallery_videos"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    video_url = Column(String)
    thumbnail_url = Column(String, nullable=True)
    category = Column(String, nullable=True, index=True)
    created_at = Column(String, default=datetime.utcnow().isoformat())


class GalleryImage(Base):
    __tablename__ = "gallery_images"

    id = Column(Integer, primary_key=True, index=True)
    image_url = Column(String)
    caption = Column(String, nullable=True)
    created_at = Column(String, default=datetime.utcnow().isoformat())


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    razorpay_order_id = Column(String, unique=True, index=True)
    amount = Column(Float)  # Amount in INR
    status = Column(String, default="CREATED")  # CREATED, PAID, FAILED
    course_ids = Column(JSON, nullable=True)   # set for individual course purchases
    package_id = Column(Integer, ForeignKey("packages.id", ondelete="SET NULL"), nullable=True)  # set for package purchases
    created_at = Column(String, default=datetime.utcnow().isoformat())

    user = relationship("User")


class Coupon(Base):
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)       # e.g. "FLASH10"
    discount_percent = Column(Float)                      # e.g. 10.0
    is_active = Column(Boolean, default=True)
    created_at = Column(String, default=datetime.utcnow().isoformat())


class SaleConfig(Base):
    """Singleton row (id=1) that controls the site-wide sale banner."""
    __tablename__ = "sale_config"

    id = Column(Integer, primary_key=True, index=True)   # always 1
    is_active = Column(Boolean, default=False)
    updated_at = Column(String, default=datetime.utcnow().isoformat())


class Package(Base):
    __tablename__ = "packages"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)          # e.g. "Beginner"
    tag = Column(String, nullable=True)            # e.g. "A1"
    price = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    features = Column(JSON, default=list)          # ["15h Fast generations", ...]
    is_popular = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(String, default=datetime.utcnow().isoformat)

    course_packages = relationship("PackageCourse", back_populates="package", cascade="all, delete-orphan")
    user_packages = relationship("UserPackage", back_populates="package", cascade="all, delete-orphan")


class PackageCourse(Base):
    __tablename__ = "package_courses"

    id = Column(Integer, primary_key=True, index=True)
    package_id = Column(Integer, ForeignKey("packages.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)

    package = relationship("Package", back_populates="course_packages")
    course = relationship("Course")


class UserPackage(Base):
    __tablename__ = "user_packages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    package_id = Column(Integer, ForeignKey("packages.id", ondelete="CASCADE"), nullable=False)
    purchased_at = Column(String, default=datetime.utcnow().isoformat)

    user = relationship("User")
    package = relationship("Package", back_populates="user_packages")


class CourseRating(Base):
    __tablename__ = "course_ratings"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating = Column(Float, nullable=False)  # 1.0 – 5.0
    created_at = Column(String, default=datetime.utcnow().isoformat())

    course = relationship("Course", back_populates="ratings")
    user = relationship("User")


class CourseOverview(Base):
    __tablename__ = "course_overviews"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    week_start = Column(Integer, nullable=False)   # e.g. 1
    week_end = Column(Integer, nullable=False)     # e.g. 2
    title = Column(String, nullable=False)         # e.g. "Foundation"
    description = Column(Text, nullable=True)      # e.g. "Thinking in English, Basic Sentence Patterns"
    order = Column(Integer, default=0)

    course = relationship("Course", back_populates="overviews")


class FAQ(Base):
    __tablename__ = "faqs"

    id = Column(Integer, primary_key=True, index=True)
    question = Column(String, nullable=False)
    answer = Column(Text, nullable=False)
    # NULL = general FAQ, set = course-specific FAQ
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=True, index=True)
    order = Column(Integer, default=0)
    created_at = Column(String, default=datetime.utcnow().isoformat())

    course = relationship("Course", back_populates="faqs")


class VerificationType(str, enum.Enum):
    EMAIL = "EMAIL"
    PHONE = "PHONE"


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id = Column(Integer, primary_key=True, index=True)
    contact = Column(String, index=True)  # Email or Phone
    code = Column(String)
    type = Column(Enum(VerificationType))
    expires_at = Column(String)  # ISO format
    is_used = Column(Boolean, default=False)
    created_at = Column(String, default=datetime.utcnow().isoformat())
