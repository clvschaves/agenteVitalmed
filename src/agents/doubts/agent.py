from __future__ import annotations
"""
DoubtsAgent — Agente de dúvidas com RAG para a Vitalmed.
Usa Gemini Pro para raciocínio mais cuidadoso sobre os documentos da knowledge base.
"""
import logging
from pathlib import Path

from agno.agent import Agent
from agno.models.google import Gemini
from src.core.config import settings
from src.agents.doubts.tools import search_knowledge_base

logger = logging.getLogger(__name__)

_CONTEXT_PATH = Path(__file__).parent / "CONTEXT.md"
_DOUBTS_CONTEXT = _CONTEXT_PATH.read_text(encoding="utf-8")

DOUBTS_TOOLS = [search_knowledge_base]


def create_doubts_agent() -> Agent:
    """
    Cria instância do DoubtsAgent.
    Usa Gemini Flash para velocidade nas respostas técnicas.
    """
    return Agent(
        name="DoubtsAgent",
        role="Especialista em produtos e dúvidas técnicas da Vitalmed com acesso à base de conhecimento",
        model=Gemini(id=settings.gemini_flash_model, api_key=settings.google_api_key),
        instructions=_DOUBTS_CONTEXT,
        tools=DOUBTS_TOOLS,
        add_history_to_context=True,
        num_history_runs=5,
        markdown=False,
    )


async def get_doubts_agent() -> Agent:
    return create_doubts_agent()
