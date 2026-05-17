"""
Cliente HTTP para o MCP Server da Vitalmed (Chatwoot).
Chamadas diretas via JSON-RPC 2.0 — sem npx/stdio.

MCP endpoint: https://chat.turninglabs.com.br/mcp/2/mcp-vitalmed
Auth: Api-Access-Token header
"""
from __future__ import annotations

import logging
import uuid

import httpx

logger = logging.getLogger(__name__)

MCP_URL = "https://chat.turninglabs.com.br/mcp/2/mcp-vitalmed"
MCP_TOKEN = "uFxBcgk62MsxB4x1Xg26GSRR"

_HEADERS = {
    "Api-Access-Token": MCP_TOKEN,
    "Content-Type": "application/json",
}


async def _call_tool(tool_name: str, arguments: dict) -> dict:
    """Executa um tool no MCP Server via JSON-RPC 2.0."""
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(MCP_URL, json=payload, headers=_HEADERS)
        resp.raise_for_status()
        return resp.json()


async def add_contact_label(contact_id: str, label: str) -> bool:
    """
    Adiciona uma label ao contato no Chatwoot via MCP.

    Usa contact_labels_set (POST /contacts/:contact_id/labels).
    A API do Chatwoot substitui todas as labels — precisamos preservar as existentes.

    Args:
        contact_id: ID do contato no Chatwoot (chatwoot_contact_id)
        label: nome da label a adicionar (ex: "contratos_gerados")

    Returns:
        True se sucesso, False se falhou
    """
    if not contact_id:
        logger.warning("⚠️ MCP: contact_id vazio — label '%s' não adicionada", label)
        return False

    try:
        # 1. Buscar labels atuais para não sobrescrever
        existing_result = await _call_tool(
            "contact_labels_list",
            {"contact_id": str(contact_id)},
        )
        existing_labels: list[str] = []
        try:
            import json as _json
            content = existing_result.get("result", {}).get("content", [])
            if content:
                body_text = content[0].get("text", "{}")
                body = _json.loads(body_text)
                existing_labels = body.get("body", {}).get("payload", [])
        except Exception:
            pass  # Se não conseguir ler, continua com lista vazia

        # 2. Mesclar: adiciona a nova label sem duplicar
        if label not in existing_labels:
            new_labels = existing_labels + [label]
        else:
            logger.info("🏷️ MCP: label '%s' já existe no contato %s", label, contact_id)
            return True

        # 3. Enviar a lista atualizada
        result = await _call_tool(
            "contact_labels_set",
            {
                "contact_id": str(contact_id),
                "body": {"labels": new_labels},
            },
        )

        # Verificar sucesso
        import json as _json
        content = result.get("result", {}).get("content", [])
        if content:
            body_text = content[0].get("text", "{}")
            body = _json.loads(body_text)
            ok = body.get("ok", False) or body.get("status") == 200
            if ok:
                final_labels = body.get("body", {}).get("payload", [])
                logger.info(
                    "🏷️ MCP: label '%s' adicionada ao contato %s | labels atuais: %s",
                    label, contact_id, final_labels,
                )
                return True

        logger.warning("⚠️ MCP: resposta inesperada ao adicionar label: %s", result)
        return False

    except Exception as e:
        logger.error("❌ MCP: falha ao adicionar label '%s' no contato %s: %s", label, contact_id, e)
        return False


async def add_conversation_label(conversation_id: str, label: str) -> bool:
    """
    Adiciona uma label à conversa no Chatwoot via MCP.

    Args:
        conversation_id: ID da conversa no Chatwoot (chatwoot_conversation_id)
        label: nome da label (ex: "contratos_gerados")
    """
    if not conversation_id:
        logger.warning("⚠️ MCP: conversation_id vazio — label '%s' não adicionada", label)
        return False

    try:
        # 1. Buscar labels atuais
        existing_result = await _call_tool(
            "conversations_get_labels",
            {"conversation_id": str(conversation_id)},
        )
        existing_labels: list[str] = []
        try:
            import json as _json
            content = existing_result.get("result", {}).get("content", [])
            if content:
                body_text = content[0].get("text", "{}")
                body = _json.loads(body_text)
                existing_labels = body.get("body", {}).get("payload", [])
        except Exception:
            pass

        if label not in existing_labels:
            new_labels = existing_labels + [label]
        else:
            return True

        # 2. Enviar lista atualizada
        result = await _call_tool(
            "conversations_set_labels",
            {
                "conversation_id": str(conversation_id),
                "body": {"labels": new_labels},
            },
        )

        import json as _json
        content = result.get("result", {}).get("content", [])
        if content:
            body_text = content[0].get("text", "{}")
            body = _json.loads(body_text)
            ok = body.get("ok", False) or body.get("status") == 200
            if ok:
                logger.info(
                    "🏷️ MCP: label '%s' adicionada à conversa %s",
                    label, conversation_id,
                )
                return True

        return False

    except Exception as e:
        logger.error("❌ MCP: falha ao adicionar label na conversa %s: %s", conversation_id, e)
        return False
