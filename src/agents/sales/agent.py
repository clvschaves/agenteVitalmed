from __future__ import annotations
"""
SalesAgent — Agente especialista em conversão de leads da Vitalmed.
Usa Gemini Pro para raciocínio mais poderoso e seguimento de instruções complexas de venda.
Chamado diretamente pelo worker, sem passar pelo router.
"""
import logging
from pathlib import Path

from agno.agent import Agent
from agno.models.google import Gemini

from src.core.config import settings
from src.agents.doubts.tools import search_knowledge_base
from src.agents.assistant.tools import (
    mark_lead_interested,
    mark_lead_closed,
    transfer_to_human,
    update_lead_status,
)

logger = logging.getLogger(__name__)

_CONTEXT = (Path(__file__).parent / "CONTEXT.md").read_text(encoding="utf-8")

SALES_TOOLS = [
    search_knowledge_base,
    mark_lead_interested,
    mark_lead_closed,
    transfer_to_human,
    update_lead_status,
]


def create_sales_agent(fallback_flash: bool = False) -> Agent:
    """
    Cria o SalesAgent.
    - fallback_flash=False → usa Gemini Pro (padrão, raciocínio superior)
    - fallback_flash=True  → usa Gemini Flash (fallback quando Pro está em 503)
    """
    model_id = settings.gemini_flash_model if fallback_flash else settings.gemini_pro_model
    logger.info("SalesAgent → modelo: %s", model_id)

    return Agent(
        name="SalesAgent",
        role="Consultor de vendas especialista em conversão de leads da Vitalmed",
        model=Gemini(id=model_id, api_key=settings.google_api_key),
        instructions=_CONTEXT,
        tools=SALES_TOOLS,
        add_history_to_messages=False,
        markdown=False,
    )
