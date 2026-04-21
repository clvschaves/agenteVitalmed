from __future__ import annotations
"""
Tools do AssistantAgent — operações de banco, Chatwoot e memória.

IMPORTANTE: O Agno 1.2.x chama tools de forma SÍNCRONA via ThreadPoolExecutor.
            Usar asyncio.run() dentro de thread causa conflito com o loop do uvicorn
            (asyncpg connections pertencem ao loop principal).
            SOLUÇÃO: usar SyncSessionLocal (psycopg2) — totalmente síncrono, sem loop.
"""
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


# ─── Sessão síncrona — usada por TODAS as tools ──────────────────────────────
def _get_sync_db():
    """Retorna uma sessão síncrona (psycopg2). Deve ser fechada pelo chamador."""
    from src.db.session import SyncSessionLocal
    return SyncSessionLocal()


def get_lead_profile(phone: str) -> dict:
    """Busca o perfil completo do lead no banco de dados."""
    from src.db.models import Lead
    from sqlalchemy import select

    db = _get_sync_db()
    try:
        lead = db.execute(select(Lead).where(Lead.phone == phone)).scalar_one_or_none()
        if not lead:
            return {"phone": phone, "status": "novo"}
        return {
            "phone": lead.phone,
            "name": lead.name,
            "email": lead.email,
            "age": lead.age,
            "status": lead.status,
            "interested_plan": lead.interested_plan,
            "source": lead.source,
            "last_contact_at": str(lead.last_contact_at),
        }
    except Exception as e:
        logger.error(f"get_lead_profile error: {e}")
        return {"phone": phone, "status": "novo"}
    finally:
        db.close()


def update_lead_status(phone: str, new_status: str, reason: str = "") -> bool:
    """
    Atualiza o status do lead no banco e registra no histórico.
    Statuses válidos: novo, contactado, sem_retorno, em_atendimento,
                      escalado, interessado, fechado, nao_interessado, perdido
    """
    from src.db.models import Lead, LeadStatusHistory
    from sqlalchemy import select

    VALID_STATUSES = {
        "novo", "contactado", "sem_retorno", "em_atendimento",
        "escalado", "interessado", "fechado", "nao_interessado", "perdido"
    }
    if new_status not in VALID_STATUSES:
        logger.warning(f"Status inválido: {new_status}")
        return False

    db = _get_sync_db()
    try:
        lead = db.execute(select(Lead).where(Lead.phone == phone)).scalar_one_or_none()
        if not lead:
            return False

        old_status = lead.status
        lead.status = new_status
        lead.updated_at = datetime.utcnow()

        history = LeadStatusHistory(
            id=uuid.uuid4(),
            lead_id=lead.id,
            old_status=str(old_status),
            new_status=new_status,
            reason=reason,
        )
        db.add(history)
        db.commit()

        logger.info(f"📊 Status: {phone} | {old_status} → {new_status}")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"update_lead_status error: {e}")
        return False
    finally:
        db.close()


def save_lead_interest(phone: str, plan: str) -> bool:
    """Registra o plano de interesse do lead no banco."""
    from src.db.models import Lead
    from sqlalchemy import select

    db = _get_sync_db()
    try:
        lead = db.execute(select(Lead).where(Lead.phone == phone)).scalar_one_or_none()
        if not lead:
            return False
        lead.interested_plan = plan
        lead.updated_at = datetime.utcnow()
        db.commit()
        logger.info(f"⭐ Interesse: {phone} → {plan}")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"save_lead_interest error: {e}")
        return False
    finally:
        db.close()


def transfer_to_human(phone: str, reason: str) -> str:
    """
    Escala a conversa para um atendente humano.
    Use quando o lead solicitar falar com humano ou situação complexa.
    """
    update_lead_status(phone, "escalado", reason)
    logger.info(f"[CHATWOOT STUB] transfer_to_human | phone={phone} | reason={reason}")
    return f"Transferência solicitada para humano. Motivo: {reason}"


def mark_lead_interested(phone: str, plan: str) -> str:
    """
    Marca lead como interessado: salva plano + atualiza status.
    Use quando o lead confirmar interesse no fechamento.
    """
    save_lead_interest(phone, plan)
    update_lead_status(phone, "interessado", f"Interesse confirmado: {plan}")
    logger.info(f"🎯 Interessado: {phone} | plano={plan}")
    return f"Lead marcado como interessado no plano: {plan}"


def mark_lead_closed(phone: str, plan: str) -> str:
    """
    Marca lead como fechado (venda concluída).
    Use quando o lead confirmar a contratação do plano.
    """
    save_lead_interest(phone, plan)
    update_lead_status(phone, "fechado", f"Venda fechada: {plan}")
    logger.info(f"✅ Fechado: {phone} | plano={plan}")
    return f"Parabéns! Lead marcado como cliente. Plano: {plan}"


def mark_lead_no_return(phone: str, reason: str = "Sem resposta após contato") -> str:
    """
    Marca lead como sem_retorno para recontato futuro.
    Use quando o lead não responder após múltiplas tentativas.
    """
    update_lead_status(phone, "sem_retorno", reason)
    logger.info(f"📵 Sem retorno: {phone}")
    return f"Lead salvo como sem_retorno. Poderá ser recontactado futuramente."
