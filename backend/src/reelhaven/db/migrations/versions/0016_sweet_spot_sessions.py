"""Sweet-spot sessions: one scene encoded at several qualities (ADR-0031).

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import reelhaven.db.types

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tune_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("library_id", sa.Integer(), nullable=False),
        sa.Column("media_file_id", sa.Integer(), nullable=True),
        sa.Column("relative_path", sa.String(length=4096), nullable=False),
        sa.Column("base", sa.JSON(), nullable=False),
        sa.Column("scene_start", sa.Double(), nullable=False),
        sa.Column("scene_seconds", sa.Double(), nullable=False),
        sa.Column("file_bytes", sa.Integer(), nullable=False),
        sa.Column("video_bytes", sa.Integer(), nullable=True),
        sa.Column("requested_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", reelhaven.db.types.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["library_id"],
            ["libraries.id"],
            name=op.f("fk_tune_sessions_library_id_libraries"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["media_file_id"],
            ["media_files.id"],
            name=op.f("fk_tune_sessions_media_file_id_media_files"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tune_sessions")),
    )
    with op.batch_alter_table("tune_sessions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_tune_sessions_library_id"), ["library_id"], unique=False
        )

    op.create_table(
        "tune_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("quality", sa.Double(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "running",
                "done",
                "failed",
                name="tune_step_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", reelhaven.db.types.UTCDateTime(), nullable=False),
        sa.Column("finished_at", reelhaven.db.types.UTCDateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'done', 'failed')", name=op.f("ck_tune_steps_tune_step_status")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["tune_sessions.id"],
            name=op.f("fk_tune_steps_session_id_tune_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tune_steps")),
    )
    with op.batch_alter_table("tune_steps", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_tune_steps_session_id"), ["session_id"], unique=False)

    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tune_step_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_jobs_tune_step_id_tune_steps"),
            "tune_steps",
            ["tune_step_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_jobs_tune_step_id_tune_steps"), type_="foreignkey")
        batch_op.drop_column("tune_step_id")

    with op.batch_alter_table("tune_steps", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tune_steps_session_id"))

    op.drop_table("tune_steps")
    with op.batch_alter_table("tune_sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tune_sessions_library_id"))

    op.drop_table("tune_sessions")
