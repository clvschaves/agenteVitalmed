from __future__ import annotations
"""
Tools do DoubtsAgent e AssistantAgent — busca semântica na knowledge base RAG.

IMPORTANTE: Agno 1.2.x exige que tools retornem STRING.
Retornar dict causa ValidationError no Message.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


def _run(coro):
    """
    Executa coroutine de forma síncrona dentro de thread executor do agno.

    O agno 2.5.x executa tools via ThreadPoolExecutor — threads que NAO tem
    event loop ativo. asyncio.get_event_loop() lanca RuntimeError nesses casos.
    asyncio.run() cria um novo event loop na thread e e a solucao correta.
    """
    try:
        return asyncio.run(coro)
    except Exception as e:
        logger.error(f"Erro em _run (doubts tools): {e}")
        raise


def search_knowledge_base(query: str, top_k: int = 5) -> str:
    """
    Busca informações sobre produtos, planos, preços e serviços da Vitalmed.

    Use SEMPRE que o lead perguntar sobre:
    - Produtos e planos (UTI Móvel, Plano Família, Área Protegida, etc.)
    - Preços e valores mensais
    - Coberturas, carência, reembolso
    - O que é a Vitalmed e seus serviços
    - Protocolo de atendimento e emergências
    - Comparações entre planos

    Args:
        query: Termos de busca relacionados à pergunta do lead
        top_k: Número de trechos a retornar (padrão 5)

    Returns:
        Texto com as informações encontradas na base de conhecimento,
        ou mensagem informando que não há dados disponíveis.
    """
    async def _impl():
        from src.rag.retriever import semantic_search
        from src.core.config import settings

        try:
            results = await semantic_search(query=query, top_k=top_k)

            if not results:
                return (
                    "RESULTADO DA BASE DE CONHECIMENTO:\n"
                    "Nenhuma informação encontrada para esta consulta.\n"
                    "Recomendo transferir para um especialista humano."
                )

            best_score = results[0]["score"] if results else 0.0

            # Sempre retornar o contexto — o modelo decide a relevância
            score_label = "alta" if best_score >= 0.65 else "moderada" if best_score >= 0.50 else "baixa"
            return (
                f"RESULTADO DA BASE DE CONHECIMENTO (relevância {score_label}: {best_score:.2f}):\n\n"
                + _format_chunks(results)
            )


        except Exception as e:
            logger.error(f"Erro na busca RAG: {e}", exc_info=True)
            return f"Erro ao acessar base de conhecimento: {e}. Use as informações disponíveis ou transfira para humano."

    return _run(_impl())


def _format_chunks(chunks: list[dict]) -> str:
    """Formata os chunks recuperados como texto de contexto para o LLM."""
    if not chunks:
        return "Nenhuma informação encontrada."

    parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source_file", "documento").replace(".pdf", "")
        page = chunk.get("page_number", "")
        page_info = f" | pág. {page}" if page else ""
        score = chunk.get("score", 0)
        parts.append(
            f"[Trecho {i} — {source}{page_info} | score: {score:.2f}]\n"
            f"{chunk['content']}"
        )

    return "\n\n---\n\n".join(parts)
