from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime


@dataclass
class A2AMessage:
    """
    Mensagem padrão do protocolo Agent-to-Agent (A2A).
    Usada para comunicação entre RouterAgent, AssistantAgent e DoubtsAgent.
    Cada agente conhece apenas seus vizinhos imediatos (N2N).
    """

    from_agent: str          # "router" | "assistant" | "doubts"
    to_agent: str            # "router" | "assistant" | "doubts" | "human"
    lead_phone: str          # identificador do lead (chave)
    session_id: str          # f"{phone}_{date}" — chave de sessão única
    content: str             # mensagem do usuário OU instrução do agente
    context: dict = field(default_factory=dict)   # perfil do lead + histórico
    metadata: dict = field(default_factory=dict)  # reason, urgency, flags
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "lead_phone": self.lead_phone,
            "session_id": self.session_id,
            "content": self.content,
            "context": self.context,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "A2AMessage":
        return cls(**data)


# ─── Motivos de escalação padronizados ────────────────────────────────────────

class EscalationReason:
    RAG_NO_MATCH = "rag_sem_resposta"          # score RAG < threshold
    USER_REQUESTED = "solicitacao_usuario"      # lead pediu atendente
    COMPLAINT = "reclamacao_seria"             # palavras-chave críticas
    LOOP_DETECTED = "loop_sem_progresso"       # 3+ msgs sem avanço
    SPECIAL_CONDITION = "condicao_especial"    # desconto, exceção


# ─── Status do lead ───────────────────────────────────────────────────────────

class LeadStatus:
    NOVO = "novo"
    CONTACTADO = "contactado"
    SEM_RETORNO = "sem_retorno"
    EM_ATENDIMENTO = "em_atendimento"
    ESCALADO = "escalado"
    INTERESSADO = "interessado"
    FECHADO = "fechado"
    NAO_INTERESSADO = "nao_interessado"
    PERDIDO = "perdido"
