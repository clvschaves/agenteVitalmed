"""
ContractAgent — coleta dados do usuário, gera e sobe o contrato para o GCS.
"""
import logging
from pathlib import Path

from agno.agent import Agent
from agno.models.google import Gemini

from src.core.config import settings
from src.agents.contract.tools import generate_and_upload_contract

logger = logging.getLogger(__name__)

_CONTEXT_PATH = Path(__file__).parent / "CONTEXT.md"


def create_contract_agent(session_id: str, lead_phone: str) -> Agent:
    """Cria uma instância do ContractAgent com histórico de sessão."""
    instructions = _CONTEXT_PATH.read_text(encoding="utf-8")

    return Agent(
        name="contract_agent",
        model=Gemini(id=settings.gemini_flash_model, api_key=settings.gemini_api_key),
        instructions=instructions,
        tools=[generate_and_upload_contract],
        session_id=session_id,
        add_history_to_context=True,
        num_history_responses=20,
        markdown=False,
        show_tool_calls=False,
    )
