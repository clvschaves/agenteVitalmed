"""rename chatwoot_contact_id to chatwoot_conversation_id

Revision ID: c7d8e9f0a1b2
Revises: b5e2c3d4f6a7
Create Date: 2026-05-17

"""
from alembic import op

revision = 'c7d8e9f0a1b2'
down_revision = 'd7e8f9a0b1c2'
branch_labels = None
depends_on = None


def upgrade():
    # Renomear coluna preservando dados existentes
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='leads' AND column_name='chatwoot_contact_id'
            ) THEN
                ALTER TABLE leads
                    RENAME COLUMN chatwoot_contact_id TO chatwoot_conversation_id;
            END IF;
        END $$;
    """)


def downgrade():
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='leads' AND column_name='chatwoot_conversation_id'
            ) THEN
                ALTER TABLE leads
                    RENAME COLUMN chatwoot_conversation_id TO chatwoot_contact_id;
            END IF;
        END $$;
    """)
