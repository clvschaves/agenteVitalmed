from __future__ import annotations
"""
Integração com a API do Chatwoot.

MODO LOCAL (CHATWOOT_LOCAL_MODE=true):
  Todas as operações são logadas localmente sem fazer chamadas reais.
  Útil para testar os agentes sem depender de uma instância Chatwoot.

MODO PRODUÇÃO (CHATWOOT_LOCAL_MODE=false):
  Faz chamadas reais à API do Chatwoot configurada no .env.
"""
import logging
import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)

BASE_URL = f"{settings.chatwoot_api_url}/api/v1/accounts/{settings.chatwoot_account_id}"
HEADERS = {
    "api_access_token": settings.chatwoot_api_token,
    "Content-Type": "application/json",
}

LOCAL_MODE = settings.chatwoot_local_mode


def _log_stub(action: str, **kwargs):
    """Log de stub para modo local — simula as chamadas sem fazer requests reais."""
    params = " | ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info(f"[CHATWOOT STUB] {action} | {params}")


async def add_label(conversation_id: str, label: str) -> bool:
    if LOCAL_MODE:
        _log_stub("add_label", conversation_id=conversation_id, label=label)
        return True

    url = f"{BASE_URL}/conversations/{conversation_id}/labels"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=HEADERS, json={"labels": [label]})
            resp.raise_for_status()
            logger.info(f"🏷️  Label '{label}' adicionada | conversation={conversation_id}")
            return True
    except httpx.HTTPError as e:
        logger.error(f"Erro ao adicionar label Chatwoot: {e}")
        return False


async def transfer_to_human(conversation_id: str, reason: str = "Escalado pelo agente") -> bool:
    if LOCAL_MODE:
        _log_stub("transfer_to_human", conversation_id=conversation_id, reason=reason)
        return True

    success = await add_label(conversation_id, settings.chatwoot_label_escalated)
    notes_url = f"{BASE_URL}/conversations/{conversation_id}/messages"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(notes_url, headers=HEADERS, json={
                "content": f"⚠️ Agente IA escalou para humano. Motivo: {reason}",
                "message_type": "activity",
                "private": True,
            })
    except httpx.HTTPError:
        pass

    logger.info(f"👤 Transferido para humano | conversation={conversation_id} | motivo={reason}")
    return success


async def mark_as_interested(conversation_id: str) -> bool:
    if LOCAL_MODE:
        _log_stub("mark_as_interested", conversation_id=conversation_id)
        return True
    return await add_label(conversation_id, settings.chatwoot_label_interested)


async def mark_as_closed(conversation_id: str) -> bool:
    if LOCAL_MODE:
        _log_stub("mark_as_closed", conversation_id=conversation_id)
        return True
    return await add_label(conversation_id, settings.chatwoot_label_closed)


async def get_conversation_id_by_phone(phone: str) -> str | None:
    if LOCAL_MODE:
        # Retorna ID fictício para testes locais
        _log_stub("get_conversation_id_by_phone", phone=phone)
        return f"local-conv-{phone}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            search_url = f"{BASE_URL}/contacts/search"
            resp = await client.get(
                search_url, headers=HEADERS, params={"q": phone, "page": 1}
            )
            resp.raise_for_status()
            data = resp.json()
            contacts = data.get("payload", {}).get("contacts", [])
            if contacts:
                contact_id = contacts[0]["id"]
                conv_url = f"{BASE_URL}/contacts/{contact_id}/conversations"
                conv_resp = await client.get(conv_url, headers=HEADERS)
                conv_resp.raise_for_status()
                convs = conv_resp.json().get("payload", [])
                if convs:
                    return str(convs[0]["id"])
    except Exception as e:
        logger.error(f"Erro ao buscar conversa Chatwoot para {phone}: {e}")
    return None
