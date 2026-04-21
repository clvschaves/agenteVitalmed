#!/bin/bash
# entrypoint.sh — garante que o banco esteja migrado antes de subir o servidor
set -e

echo "================================================================="
echo "  Vitalmed API — Iniciando container"
echo "================================================================="

# ── 1. Aguardar Postgres ficar disponível ────────────────────────────
echo "→ Aguardando PostgreSQL..."
until pg_isready -h "${PGHOST:-postgres}" -U "${PGUSER:-vitalmed}" -q; do
  sleep 1
done
echo "✓ PostgreSQL disponível"

# ── 2. Rodar migrations Alembic (idempotente — safe em cada restart) ─
echo "→ Aplicando migrations Alembic..."
alembic -c /app/alembic.ini upgrade head
echo "✓ Migrations aplicadas"

# ── 3. Subir o comando passado ao container (ex: uvicorn ou streamlit) ─
echo "→ Iniciando: $*"
exec "$@"
