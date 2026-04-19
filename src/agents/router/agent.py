from __future__ import annotations
"""
RouterAgent — Orquestrador central do sistema Vitalmed.
Usa Agno Team para coordenar AssistantAgent e DoubtsAgent via protocolo A2A.
"""
import logging
from pathlib import Path

from agno.agent import Agent
from agno.team import Team
from agno.models.google import Gemini

from src.core.config import settings
from src.agents.assistant.agent import create_assistant_agent
from src.agents.doubts.agent import create_doubts_agent

logger = logging.getLogger(__name__)

_CONTEXT_PATH = Path(__file__).parent / "CONTEXT.md"
_ROUTER_CONTEXT = _CONTEXT_PATH.read_text(encoding="utf-8")


def create_router_team(lead_memory_summary: str = "") -> Team:
    """
    Cria o Agno Team com RouterAgent como líder.
    O router coordena o AssistantAgent e DoubtsAgent via modo route.

    O Team usa Gemini Flash para o roteamento (decisão rápida e barata).
    Os membros usam seus próprios modelos (Flash para assistant, Pro para doubts).
    """
    assistant = create_assistant_agent(lead_memory_summary)
    doubts = create_doubts_agent()

    team = Team(
        name="VitalmedTeam",
        mode="route",           # Router decide qual membro responde
        model=Gemini(id=settings.gemini_flash_model, api_key=settings.google_api_key),
        members=[assistant, doubts],
        instructions=_ROUTER_CONTEXT,
        enable_agentic_context=True,   # Compartilha contexto entre membros
    )

    return team


async def get_router_agent(lead_memory_summary: str = "") -> Team:
    """Async factory — retorna o Team configurado."""
    return create_router_team(lead_memory_summary)
