"""
FastAPI Gateway — Agente Vitalmed
Entry point da aplicação. Registra rotas, configura lifespan e middleware.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.gateway.routes.webhook import router as webhook_router
from src.gateway.routes.status import router as status_router
from src.gateway.routes.admin import router as admin_router
from src.core.config import settings

logging.basicConfig(level=getattr(logging, settings.log_level))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup e shutdown da aplicação."""
    logger.info("🚀 Agente Vitalmed iniciando...")
    logger.info(f"   ENV:   {settings.app_env}")
    logger.info(f"   LLM:   {settings.gemini_flash_model} (flash) / {settings.gemini_pro_model} (pro)")
    yield
    logger.info("🛑 Agente Vitalmed encerrando...")


app = FastAPI(
    title="Agente Vitalmed — API",
    description="Gateway async para o sistema multi-agentes de vendas da Vitalmed",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Rotas ───────────────────────────────────────────────────────────────────
app.include_router(webhook_router, prefix="/webhook", tags=["Webhook"])
app.include_router(status_router, prefix="/webhook", tags=["Status Jobs"])
app.include_router(admin_router, prefix="/admin", tags=["Admin RAG"])


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "agente-vitalmed"}
