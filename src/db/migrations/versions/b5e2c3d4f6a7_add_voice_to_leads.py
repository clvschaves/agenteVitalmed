"""add voice and fix chatwoot_contact_id to leads

Revision ID: b5e2c3d4f6a7
Revises: a3f1b2c4d5e6
Create Date: 2026-04-21 14:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b5e2c3d4f6a7'
down_revision: Union[str, None] = 'a3f1b2c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Garante chatwoot_contact_id caso não exista (idempotente)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='leads' AND column_name='chatwoot_contact_id'
            ) THEN
                ALTER TABLE leads ADD COLUMN chatwoot_contact_id VARCHAR(50);
            END IF;
        END$$;
    """)

    # Adiciona coluna voice
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='leads' AND column_name='voice'
            ) THEN
                ALTER TABLE leads ADD COLUMN voice BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;
        END$$;
    """)


def downgrade() -> None:
    op.drop_column('leads', 'voice')
