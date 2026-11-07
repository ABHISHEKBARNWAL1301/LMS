from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models import Coupon, SaleConfig, User, UserRole
from schemas import CouponCreate, CouponOut, CouponApplyRequest, CouponApplyResponse, SaleInfoOut
from auth import get_current_user
from typing import List
from datetime import datetime

router = APIRouter(prefix="/coupons", tags=["coupons"])


# ── Helpers ──────────────────────────────────────────────────────────────────

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def get_or_create_sale_config(db: Session) -> SaleConfig:
    config = db.query(SaleConfig).filter(SaleConfig.id == 1).first()
    if not config:
        config = SaleConfig(id=1, is_active=False)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


# ── Public endpoint ───────────────────────────────────────────────────────────

@router.get("/sale-info", response_model=SaleInfoOut)
def get_sale_info(db: Session = Depends(get_db)):
    """
    Public endpoint. Returns whether the sale banner is active and the list
    of currently enabled coupon codes (so the banner can display them).
    """
    config = get_or_create_sale_config(db)
    active_coupons = db.query(Coupon).filter(Coupon.is_active == True).all()
    max_discount = (
        max((c.discount_percent for c in active_coupons), default=None)
        if active_coupons
        else None
    )
    return {
        "is_sale_active": config.is_active,
        "max_discount": max_discount,
        "active_coupons": [
            {"code": c.code, "discount_percent": c.discount_percent}
            for c in active_coupons
        ],
    }


# ── Authenticated: validate/apply a coupon code ───────────────────────────────

@router.post("/apply", response_model=CouponApplyResponse)
def apply_coupon(
    request: CouponApplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Validate a coupon code for the current user. Returns discount percentage
    so the frontend can show the discounted total before checkout.
    """
    coupon = (
        db.query(Coupon)
        .filter(Coupon.code == request.code.strip().upper())
        .first()
    )
    if not coupon:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invalid coupon code"
        )
    if not coupon.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This coupon has been disabled",
        )
    return {
        "code": coupon.code,
        "discount_percent": coupon.discount_percent,
        "valid": True,
        "message": f"{coupon.discount_percent:.0f}% discount applied!",
    }


# ── Admin: sale toggle ────────────────────────────────────────────────────────

@router.patch("/sale/toggle")
def toggle_sale(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    config = get_or_create_sale_config(db)
    config.is_active = not config.is_active
    config.updated_at = datetime.utcnow().isoformat()
    db.commit()
    db.refresh(config)
    return {"is_sale_active": config.is_active}


# ── Admin: coupon CRUD ────────────────────────────────────────────────────────

@router.get("/", response_model=List[CouponOut])
def list_coupons(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return db.query(Coupon).order_by(Coupon.id).all()


@router.post("/", response_model=CouponOut, status_code=status.HTTP_201_CREATED)
def create_coupon(
    coupon: CouponCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if not (0 < coupon.discount_percent < 100):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Discount percent must be between 1 and 99",
        )
    code = coupon.code.strip().upper()
    existing = db.query(Coupon).filter(Coupon.code == code).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Coupon code already exists",
        )
    db_coupon = Coupon(
        code=code,
        discount_percent=coupon.discount_percent,
        is_active=True,
        created_at=datetime.utcnow().isoformat(),
    )
    db.add(db_coupon)
    db.commit()
    db.refresh(db_coupon)
    return db_coupon


@router.patch("/{coupon_id}/toggle", response_model=CouponOut)
def toggle_coupon(
    coupon_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    coupon = db.query(Coupon).filter(Coupon.id == coupon_id).first()
    if not coupon:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coupon not found")
    coupon.is_active = not coupon.is_active
    db.commit()
    db.refresh(coupon)
    return coupon


@router.delete("/{coupon_id}")
def delete_coupon(
    coupon_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    coupon = db.query(Coupon).filter(Coupon.id == coupon_id).first()
    if not coupon:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coupon not found")
    db.delete(coupon)
    db.commit()
    return {"message": "Coupon deleted"}
