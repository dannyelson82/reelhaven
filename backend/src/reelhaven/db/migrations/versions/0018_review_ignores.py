"""Remember review items the owner chose to ignore (ADR-0032).

Revision ID: 0018
Revises: 0017
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("media_files", schema=None) as batch_op:
        batch_op.add_column(sa.Column("review_ignored", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("media_files", schema=None) as batch_op:
        batch_op.drop_column("review_ignored")
