from pydantic import BaseModel, EmailStr, model_validator, Field, field_validator
from typing import Optional, List, Dict
from enum import Enum
from datetime import datetime


class UserRole(str, Enum):
    STUDENT = "STUDENT"
    INSTRUCTOR = "INSTRUCTOR"
    ADMIN = "ADMIN"


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole = UserRole.STUDENT
    phone_number: Optional[str] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)


class EmailChangeRequest(BaseModel):
    new_email: EmailStr


class EmailVerifyRequest(BaseModel):
    code: str


class UserCreate(BaseModel):
    phone_number: str = Field(..., min_length=10, max_length=15)
    full_name: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=8)
    email: Optional[EmailStr] = None
    msg91_access_token: str  # proof that phone OTP was verified (H3)


class UserOut(BaseModel):
    id: int
    email: Optional[EmailStr] = None
    pending_email: Optional[str] = None
    full_name: Optional[str] = None
    role: UserRole
    phone_number: Optional[str] = None
    is_active: bool = True
    is_phone_verified: bool = False
    is_email_verified: bool = False

    @field_validator("is_active", "is_phone_verified", "is_email_verified", mode="before")
    @classmethod
    def coerce_none_to_false(cls, v):
        return v if v is not None else False

    class Config:
        from_attributes = True


class UserPublic(BaseModel):
    full_name: Optional[str] = "Student"

    class Config:
        from_attributes = True


class InstructorCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    phone_number: Optional[str] = Field(None, min_length=10, max_length=15)
    password: str = Field(..., min_length=8)
    bio: Optional[str] = None


class InstructorUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = Field(None, min_length=10, max_length=15)
    bio: Optional[str] = None
    is_active: Optional[bool] = None


class InstructorOut(BaseModel):
    id: int
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    bio: Optional[str] = None
    role: UserRole
    is_active: bool = True

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: Optional[str] = None


class OTPRequest(BaseModel):
    contact: str
    type: str = "PHONE"  # PHONE or EMAIL


class OTPVerify(BaseModel):
    contact: str
    code: str
    type: str = "PHONE"


class WidgetTokenVerify(BaseModel):
    access_token: str


class VideoLessonResponse(BaseModel):
    description: Optional[str]
    duration: Optional[int]
    video_url: Optional[str]
    transcoded_urls: Optional[Dict[str, str]]
    processing_status: str
    thumbnail_url: Optional[str]


class QuizLessonResponse(BaseModel):
    quiz_data: Optional[Dict[str, str]]





class LessonTypeEnum(str, Enum):
    VIDEO = "VIDEO"
    QUIZ = "QUIZ"


class LessonStatusEnum(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class LessonCreate(BaseModel):
    title: str
    description: Optional[str] = None
    type: LessonTypeEnum = LessonTypeEnum.VIDEO
    processing_status: Optional[LessonStatusEnum] = LessonStatusEnum.PENDING
    order: int = 0
    transcoded_urls: Optional[str] = None
    video_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    is_free: bool = False


class LessonReorder(BaseModel):
    lesson_ids: List[int]


class QuestionBase(BaseModel):
    text: str
    options: str  # JSON string
    correct_option_index: int


class QuestionCreate(QuestionBase):
    pass


class QuestionOut(QuestionBase):
    id: int
    lesson_id: int

    class Config:
        from_attributes = True


class LessonOut(BaseModel):
    id: int
    course_id: int
    title: str
    description: Optional[str] = None
    type: LessonTypeEnum
    order: int
    video_url: Optional[str] = None
    duration: Optional[int] = None
    processing_status: Optional[str] = None
    thumbnail_url: Optional[str] = None
    transcoded_urls: Optional[Dict[str, str]] = None  # Or JSON
    is_free: bool = False
    questions: List[QuestionOut] = []

    class Config:
        from_attributes = True


class CourseOut(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    selling_price: Optional[float] = None
    original_price: Optional[float] = None
    image_url: Optional[str] = None
    topic: Optional[str] = None
    level: Optional[str] = None
    is_live_class: Optional[bool] = False
    start_time: Optional[str] = None
    duration: Optional[int] = None  # number of days
    instructor_name: Optional[str] = None
    instructor_id: int
    lessons: List[LessonOut] = []
    assigned_instructor_id: Optional[int] = None
    assigned_instructor: Optional[InstructorOut] = None
    display_rating: Optional[float] = None
    display_learners_count: int = 0

    class Config:
        from_attributes = True


class CoursesPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[CourseOut]

    class Config:
        from_attributes = True


class AdminRatingUpdate(BaseModel):
    admin_rating: Optional[float] = Field(None, ge=0.0, le=5.0)
    admin_learners_count: Optional[int] = Field(None, ge=0)


class UserRatingCreate(BaseModel):
    rating: float = Field(..., ge=1.0, le=5.0)


class RatingSummaryOut(BaseModel):
    display_rating: Optional[float] = None      # rounded to 1 decimal
    display_learners_count: int = 0
    user_ratings_count: int = 0                 # actual submitted ratings


class CourseOverviewCreate(BaseModel):
    course_id: int
    week_start: int
    week_end: int
    title: str
    description: Optional[str] = None


class CourseOverviewUpdate(BaseModel):
    week_start: Optional[int] = None
    week_end: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None


class CourseOverviewReorder(BaseModel):
    overview_ids: List[int]


class CourseOverviewOut(BaseModel):
    id: int
    course_id: int
    week_start: int
    week_end: int
    title: str
    description: Optional[str] = None
    order: int

    class Config:
        from_attributes = True


class FAQCreate(BaseModel):
    question: str
    answer: str
    course_id: Optional[int] = None  # None = general FAQ


class FAQUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None


class FAQReorder(BaseModel):
    faq_ids: List[int]  # ordered list of IDs → assigned order 0, 1, 2, ...


class FAQOut(BaseModel):
    id: int
    question: str
    answer: str
    course_id: Optional[int] = None
    order: int
    created_at: str

    class Config:
        from_attributes = True


class EnrollmentBase(BaseModel):
    course_id: Optional[int] = None


class EnrollmentOut(BaseModel):
    id: int
    course_id: Optional[int] = None
    progress: float
    completed: bool
    completed_lesson_ids: Optional[List[int]] = []
    course: Optional[CourseOut] = None

    class Config:
        from_attributes = True


class BlogPostBase(BaseModel):
    title: str
    content: str
    excerpt: Optional[str] = None
    category: str
    image_url: Optional[str] = None


class BlogPostCreate(BlogPostBase):
    pass


class BlogPostOut(BlogPostBase):
    id: int
    author: str
    created_at: str

    class Config:
        from_attributes = True


class GalleryVideoBase(BaseModel):
    title: str
    video_url: str
    thumbnail_url: Optional[str] = None
    category: Optional[str] = None


class GalleryVideoCreate(GalleryVideoBase):
    pass


class GalleryVideoOut(GalleryVideoBase):
    id: int
    created_at: str

    class Config:
        from_attributes = True


class GalleryImageBase(BaseModel):
    caption: Optional[str] = None


class GalleryImageCreate(GalleryImageBase):
    pass


class GalleryImageOut(GalleryImageBase):
    id: int
    image_url: str
    created_at: str

    class Config:
        from_attributes = True


# Schema for the callback data
class TranscodeCallback(BaseModel):
    course_id: int
    lesson_id: int
    status: str  # "COMPLETED" or "FAILED"
    master_key: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration: Optional[int] = 0
    qualities: Optional[List[str]] = []
    error: Optional[str] = None


class CourseUpdate(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    selling_price: float = Field(0.0, ge=0)
    original_price: Optional[float] = Field(None, ge=0)
    lessons_count: int = Field(0)
    quiz_count: int = Field(0)
    image_url: Optional[str] = Field(None)
    topic: Optional[str] = Field(None)
    level: Optional[str] = Field(None)
    is_live_class: Optional[bool] = False
    start_time: Optional[str] = None
    duration: Optional[int] = None  # number of days
    instructor_name: Optional[str] = None

    @model_validator(mode="after")
    def validate_prices(self):
        if self.original_price is not None and self.original_price < self.selling_price:
            raise ValueError("Original price cannot be less than selling price")
        return self


class CounsellingRequest(BaseModel):
    name: str
    email: str
    phone: str


class CouponCreate(BaseModel):
    code: str
    discount_percent: float


class CouponOut(BaseModel):
    id: int
    code: str
    discount_percent: float
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True


class CouponApplyRequest(BaseModel):
    code: str


class CouponApplyResponse(BaseModel):
    code: str
    discount_percent: float
    valid: bool
    message: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


class SaleInfoOut(BaseModel):
    is_sale_active: bool
    max_discount: Optional[float] = None
    active_coupons: List[dict] = []


class PackageCourseOut(BaseModel):
    course_id: int

    class Config:
        from_attributes = True


class PackageOut(BaseModel):
    id: int
    name: str
    tag: Optional[str] = None
    price: float
    description: Optional[str] = None
    features: List[str] = []
    is_popular: bool = False
    is_active: bool = True
    course_packages: List[PackageCourseOut] = []

    class Config:
        from_attributes = True


class PackageCreate(BaseModel):
    name: str
    tag: Optional[str] = None
    price: float = Field(..., ge=0)
    description: Optional[str] = None
    features: List[str] = []
    is_popular: bool = False
    course_ids: List[int] = []


class PackageUpdate(BaseModel):
    name: Optional[str] = None
    tag: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    description: Optional[str] = None
    features: Optional[List[str]] = None
    is_popular: Optional[bool] = None
    is_active: Optional[bool] = None
    course_ids: Optional[List[int]] = None


class OrderCreate(BaseModel):
    course_ids: Optional[List[int]] = None
    package_id: Optional[int] = None
    coupon_code: Optional[str] = None

    @model_validator(mode="after")
    def validate_order_type(self):
        if not self.course_ids and self.package_id is None:
            raise ValueError("Provide either course_ids or package_id")
        if self.course_ids and self.package_id is not None:
            raise ValueError("Provide either course_ids or package_id, not both")
        return self


class OrderOut(BaseModel):
    id: int
    razorpay_order_id: str
    amount: float
    status: str
    currency: str = "INR"

    class Config:
        from_attributes = True


class PaymentVerification(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str

    razorpay_signature: str


class CheckPhoneRequest(BaseModel):
    phone_number: str


class CheckEmailRequest(BaseModel):
    email: EmailStr


class Msg91SendOtpRequest(BaseModel):
    contact: str
    token: Optional[str] = None
    purpose: str = "login"  # "login" | "register"


class Msg91VerifyOtpRequest(BaseModel):
    contact: str
    code: str
    req_id: str


class OTPLoginRequest(BaseModel):
    """MSG91 access token + phone number for phone OTP login."""

    access_token: str
    phone_number: str
