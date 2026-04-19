"""update_embedding_dim_3072

Revision ID: 7c4975a440b4
Revises: 34681de95918
Create Date: 2026-04-12

Altera a coluna embedding de vector(768) para vector(3072)
para compatibilidade com gemini-embedding-001.

Nota: índice vetorial deve ser criado manualmente após popular o banco
com: CREATE INDEX ... USING hnsw
Requer pgvector >= 0.7.0 para hnsw com dims > 2000.
"""
from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa

revision: str = '7c4975a440b4'
down_revision: Union[str, Sequence[str], None] = '34681de95918'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remover índice ivfflat (não suporta ALTER TYPE)
    op.execute('DROP INDEX IF EXISTS ix_knowledge_chunks_embedding')

    # Alterar dimensão do vetor de 768 para 3072
    op.execute(
        'ALTER TABLE knowledge_chunks '
        'ALTER COLUMN embedding TYPE vector(3072) '
        'USING embedding::text::vector(3072)'
    )
    # Nota: índice vetorial hnsw/ivfflat requer pgvector >= 0.7.0 para 3072 dims.
    # O índice será criado manualmente após popular o banco.


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ix_knowledge_chunks_embedding')
    op.execute(
        'ALTER TABLE knowledge_chunks '
        'ALTER COLUMN embedding TYPE vector(768) '
        'USING NULL'
    )
    op.create_index(
        'ix_knowledge_chunks_embedding',
        'knowledge_chunks',
        ['embedding'],
        unique=False,
        postgresql_using='ivfflat',
        postgresql_with={'lists': 100},
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )
