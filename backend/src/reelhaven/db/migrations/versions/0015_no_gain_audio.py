"""Remember audio conversions that didn't make a file smaller.

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("media_files", schema=None) as batch_op:
        batch_op.add_column(sa.Column("no_gain_audio", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("media_files", schema=None) as batch_op:
        batch_op.drop_column("no_gain_audio")
