"""Sweet-spot sessions on test films, which belong to no library (ADR-0031).

Revision ID: 0017
Revises: 0016
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.alter_column("library_id", existing_type=sa.INTEGER(), nullable=True)

    with op.batch_alter_table("tune_sessions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("film_id", sa.String(length=64), nullable=True))
        batch_op.alter_column("library_id", existing_type=sa.INTEGER(), nullable=True)


def downgrade() -> None:
    # Sessions and steps on test films have no library: they can't go back.
    op.execute("DELETE FROM jobs WHERE library_id IS NULL")
    op.execute("DELETE FROM tune_sessions WHERE library_id IS NULL")
    with op.batch_alter_table("tune_sessions", schema=None) as batch_op:
        batch_op.alter_column("library_id", existing_type=sa.INTEGER(), nullable=False)
        batch_op.drop_column("film_id")

    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.alter_column("library_id", existing_type=sa.INTEGER(), nullable=False)
