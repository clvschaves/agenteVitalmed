from __future__ import annotations
"""
Worker async — processa um job de mensagem em background.
É chamado como BackgroundTask pelo FastAPI após receber a mensagem.

Fluxo:
1. Busca/cria perfil do lead no DB
2. Carrega memória longa (.md) do lead
3. Monta contexto e envia para o RouterAgent (Agno Team)
4. Persiste conversa e atualiza memória
5. Registra trace completo no Langfuse (tokens, custo, latência)
6. Atualiza Redis (status: done)
"""
import json
import logging
from datetime import datetime

import httpx

from src.gateway.redis_client import get_redis
from src.core.a2a import LeadStatus

logger = logging.getLogger(__name__)


async def _send_to_n8n_webhook(
    phone: str,
    name: str | None,
    user_message: str,
    agent_response: str,
    agent_used: str,
    job_id: str,
    chatwoot_conversation_id: str | None = None,
    chatwoot_contact_id: str | None = None,
    voice: bool = False,
    contract_gcs_path: str | None = None,
) -> None:
    """
    Envia a resposta do agente ao webhook n8n para que seja
    encaminhada ao lead via Chatwoot / WhatsApp.
    """
    from src.core.config import settings
    url = settings.n8n_webhook_url
    if not url:
        logger.warning("⚠️  N8N_WEBHOOK_URL não configurado — resposta não enviada ao lead")
        return

    payload = {
        "phone": phone,
        "name": name or "",
        "user_message": user_message,
        "agent_response": agent_response,
        "agent_used": agent_used,
        "job_id": job_id,
        "chatwoot_conversation_id": chatwoot_conversation_id or "",
        "chatwoot_contact_id": chatwoot_contact_id or "",
        "voice": voice,
        "contract_gcs_path": contract_gcs_path or "",
        "sent_at": datetime.utcnow().isoformat(),
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            logger.info(f"📤 Resposta enviada ao n8n | phone={phone} | status={resp.status_code}")
    except Exception as e:
        logger.error(f"❌ Falha ao enviar para n8n webhook | phone={phone} | erro={e}")


async def process_message_job(
    job_id: str,
    session_id: str,
    phone: str,
    message: str,
    name: str | None = None,
    email: str | None = None,
    age: int | None = None,
    source: str | None = "botpress",
    chatwoot_conversation_id: str | None = None,
    chatwoot_contact_id: str | None = None,
    voice: bool = False,
) -> None:
    """
    Processa uma mensagem de lead de forma assíncrona.
    Atualiza o Redis ao final com status 'done' ou 'error'.
    """
    redis = await get_redis()
    from src.integrations.langfuse import ConversationTrace
    from src.core.config import settings

    # Iniciar trace Langfuse logo no início
    ct = ConversationTrace(
        session_id=session_id,
        lead_phone=phone,
        user_message=message,
        lead_name=name,
    )
    ct.__enter__()

    response_text = "Ocorreu um erro interno. Por favor, tente novamente."
    agent_used = "unknown"
    tools_called: list[str] = []
    input_tokens = 0
    output_tokens = 0
    rag_best_score = 0.0
    error_msg = None
    contract_gcs_path: str | None = None

    try:
        # ─── 1. Buscar ou criar perfil do lead no DB ──────────────────────
        lead_profile = await _get_or_create_lead(
            phone=phone, name=name, email=email, age=age, source=source,
            chatwoot_contact_id=chatwoot_contact_id,
            voice=voice,
        )

        # ─── 2. Carregar memória longa do lead (.md) ──────────────────────
        from src.memory.long_term import LongTermMemory
        ltm = LongTermMemory(phone=phone)
        memory_raw = await ltm.load()
        memory_summary = ltm.build_context_summary(memory_raw)

        # ─── 3. Montar mensagem com contexto injetado ─────────────────────
        context_prefix = _build_context_prefix(lead_profile, memory_summary)

        # ─── 3b. Busca RAG proativa — injeta contexto da KB na mensagem ───
        rag_context, rag_best_score = await _fetch_rag_context(message)
        rag_section = f"\n\n{rag_context}" if rag_context else ""

        # ─── 3c. Histrico recente da conversa (resolve perguntas repetidas) ─
        recent_history = await _load_recent_history(
            lead_id=lead_profile["id"],
            session_id=session_id,
            limit=6,
        )
        history_section = ""
        if recent_history:
            history_section = "\n\n## Histórico Recente da Conversa\n" + recent_history

        # ─── Sanity check: mensagem não pode ser vazia ─────────────────────
        # O Gemini rejeita chamadas com contents=[]
        if not message or not message.strip():
            logger.warning(f"⚠️ Mensagem vazia recebida do lead {phone} — ignorando job {job_id}")
            await redis.hset(
                f"job:{job_id}",
                mapping={"status": "done", "response": ""}
            )
            return

        full_message = (
            f"{context_prefix}"
            f"{history_section}"
            f"{rag_section}"
            f"\n\n**Mensagem atual do lead:**\n{message.strip()}"
        ).strip()

        # Fallback final — nunca deve acontecer, mas garante que a string não é vazia
        if not full_message:
            full_message = message.strip() or "Olá"

        # ─── 4. Enviar para o SalesAgent (Gemini Pro — vendas) ────────────
        from src.agents.sales.agent import create_sales_agent

        import asyncio
        loop = asyncio.get_event_loop()

        def _run_sales(use_flash: bool = False):
            agent = create_sales_agent(fallback_flash=use_flash)
            return agent.run(
                full_message,          # posicional — compatível com agno 1.2.6 e 1.3.x
                session_id=session_id,
                user_id=phone,
            )

        try:
            result = await loop.run_in_executor(None, _run_sales)
            agent_used = "sales_pro"
        except Exception as e_pro:
            # Fallback: Gemini Pro indisponível (503/quota/conteúdo vazio) → tenta com Flash
            err_str = str(e_pro).lower()
            if any(k in err_str for k in ["503", "unavailable", "quota", "contents are required"]):
                logger.warning(f"⚠️ Gemini Pro falhou ({e_pro}) — fallback para Flash")
                try:
                    result = await loop.run_in_executor(None, lambda: _run_sales(use_flash=True))
                    agent_used = "sales_flash"
                except Exception as e_flash:
                    raise e_flash
            else:
                raise e_pro

        response_text = _extract_response(result)
        tools_called = _extract_tools(result)

        # ─── 4b. Verificar se o SalesAgent indicou transição para ContractAgent ─
        # Lead em status 'interessado' com tool mark_lead_interested → ContractAgent
        import re as _re
        _tools_str = " ".join(str(t) for t in tools_called)
        _is_contract_phase = any(
            k in _tools_str for k in ["mark_lead_interested", "mark_lead_closed"]
        ) or lead_profile.get("status") in ("interessado", "em_contrato")

        if _is_contract_phase:
            # Roda o ContractAgent para resposta a esta mensagem
            from src.agents.contract.agent import create_contract_agent
            def _run_contract():
                ca = create_contract_agent(session_id=session_id, lead_phone=phone)
                return ca.run(input=message, session_id=session_id, user_id=phone)
            try:
                contract_result = await loop.run_in_executor(None, _run_contract)
                contract_text = _extract_response(contract_result)
                contract_tools = _extract_tools(contract_result)

                # Detectar se o contrato foi gerado (tool generate_and_upload_contract chamada)
                for t in contract_tools:
                    t_str = str(t)
                    if "generate_and_upload_contract" in t_str:
                        # Extrair gcs_path do resultado da tool
                        gcs_match = _re.search(r"gcs_path['"]?:\s*['"]?(gs://[^'"\s,}]+)", t_str)
                        if gcs_match:
                            contract_gcs_path = gcs_match.group(1)

                # Sobrescreve a resposta com a do ContractAgent
                response_text = contract_text
                agent_used = "contract_agent"
                tools_called = contract_tools
            except Exception as e_contract:
                logger.warning(f"⚠️ ContractAgent error: {e_contract} — mantendo resposta do SalesAgent")

        # ─── 5. Extrair tokens do resultado Agno ─────────────────────────
        input_tokens, output_tokens = _extract_tokens(result)

        # ─── 6. Salvar conversa no DB ─────────────────────────────────────
        await _save_conversation(
            lead_id=lead_profile["id"],
            session_id=session_id,
            role="user",
            message=message,
            agent_type=None,
        )
        await _save_conversation(
            lead_id=lead_profile["id"],
            session_id=session_id,
            role="agent",
            message=response_text,
            agent_type=agent_used,
            tools_called=tools_called,
        )

        # ─── 7. Atualizar memória longa (palace) ──────────────────────────
        # hall_events — sempre
        await ltm.append_event(
            event=f"Sessão {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} — lead: {message[:80]}",
        )

        # profile.md — atualiza com dados coletados do lead
        profile_fields: dict = {}
        if lead_profile.get("name"):
            profile_fields["nome"] = lead_profile["name"]
        if lead_profile.get("email"):
            profile_fields["email"] = lead_profile["email"]
        if lead_profile.get("age"):
            profile_fields["idade"] = lead_profile["age"]
        if lead_profile.get("interested_plan"):
            profile_fields["plano_interesse"] = lead_profile["interested_plan"]
        if lead_profile.get("status"):
            profile_fields["status"] = str(lead_profile["status"])
        if profile_fields:
            await ltm.update_profile(**profile_fields)

        # hall_facts — registra quando tools de interesse/fechamento foram chamadas
        import re
        for tool in tools_called:
            tool_str = str(tool)
            # Extrai tool_name do objeto ToolExecution serializado
            match = re.search(r"tool_name='([^']+)'", tool_str)
            tool_name = match.group(1) if match else tool_str[:50]
            if any(k in tool_name for k in ["interested", "closed", "mark_lead"]):
                plan = lead_profile.get("interested_plan") or "nao definido"
                await ltm.append_fact(
                    fact=f"Tool '{tool_name}' executada — plano: {plan}"
                )

        # hall_preferences — detecta objeções e preferências no texto do lead
        msg_lower = message.lower()
        if any(w in msg_lower for w in ["caro", "preço", "valor", "custo", "barato"]):
            await ltm.append_preference("Objeção de preço mencionada")
        if any(w in msg_lower for w in ["pensar", "depois", "mais tarde", "amanhã"]):
            await ltm.append_preference("Lead postergou decisão")
        if any(w in msg_lower for w in ["familia", "filho", "esposa", "marido", "esposo"]):
            await ltm.append_preference("Interesse em plano familiar")
        if any(w in msg_lower for w in ["individual", "so eu", "só eu", "sozinho"]):
            await ltm.append_preference("Interesse em plano individual")

        # ─── 8. Marcar job como concluído no Redis ────────────────────────
        await redis.hset(
            f"job:{job_id}",
            mapping={
                "status": "done",
                "response": response_text,
                "agent_used": agent_used,
                "tools_called": json.dumps(tools_called),
                "contract_gcs_path": contract_gcs_path or "",
            },
        )
        logger.info(f"✅ Job {job_id} | phone={phone} | agent={agent_used} | tokens={input_tokens}+{output_tokens}")

        # ─── 9. Enviar resposta ao n8n webhook (Chatwoot/WhatsApp) ────────
        logger.info(
            f"📤 Enviando ao n8n | phone={phone} | "
            f"chatwoot_conversation_id={chatwoot_conversation_id!r}"
        )
        await _send_to_n8n_webhook(
            phone=phone,
            name=name,
            user_message=message,
            agent_response=response_text,
            agent_used=agent_used,
            job_id=job_id,
            chatwoot_conversation_id=chatwoot_conversation_id,
            chatwoot_contact_id=lead_profile.get("chatwoot_contact_id") or chatwoot_contact_id,
            voice=lead_profile.get("voice", False),
            contract_gcs_path=contract_gcs_path,
        )

    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Erro no job {job_id}: {e}", exc_info=True)
        ct.log_error(error_msg)
        await redis.hset(
            f"job:{job_id}",
            mapping={
                "status": "error",
                "response": "Ocorreu um erro interno. Por favor, tente novamente.",
            },
        )

    finally:
        # ─── 9. Fechar trace Langfuse (sempre — mesmo em erro) ─────────────
        from src.core.config import settings
        ct.finish(
            response=response_text,
            agent_used=agent_used,
            model=settings.gemini_flash_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tools_called=tools_called,
            rag_chunks=4,
            rag_best_score=rag_best_score,
            error=error_msg,
        )
        ct.__exit__(None, None, None)


async def _fetch_rag_context(message: str) -> tuple[str, float]:
    """
    Busca semântica proativa na knowledge base.
    Retorna (contexto_formatado, best_score).
    """
    try:
        from src.rag.retriever import semantic_search
        results = await semantic_search(query=message, top_k=4)

        if not results:
            return "", 0.0

        best_score = results[0]["score"] if results else 0.0
        score_label = "alta" if best_score >= 0.65 else "moderada" if best_score >= 0.50 else "baixa"

        parts = []
        for chunk in results:
            content = chunk.get("content", "").strip()
            if content:
                parts.append(content)

        context_text = "\n\n".join(parts)
        logger.info("RAG proativo: %d chunks | best_score=%.3f", len(results), best_score)

        context_str = (
            f"## Base de Conhecimento Vitalmed (relevância {score_label}: {best_score:.2f})\n"
            f"*Use estas informações para responder ao lead:*\n\n"
            f"{context_text}"
        )
        return context_str, round(best_score, 4)

    except Exception as e:
        logger.warning("Erro no RAG proativo: %s", e)
        return "", 0.0



async def _load_recent_history(lead_id: str, session_id: str, limit: int = 6) -> str:
    """
    Carrega as últimas `limit` mensagens da sessão atual para dar continuidade à conversa.
    Injeta como histórico no contexto do agente — evita perguntas repetidas.
    """
    try:
        from src.db.session import AsyncSessionLocal
        from src.db.models import Conversation
        from sqlalchemy import select
        import uuid

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Conversation)
                .where(
                    Conversation.lead_id == uuid.UUID(lead_id),
                    Conversation.session_id == session_id,
                )
                .order_by(Conversation.created_at.desc())
                .limit(limit)
            )
            rows = result.scalars().all()

        if not rows:
            return ""

        lines = []
        for row in reversed(rows):
            role_label = "Lead" if row.role == "user" else "Carlos"
            lines.append(f"{role_label}: {row.message}")

        return "\n".join(lines)

    except Exception as e:
        logger.debug("Erro ao carregar histórico: %s", e)
        return ""


def _build_context_prefix(lead_profile: dict, memory_summary: str) -> str:
    """Monta o prefixo de contexto do lead para injetar na mensagem."""
    profile_lines = [
        "## Contexto do Lead (para uso interno do agente)",
        f"- **Telefone:** {lead_profile.get('phone', 'N/A')}",
        f"- **Nome:** {lead_profile.get('name') or 'Não informado'}",
        f"- **Email:** {lead_profile.get('email') or 'Não informado'}",
        f"- **Idade:** {lead_profile.get('age') or 'Não informado'}",
        f"- **Status atual:** {lead_profile.get('status', 'novo')}",
        f"- **Plano de interesse:** {lead_profile.get('interested_plan') or 'Não identificado'}",
        f"- **Fonte:** {lead_profile.get('source') or 'N/A'}",
    ]

    context = "\n".join(profile_lines)
    if memory_summary and "Sem dados ainda" not in memory_summary:
        context += f"\n\n{memory_summary}"

    return context



def _extract_response(result) -> str:
    """Extrai o texto de resposta do resultado do Agno Team."""
    if result is None:
        return "Olá! Como posso te ajudar hoje?"

    if hasattr(result, "content") and result.content:
        return str(result.content)

    if hasattr(result, "messages") and result.messages:
        for msg in reversed(result.messages):
            if hasattr(msg, "content") and msg.content:
                return str(msg.content)

    return str(result)


def _extract_tools(result) -> list[str]:
    """Extrai lista de tools invocadas do resultado."""
    tools = []
    try:
        if hasattr(result, "tools") and result.tools:
            tools = [str(t) for t in result.tools]
        elif hasattr(result, "messages"):
            for msg in result.messages:
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        name = getattr(tc, "function", {})
                        if hasattr(name, "name"):
                            tools.append(name.name)
    except Exception:
        pass
    return tools


def _extract_tokens(result) -> tuple[int, int]:
    """
    Extrai contagem de tokens input/output do resultado Agno 1.2.x.
    result.metrics é um dict: {'input_tokens': [N], 'output_tokens': [M], ...}
    """
    try:
        m = getattr(result, "metrics", None)
        if m and isinstance(m, dict):
            # Agno guarda como lista de valores por round — somamos tudo
            input_t  = sum(m.get("input_tokens",  [0]) or [0])
            output_t = sum(m.get("output_tokens", [0]) or [0])
            return input_t, output_t

        # Fallback: varrer messages
        if hasattr(result, "messages"):
            input_t = output_t = 0
            for msg in result.messages:
                mm = getattr(msg, "metrics", None)
                if mm:
                    input_t  += getattr(mm, "input_tokens",  0) or 0
                    output_t += getattr(mm, "output_tokens", 0) or 0
            return input_t, output_t

    except Exception as e:
        logger.debug("Erro ao extrair tokens: %s", e)

    return 0, 0


async def _get_or_create_lead(
    phone: str,
    name: str | None,
    email: str | None,
    age: int | None,
    source: str | None,
    chatwoot_contact_id: str | None = None,
    voice: bool = False,
) -> dict:
    """Busca lead existente ou cria novo registro no banco."""
    from src.db.session import AsyncSessionLocal
    from src.db.models import Lead
    from sqlalchemy import select
    import uuid

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Lead).where(Lead.phone == phone))
        lead = result.scalar_one_or_none()

        if not lead:
            lead = Lead(
                id=uuid.uuid4(),
                phone=phone,
                name=name,
                email=email,
                age=age,
                source=source,
                status=LeadStatus.EM_ATENDIMENTO,
                last_contact_at=datetime.utcnow(),
                chatwoot_contact_id=chatwoot_contact_id,
                voice=voice,
            )
            db.add(lead)
            logger.info(f"🆕 Novo lead criado: {phone}")
        else:
            if name and not lead.name:
                lead.name = name
            if email and not lead.email:
                lead.email = email
            if age and not lead.age:
                lead.age = age
            if chatwoot_contact_id and not lead.chatwoot_contact_id:
                lead.chatwoot_contact_id = chatwoot_contact_id
            # voice: uma vez ativado (True) nunca volta para False
            if voice and not lead.voice:
                lead.voice = True
            lead.status = LeadStatus.EM_ATENDIMENTO
            lead.last_contact_at = datetime.utcnow()

        await db.commit()
        await db.refresh(lead)

        return {
            "id": str(lead.id),
            "phone": lead.phone,
            "name": lead.name,
            "email": lead.email,
            "age": lead.age,
            "status": lead.status,
            "interested_plan": lead.interested_plan,
            "source": lead.source,
            "chatwoot_contact_id": lead.chatwoot_contact_id,
            "voice": bool(lead.voice),
        }


async def _save_conversation(
    lead_id: str,
    session_id: str,
    role: str,
    message: str,
    agent_type: str | None,
    tools_called: list | None = None,
) -> None:
    """Persiste uma mensagem da conversa no banco."""
    from src.db.session import AsyncSessionLocal
    from src.db.models import Conversation
    import uuid

    async with AsyncSessionLocal() as db:
        conv = Conversation(
            id=uuid.uuid4(),
            lead_id=uuid.UUID(lead_id),
            session_id=session_id,
            agent_type=agent_type,
            role=role,
            message=message,
            tools_called=tools_called or [],
        )
        db.add(conv)
        await db.commit()
