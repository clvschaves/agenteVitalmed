#!/bin/bash
# entrypoint.sh — garante que o banco esteja migrado antes de subir o servidor
set -e

echo "================================================================="
echo "  Vitalmed API — Iniciando container"
echo "================================================================="

PGHOST="${PGHOST:-postgres}"
PGUSER="${PGUSER:-vitalmed}"
PGPORT="${PGPORT:-5432}"

# ── 1. Aguardar Postgres ficar disponível ────────────────────────────
echo "→ Aguardando PostgreSQL em ${PGHOST}:${PGPORT}..."

# Usa pg_isready se disponível, senão usa nc (netcat) como fallback
wait_postgres() {
    if command -v pg_isready &>/dev/null; then
        pg_isready -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -q
    else
        # Fallback: checar porta TCP
        bash -c ">/dev/tcp/${PGHOST}/${PGPORT}" 2>/dev/null
    fi
}

MAX_TRIES=30
COUNT=0
until wait_postgres; do
    COUNT=$((COUNT + 1))
    if [ $COUNT -ge $MAX_TRIES ]; then
        echo "✗ PostgreSQL não disponível após ${MAX_TRIES}s — abortando"
        exit 1
    fi
    sleep 2
done
echo "✓ PostgreSQL disponível"

# ── 2. Rodar migrations Alembic (idempotente — safe em cada restart) ─
echo "→ Aplicando migrations Alembic..."
alembic -c /app/alembic.ini upgrade head
echo "✓ Migrations aplicadas"

# ── 3. Subir o comando passado ao container ──────────────────────────
echo "→ Iniciando: $*"
exec "$@"
