#!/bin/bash
# deploy.sh — Deploy automatizado no servidor Linux
# Uso: ./deploy.sh
set -e

echo "================================================================="
echo "  Vitalmed — Deploy em Producao"
echo "  $(date '+%d/%m/%Y %H:%M:%S')"
echo "================================================================="

COMPOSE="docker compose"
# Fallback para docker-compose v1 se necessário
command -v "docker compose" &>/dev/null || COMPOSE="docker-compose"

# ── 1. Atualizar código ──────────────────────────────────────────────
echo ""
echo "→ [1/5] Atualizando código (git pull)..."
git pull origin main
echo "✓ Código atualizado"

# ── 2. Rebuild apenas da imagem da API (sem cache para pegar novas deps) ──
echo ""
echo "→ [2/5] Rebuilding imagem (sem cache)..."
$COMPOSE build --no-cache api streamlit
echo "✓ Imagem reconstruída"

# ── 3. Reiniciar containers (o entrypoint.sh roda alembic upgrade head) ──
echo ""
echo "→ [3/5] Reiniciando containers..."
$COMPOSE up -d api streamlit
echo "✓ Containers reiniciados"

# ── 4. Aguardar API ficar saudável ───────────────────────────────────
echo ""
echo "→ [4/5] Aguardando API ficar saudável..."
MAX_WAIT=60
COUNT=0
until curl -sf http://localhost:8000/health > /dev/null 2>&1; do
  if [ $COUNT -ge $MAX_WAIT ]; then
    echo "✗ Timeout — API não respondeu em ${MAX_WAIT}s"
    echo "  Verificando logs..."
    $COMPOSE logs --tail=30 api
    exit 1
  fi
  sleep 2
  COUNT=$((COUNT + 2))
  echo "  ... aguardando (${COUNT}s)"
done
echo "✓ API respondendo em http://localhost:8000"

# ── 5. Status final ──────────────────────────────────────────────────
echo ""
echo "→ [5/5] Status dos containers:"
$COMPOSE ps

echo ""
echo "================================================================="
echo "  ✅ Deploy concluído com sucesso!"
echo "  API:       http://localhost:8000"
echo "  Streamlit: http://localhost:8501"
echo "================================================================="
