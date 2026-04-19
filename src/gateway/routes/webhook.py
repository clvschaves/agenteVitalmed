from __future__ import annotations
"""
POST /webhook/message — ponto de entrada das mensagens do Botpress/Chatwoot.
Recebe a mensagem, gera um job_id e dispara o processamento em background.
Retorna imediatamente com o job_id para o Botpress fazer polling.
"""
import uuid
import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel

from src.gateway.worker import process_message_job
from src.gateway.redis_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter()


class IncomingMessage(BaseModel):
    """Payload enviado pelo Botpress ao webhook."""
    phone: str                      # Ex: "5511999999999"
    name: str | None = None
    email: str | None = None
    age: int | None = None
    message: str                    # Texto da mensagem do lead
    source: str | None = "botpress" # Origem do lead
    chatwoot_conversation_id: str | None = None  # ID da conversa no Chatwoot


class WebhookResponse(BaseModel):
    """Resposta imediata — o Botpress usa o job_id para polling."""
    job_id: str
    status: str = "processing"
    message: str = "Mensagem recebida. Use o job_id para consultar a resposta."


@router.post("/message", response_model=WebhookResponse)
async def receive_message(
    payload: IncomingMessage,
    background_tasks: BackgroundTasks,
    redis=Depends(get_redis),
):
    """
    Recebe mensagem do lead via Botpress.
    1. Gera job_id único
    2. Salva estado inicial no Redis (status: processing)
    3. Dispara processamento em background (não bloqueia)
    4. Retorna job_id imediatamente (< 200ms)
    """
    job_id = str(uuid.uuid4())
    session_id = f"{payload.phone}_{datetime.utcnow().strftime('%Y%m%d')}"

    # Estado inicial no Redis com TTL
    job_data = {
        "status": "processing",
        "response": "",
        "agent_used": "",
        "tools_called": "[]",
        "created_at": datetime.utcnow().isoformat(),
        "session_id": session_id,
        "lead_phone": payload.phone,
    }

    from src.core.config import settings
    await redis.hset(f"job:{job_id}", mapping=job_data)
    await redis.expire(f"job:{job_id}", settings.job_ttl_seconds)

    logger.info(f"📩 Mensagem recebida | phone={payload.phone} | job_id={job_id}")

    # Processar em background sem bloquear a resposta
    background_tasks.add_task(
        process_message_job,
        job_id=job_id,
        session_id=session_id,
        phone=payload.phone,
        name=payload.name,
        email=payload.email,
        age=payload.age,
        message=payload.message,
        source=payload.source,
        chatwoot_conversation_id=payload.chatwoot_conversation_id,
    )

    return WebhookResponse(job_id=job_id)
