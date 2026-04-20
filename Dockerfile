FROM python:3.11-slim

WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependências Python
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir -e .

# Copiar código
COPY . .

# Diretórios de dados
RUN mkdir -p uploads docs src/memory/palace/leads

EXPOSE 8000 8501
