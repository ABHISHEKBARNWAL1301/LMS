"""Add missing user columns (phone_number, role, is_active, etc.)

These columns existed in the original create_all() schema but were never
covered by a migration, causing Railway (and any fresh DB from migrations)
to be missing them. Uses IF NOT EXISTS so it is safe on both fresh and
existing databases.

Revision ID: e5f6a7b8c9d0
Revises: c3d4e5f6a7b8
Create Date: 2026-03-02 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the userrole ENUM type if it does not already exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'userrole') THEN
                CREATE TYPE userrole AS ENUM ('STUDENT', 'INSTRUCTOR', 'ADMIN');
            END IF;
        END$$;
    """)

    # Users table — columns that were always in the model but never in a migration
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number VARCHAR")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS hashed_password VARCHAR")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_phone_verified BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_email_verified BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE")

    # Add role column using the userrole enum (IF NOT EXISTS via DO block)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'role'
            ) THEN
                ALTER TABLE users ADD COLUMN role userrole DEFAULT 'STUDENT';
            END IF;
        END$$;
    """)

    # Add unique index on phone_number if not already present
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE tablename = 'users' AND indexname = 'ix_users_phone_number'
            ) THEN
                CREATE UNIQUE INDEX ix_users_phone_number ON users (phone_number);
            END IF;
        END$$;
    """)

    # Enrollments — ensure enrolled_at and completed columns exist
    op.execute("ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS enrolled_at VARCHAR")
    op.execute("ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS completed BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS progress FLOAT DEFAULT 0.0")

    # Courses — ensure all current columns exist
    op.execute("ALTER TABLE courses ADD COLUMN IF NOT EXISTS selling_price FLOAT DEFAULT 0.0")
    op.execute("ALTER TABLE courses ADD COLUMN IF NOT EXISTS original_price FLOAT")
    op.execute("ALTER TABLE courses ADD COLUMN IF NOT EXISTS image_url VARCHAR")
    op.execute("ALTER TABLE courses ADD COLUMN IF NOT EXISTS topic VARCHAR")
    op.execute("ALTER TABLE courses ADD COLUMN IF NOT EXISTS level VARCHAR")
    op.execute("ALTER TABLE courses ADD COLUMN IF NOT EXISTS duration VARCHAR")

    # Create coupons table if missing
    op.execute("""
        CREATE TABLE IF NOT EXISTS coupons (
            id SERIAL PRIMARY KEY,
            code VARCHAR UNIQUE NOT NULL,
            discount_percent FLOAT NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at VARCHAR
        )
    """)

    # Create sale_config table if missing
    op.execute("""
        CREATE TABLE IF NOT EXISTS sale_config (
            id SERIAL PRIMARY KEY,
            is_active BOOLEAN DEFAULT FALSE,
            updated_at VARCHAR
        )
    """)

    # Create orders table if missing
    op.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            razorpay_order_id VARCHAR UNIQUE,
            amount FLOAT,
            status VARCHAR DEFAULT 'CREATED',
            course_ids JSON,
            created_at VARCHAR
        )
    """)

    # Create verification_codes table if missing
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'verificationtype') THEN
                CREATE TYPE verificationtype AS ENUM ('EMAIL', 'PHONE');
            END IF;
        END$$;
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS verification_codes (
            id SERIAL PRIMARY KEY,
            contact VARCHAR,
            code VARCHAR,
            type verificationtype,
            expires_at VARCHAR,
            is_used BOOLEAN DEFAULT FALSE,
            created_at VARCHAR
        )
    """)


def downgrade() -> None:
    # Downgrade is intentionally a no-op — dropping these columns would lose data
    pass
