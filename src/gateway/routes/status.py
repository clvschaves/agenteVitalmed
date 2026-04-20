from __future__ import annotations
"""
GET /webhook/status/{job_id} — polling de status do job.
O Botpress consulta essa rota até receber status "done" ou "error".
"""
import json
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from src.gateway.redis_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter()


class JobStatusResponse(BaseModel):
    """Resposta do polling — idêntica ao padrão Promise do Node.js."""
    job_id: str
    status: str                  # "processing" | "done" | "error"
    response: str | None = None  # Texto de resposta do agente (quando done)
    agent_used: str | None = None
    tools_called: list[str] = []
    session_id: str | None = None
    chatwoot_conversation_id: str | None = None  # ← sempre retornado para rastreamento


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, redis=Depends(get_redis)):
    """
    Consulta o status de um job em processamento.

    - **processing**: o agente ainda está gerando a resposta
    - **done**: resposta pronta em `response`
    - **error**: falha no processamento (detalhes em `response`)

    O Botpress deve fazer polling a cada 3-5 segundos.
    Após 5 minutos (TTL), o job expira automaticamente do Redis.
    """
    job_data = await redis.hgetall(f"job:{job_id}")

    if not job_data:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' não encontrado ou expirado (TTL 5min).",
        )

    # Deserializar tools_called (armazenado como JSON string)
    tools_called = []
    try:
        tools_raw = job_data.get("tools_called", "[]")
        tools_called = json.loads(tools_raw) if tools_raw else []
    except json.JSONDecodeError:
        pass

    return JobStatusResponse(
        job_id=job_id,
        status=job_data.get("status", "processing"),
        response=job_data.get("response") or None,
        agent_used=job_data.get("agent_used") or None,
        tools_called=tools_called,
        session_id=job_data.get("session_id") or None,
        chatwoot_conversation_id=job_data.get("chatwoot_conversation_id") or None,
    )

