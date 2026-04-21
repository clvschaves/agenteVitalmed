"""add chatwoot_contact_id to leads

Revision ID: a3f1b2c4d5e6
Revises: 7c4975a440b4
Create Date: 2026-04-21 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3f1b2c4d5e6'
down_revision: Union[str, None] = '7c4975a440b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'leads',
        sa.Column('chatwoot_contact_id', sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('leads', 'chatwoot_contact_id')
