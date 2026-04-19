from __future__ import annotations
"""
AssistantAgent — Agente de vendas da Vitalmed.
Usa Agno com Gemini Flash e storage PostgreSQL para memória de curto prazo.
"""
import logging
from pathlib import Path

from agno.agent import Agent
from agno.models.google import Gemini

from src.core.config import settings
from src.agents.assistant.tools import (
    get_lead_profile,
    update_lead_status,
    save_lead_interest,
    mark_lead_interested,
    mark_lead_closed,
    mark_lead_no_return,
    transfer_to_human,
)
from src.agents.doubts.tools import search_knowledge_base  # RAG compartilhado

logger = logging.getLogger(__name__)

# Carrega CONTEXT.md do agente (N2N)
_CONTEXT_PATH = Path(__file__).parent / "CONTEXT.md"
_ASSISTANT_CONTEXT = _CONTEXT_PATH.read_text(encoding="utf-8")


def _build_assistant_instructions(lead_memory_summary: str = "") -> str:
    """Monta as instruções completas do agente com contexto do lead."""
    memory_section = f"\n\n{lead_memory_summary}" if lead_memory_summary else ""
    return f"{_ASSISTANT_CONTEXT}{memory_section}"


ASSISTANT_TOOLS = [
    search_knowledge_base,   # RAG — SEMPRE usar antes de responder sobre produtos
    get_lead_profile,
    update_lead_status,
    save_lead_interest,
    mark_lead_interested,
    mark_lead_closed,
    mark_lead_no_return,
    transfer_to_human,
]


def create_assistant_agent(lead_memory_summary: str = "") -> Agent:
    """
    Cria instância do AssistantAgent com contexto do lead injetado.
    Usa Gemini Flash para velocidade e custo.
    """
    return Agent(
        name="AssistantAgent",
        role="Especialista em vendas e atendimento da Vitalmed",
        model=Gemini(id=settings.gemini_flash_model, api_key=settings.google_api_key),
        instructions=_build_assistant_instructions(lead_memory_summary),
        tools=ASSISTANT_TOOLS,
        add_history_to_context=False,  # Desabilitado — contexto vem do worker via full_message
        markdown=False,
        # respond_directly não disponível no agno 2.5.17
    )


async def get_assistant_agent(lead_memory_summary: str = "") -> Agent:
    """Async factory para uso no worker."""
    return create_assistant_agent(lead_memory_summary)
