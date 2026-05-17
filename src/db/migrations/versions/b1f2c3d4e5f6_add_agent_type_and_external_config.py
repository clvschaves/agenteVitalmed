"""add_agent_type_and_external_config

Adiciona suporte a agentes importados (BigQuery, Databricks, custom code).

Revision ID: b1f2c3d4e5f6
Revises: a3f8b2d10c5e
Create Date: 2026-05-02 03:15:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1f2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'd7e8f9a0b1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adiciona agent_type e external_config na tabela platform_agents."""
    # agent_type: "native" | "bigquery" | "databricks_genie" | "custom_code"
    op.add_column(
        'platform_agents',
        sa.Column(
            'agent_type',
            sa.String(length=30),
            nullable=False,
            server_default='native',
        ),
    )
    # external_config: JSON com credenciais e parâmetros do agente importado
    op.add_column(
        'platform_agents',
        sa.Column('external_config', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    """Remove colunas de agente importado."""
    op.drop_column('platform_agents', 'external_config')
    op.drop_column('platform_agents', 'agent_type')
