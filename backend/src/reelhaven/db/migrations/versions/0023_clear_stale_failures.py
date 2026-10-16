"""Clear failures that can't be retried from the Failed tab (ADR-0033).

Before 0.9.2 a retry didn't clear the failure it replaced, so failed jobs whose file
has had a newer job since (or whose file is gone) stayed on the Failed tab, and Retry
all (which looks at each file's latest job) never reached them. They stay in the
database and the failure report.

Revision ID: 0023
Revises: 0022
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Timestamps are stored like UTCDateTime writes them (naive UTC, ISO with a space).
    op.execute(
        """
        UPDATE jobs SET cleared_at = strftime('%Y-%m-%d %H:%M:%S', 'now') || '.000000'
        WHERE status = 'failed' AND cleared_at IS NULL AND (
            (media_file_id IS NOT NULL AND EXISTS (
                SELECT 1 FROM jobs AS newer
                WHERE newer.media_file_id = jobs.media_file_id AND newer.id > jobs.id
            ))
            OR (media_file_id IS NULL AND type IN ('remux', 'encode'))
        )
        """
    )


def downgrade() -> None:
    pass  # nothing to undo: clearing only hides failures from the Failed tab
