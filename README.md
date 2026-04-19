# 🏥 Agente Vitalmed

Sistema multi-agente de vendas e atendimento para a **Vitalmed**, especializada em UTI Móvel e planos de saúde emergencial.

## 🏗️ Arquitetura

```
WhatsApp/Chatwoot → n8n → POST /webhook/message
                              ↓
                         FastAPI Worker (background)
                              ↓
                    ┌─────────────────────┐
                    │   SalesAgent (Pro)  │ ← Gemini 2.5 Pro
                    │   + RAG (pgvector)  │
                    └─────────────────────┘
                              ↓
                    POST n8n webhook (resposta)
                              ↓
                    Chatwoot → WhatsApp
```

## 🤖 Agents

| Agent | Modelo | Função |
|---|---|---|
| **SalesAgent** | Gemini 2.5 Pro | Conversão de leads, follow-up e fechamento |
| **DoubtsAgent** | Gemini 2.5 Flash | Dúvidas técnicas com busca RAG |
| **AssistantAgent** | Gemini 2.5 Flash | Atendimento geral e ferramentas de CRM |

## ⚡ Stack

- **FastAPI** + Uvicorn (4 workers)
- **Agno 2.5.x** — framework de agents
- **Gemini 2.5 Pro/Flash** — modelos de linguagem
- **PostgreSQL + pgvector** — banco de dados + busca vetorial
- **Redis** — filas de jobs e cache de sessão
- **Docker Compose** — orquestração
- **n8n** — automação e entrega de mensagens

## 🚀 Setup

### Pré-requisitos
- Docker + Docker Compose V2
- Chave de API Google Gemini

### Variáveis de ambiente

Copie `.env.example` para `.env` e preencha:

```env
GOOGLE_API_KEY=...
DATABASE_URL=postgresql+asyncpg://vitalmed:senha@localhost:5432/vitalmed_db
REDIS_URL=redis://localhost:6379/0
N8N_WEBHOOK_URL=https://seu-n8n.com/webhook/...
```

### Subir localmente

```bash
docker compose up -d
```

A API estará disponível em `http://localhost:8000`.

## 📡 Endpoints

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/webhook/message` | Recebe mensagem do lead |
| `GET` | `/webhook/status/{job_id}` | Consulta status do job |
| `POST` | `/admin/upload` | Upload de documento para RAG |
| `GET` | `/admin/documents` | Lista documentos indexados |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Swagger UI |

### Payload do webhook

```json
{
  "phone": "5511999999999",
  "name": "João Silva",
  "message": "Quero saber sobre os planos",
  "source": "chatwoot",
  "chatwoot_conversation_id": "123"
}
```

### Resposta enviada ao n8n

```json
{
  "phone": "5511999999999",
  "name": "João Silva",
  "user_message": "Quero saber sobre os planos",
  "agent_response": "Olá, João! ...",
  "agent_used": "sales_pro",
  "job_id": "uuid",
  "chatwoot_conversation_id": "123",
  "sent_at": "2026-04-19T..."
}
```

## 📁 Estrutura

```
src/
├── agents/
│   ├── sales/       # SalesAgent (vendas, Pro)
│   ├── doubts/      # DoubtsAgent (dúvidas + RAG)
│   ├── assistant/   # AssistantAgent (CRM tools)
│   └── router/      # RouterAgent (Agno Team)
├── gateway/
│   ├── main.py      # FastAPI app
│   ├── worker.py    # Processamento async de jobs
│   └── routes/      # Endpoints HTTP
├── rag/             # Pipeline RAG (ingest + retriever)
├── db/              # Models + migrations (Alembic)
├── memory/          # Long-term memory (.md files)
└── core/            # Config, settings
```
