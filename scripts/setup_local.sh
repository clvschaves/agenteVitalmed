#!/usr/bin/env bash
# ============================================================
# setup_local.sh — Setup completo do ambiente local Vitalmed
# ============================================================
# Uso:
#   chmod +x scripts/setup_local.sh
#   ./scripts/setup_local.sh
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${CYAN}[SETUP]${NC} $1"; }
ok()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn(){ echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[ERR]${NC} $1"; exit 1; }

echo ""
echo -e "${CYAN}╔════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║    Agente Vitalmed — Setup Local       ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════╝${NC}"
echo ""

# ─── 1. Verificar dependências do sistema ────────────────────────────────────
log "Verificando dependências..."

command -v docker >/dev/null 2>&1 || err "Docker não encontrado. Instale Docker Desktop."
command -v python3 >/dev/null 2>&1 || err "Python3 não encontrado."

PYTHON=$(command -v python3.11 || command -v python3 || echo "python3")
ok "Python: $($PYTHON --version)"
ok "Docker: $(docker --version | cut -d' ' -f3)"

# ─── 2. Criar .env se não existir ────────────────────────────────────────────
if [ ! -f ".env" ]; then
    warn ".env não encontrado. Copiando de .env.example..."
    cp .env.example .env
    warn "⚠️  Configure o GOOGLE_API_KEY no .env antes de continuar!"
    exit 1
fi
ok ".env encontrado"

# ─── 3. Instalar dependências Python ─────────────────────────────────────────
log "Instalando dependências Python..."
$PYTHON -m pip install --quiet -e ".[dev]" 2>&1 | tail -3 || \
$PYTHON -m pip install --quiet \
    fastapi uvicorn[standard] sqlalchemy asyncpg psycopg2-binary pgvector \
    redis pydantic pydantic-settings python-dotenv httpx python-multipart \
    langfuse pymupdf python-docx tiktoken google-generativeai \
    streamlit pandas alembic agno 2>&1 | tail -5
ok "Dependências instaladas"

# ─── 4. Subir PostgreSQL e Redis via Docker ───────────────────────────────────
log "Subindo PostgreSQL e Redis via Docker..."
docker compose up -d postgres redis
log "Aguardando PostgreSQL ficar pronto..."
for i in $(seq 1 20); do
    if docker compose exec postgres pg_isready -U vitalmed -d vitalmed_db >/dev/null 2>&1; then
        ok "PostgreSQL pronto!"
        break
    fi
    echo -n "."
    sleep 2
done
echo ""

# ─── 5. Aplicar migrations ───────────────────────────────────────────────────
log "Aplicando migrations Alembic..."
$PYTHON -m alembic upgrade head 2>&1 | tail -10
ok "Migrations aplicadas!"

# ─── 6. Criar migration inicial se não existir ────────────────────────────────
MIGRATIONS_COUNT=$(ls src/db/migrations/versions/ 2>/dev/null | wc -l | tr -d ' ')
if [ "$MIGRATIONS_COUNT" -eq "0" ]; then
    log "Criando migration inicial..."
    $PYTHON -m alembic revision --autogenerate -m "initial_schema"
    $PYTHON -m alembic upgrade head
    ok "Migration inicial criada e aplicada!"
fi

# ─── 7. Seed de leads mockados ────────────────────────────────────────────────
log "Inserindo leads mockados no banco..."
$PYTHON scripts/seed_leads.py
ok "Leads mockados inseridos!"

# ─── 8. Resumo final ──────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ✅ Setup concluído! Comandos para iniciar:        ║${NC}"
echo -e "${GREEN}╠════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║                                                    ║${NC}"
echo -e "${GREEN}║  FastAPI:    uvicorn src.gateway.main:app          ║${NC}"
echo -e "${GREEN}║              --reload --port 8000                  ║${NC}"
echo -e "${GREEN}║                                                    ║${NC}"
echo -e "${GREEN}║  Streamlit:  streamlit run tests/streamlit_app.py  ║${NC}"
echo -e "${GREEN}║                                                    ║${NC}"
echo -e "${GREEN}║  API Docs:   http://localhost:8000/docs            ║${NC}"
echo -e "${GREEN}║  Streamlit:  http://localhost:8501                 ║${NC}"
echo -e "${GREEN}║                                                    ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════╝${NC}"
echo ""
