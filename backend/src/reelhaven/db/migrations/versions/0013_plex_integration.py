"""plex integration kind

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-07 22:30:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME = "ck_integrations_integration_kind"


def upgrade() -> None:
    # SQLite can't alter a CHECK constraint: batch mode rebuilds the table.
    with op.batch_alter_table("integrations", recreate="always") as batch_op:
        batch_op.drop_constraint(op.f(_NAME), type_="check")
        batch_op.create_check_constraint(
            "integration_kind", "kind IN ('sonarr', 'radarr', 'tmdb', 'plex')"
        )


def downgrade() -> None:
    op.execute("DELETE FROM integrations WHERE kind = 'plex'")
    with op.batch_alter_table("integrations", recreate="always") as batch_op:
        batch_op.drop_constraint(op.f(_NAME), type_="check")
        batch_op.create_check_constraint("integration_kind", "kind IN ('sonarr', 'radarr', 'tmdb')")
