"""add contracts and contract_dependents tables

Revision ID: d7e8f9a0b1c2
Revises: b5e2c3d4f6a7
Create Date: 2026-04-21

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'd7e8f9a0b1c2'
down_revision = 'b5e2c3d4f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── contracts ───────────────────────────────────────────────────────────────
    op.create_table(
        'contracts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('lead_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('contract_type', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='a_enviar'),
        sa.Column('gcs_path', sa.String(500)),
        sa.Column('filename', sa.String(255)),
        sa.Column('titular_data', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('contract_data', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('signed_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_contracts_lead_id', 'contracts', ['lead_id'])
    op.create_index('ix_contracts_status', 'contracts', ['status'])

    # ── contract_dependents ──────────────────────────────────────────────────────
    op.create_table(
        'contract_dependents',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('contract_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('nome_completo', sa.String(150), nullable=False),
        sa.Column('cpf', sa.String(14)),
        sa.Column('rg', sa.String(20)),
        sa.Column('data_nascimento', sa.String(20)),
        sa.Column('idade', sa.Integer()),
        sa.Column('parentesco', sa.String(50)),
        sa.Column('faixa_etaria', sa.String(30)),
        sa.Column('valor_plano', sa.String(30)),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_contract_dependents_contract_id', 'contract_dependents', ['contract_id'])


def downgrade() -> None:
    op.drop_table('contract_dependents')
    op.drop_table('contracts')
