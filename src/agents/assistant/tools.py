from __future__ import annotations
"""
Tools do AssistantAgent — operações de banco, Chatwoot e memória.

IMPORTANTE: O Agno 1.2.x chama tools de forma SÍNCRONA.
Todas as tools aqui são síncronas e usam asyncio internamente.
"""
import asyncio
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


def _run(coro):
    """
    Helper: executa coroutine de forma sincrona dentro de thread do agno.

    O agno 2.5.x executa tools via ThreadPoolExecutor — threads sem event loop.
    asyncio.run() cria um novo event loop na thread (solucao correta para Python 3.10+).
    """
    try:
        return asyncio.run(coro)
    except Exception as e:
        logger.error(f"Erro em _run: {e}")
        raise


def get_lead_profile(phone: str) -> dict:
    """Busca o perfil completo do lead no banco de dados."""
    async def _impl():
        from src.db.session import AsyncSessionLocal
        from src.db.models import Lead
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Lead).where(Lead.phone == phone))
            lead = result.scalar_one_or_none()
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
    return _run(_impl())


def update_lead_status(phone: str, new_status: str, reason: str = "") -> bool:
    """
    Atualiza o status do lead no banco e registra no histórico.
    Statuses válidos: novo, contactado, sem_retorno, em_atendimento,
                      escalado, interessado, fechado, nao_interessado, perdido
    """
    async def _impl():
        from src.db.session import AsyncSessionLocal
        from src.db.models import Lead, LeadStatusHistory
        from sqlalchemy import select

        VALID_STATUSES = {
            "novo", "contactado", "sem_retorno", "em_atendimento",
            "escalado", "interessado", "fechado", "nao_interessado", "perdido"
        }
        if new_status not in VALID_STATUSES:
            logger.warning(f"Status inválido: {new_status}")
            return False

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Lead).where(Lead.phone == phone))
            lead = result.scalar_one_or_none()
            if not lead:
                return False

            old_status = lead.status
            lead.status = new_status
            lead.updated_at = datetime.utcnow()

            history = LeadStatusHistory(
                id=uuid.uuid4(),
                lead_id=lead.id,
                old_status=old_status,
                new_status=new_status,
                reason=reason,
            )
            db.add(history)
            await db.commit()

        logger.info(f"📊 Status: {phone} | {old_status} → {new_status}")
        return True

    return _run(_impl())


def save_lead_interest(phone: str, plan: str) -> bool:
    """Registra o plano de interesse do lead no banco."""
    async def _impl():
        from src.db.session import AsyncSessionLocal
        from src.db.models import Lead
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Lead).where(Lead.phone == phone))
            lead = result.scalar_one_or_none()
            if not lead:
                return False
            lead.interested_plan = plan
            lead.updated_at = datetime.utcnow()
            await db.commit()

        logger.info(f"⭐ Interesse: {phone} → {plan}")
        return True

    return _run(_impl())


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
