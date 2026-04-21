# ─── Base: Python 3.11 slim (Debian Bookworm) ────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# ─── Dependências de sistema ──────────────────────────────────────────────────
# libpq-dev   → psycopg2 (sync, para alembic)
# gcc/g++     → compilar extensões C (asyncpg, tiktoken)
# libffi-dev  → cffi (dependência de várias libs crypto/google)
# curl        → healthchecks e download de assets
# ffmpeg      → processamento de áudio (whisper, se necessário)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    libffi-dev \
    curl \
    ffmpeg \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# ─── Instalar dependências Python ─────────────────────────────────────────────
# Copiamos apenas o pyproject.toml primeiro para aproveitar cache de camadas
COPY pyproject.toml README.md ./

# Atualizar pip + wheel antes de instalar pacotes
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Instalar o projeto em modo editável (sem torch/whisper no build principal)
RUN pip install --no-cache-dir -e .

# ─── Copiar código fonte ──────────────────────────────────────────────────────
COPY . .

# ─── Diretórios de runtime ────────────────────────────────────────────────────
RUN mkdir -p uploads docs src/memory/palace/leads

# ─── Entrypoint: roda migration antes de qualquer comando ────────────────────
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# ─── Metadados ────────────────────────────────────────────────────────────────
EXPOSE 8000 8501
ENTRYPOINT ["/entrypoint.sh"]
