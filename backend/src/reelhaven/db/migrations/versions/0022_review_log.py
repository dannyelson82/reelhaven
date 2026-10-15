"""The review record: files the Review page listed, kept after they're resolved (ADR-0033).

Revision ID: 0022
Revises: 0021
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import reelhaven.db.types

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("media_file_id", sa.Integer(), nullable=True),
        sa.Column("library_name", sa.String(length=256), nullable=False),
        sa.Column("relative_path", sa.String(length=4096), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("first_seen_at", reelhaven.db.types.UTCDateTime(), nullable=False),
        sa.Column("last_seen_at", reelhaven.db.types.UTCDateTime(), nullable=False),
        sa.Column("resolved_at", reelhaven.db.types.UTCDateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["media_file_id"],
            ["media_files.id"],
            name=op.f("fk_review_log_media_file_id_media_files"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_log")),
    )
    with op.batch_alter_table("review_log", schema=None) as batch_op:
        batch_op.create_index(
            "ix_review_log_open", ["resolved_at", "media_file_id", "kind"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("review_log", schema=None) as batch_op:
        batch_op.drop_index("ix_review_log_open")

    op.drop_table("review_log")
