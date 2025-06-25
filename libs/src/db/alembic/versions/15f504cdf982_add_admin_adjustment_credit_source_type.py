"""Add admin adjustment credit source type

Revision ID: 15f504cdf982
Revises: 2d712715f78b
Create Date: 2025-06-25 19:48:30.996662

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '15f504cdf982'
down_revision: Union[str, None] = '2d712715f78b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add ADMIN_ADJUSTMENT to the existing credit source type enum
    op.execute("ALTER TYPE kiwiq_billing_credit_source_type_enum ADD VALUE 'ADMIN_ADJUSTMENT'")


def downgrade() -> None:
    """Downgrade schema."""
    # Note: PostgreSQL doesn't support removing enum values directly
    # To downgrade, we would need to recreate the enum without ADMIN_ADJUSTMENT
    # For now, we'll leave it as no-op since removing enum values is complex
    # and would require checking if the value is in use
    pass
