"""Add pending_email to users table (H4 security fix)

Revision ID: b1c2d3e4f5a6
Revises: aa3094553aa3
Create Date: 2026-03-01 00:00:00.000000

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "205053ef3049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("pending_email", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "pending_email")
