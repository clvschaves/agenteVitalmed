from __future__ import annotations
"""
Tools do DoubtsAgent e AssistantAgent — busca semântica na knowledge base RAG.

IMPORTANTE: Agno executa tools em ThreadPoolExecutor (threads síncronas).
Usar asyncio.run() ou AsyncSession de dentro de uma thread causa:
    RuntimeError: Future attached to a different loop

Solução: usar semantic_search_sync() — 100% síncrona, sem asyncio.
"""
import logging

logger = logging.getLogger(__name__)


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
    from src.rag.retriever import semantic_search_sync

    try:
        results = semantic_search_sync(query=query, top_k=top_k)

        if not results:
            return (
                "RESULTADO DA BASE DE CONHECIMENTO:\n"
                "Nenhuma informação encontrada para esta consulta.\n"
                "Recomendo transferir para um especialista humano."
            )

        best_score = results[0]["score"] if results else 0.0
        score_label = "alta" if best_score >= 0.65 else "moderada" if best_score >= 0.50 else "baixa"

        return (
            f"RESULTADO DA BASE DE CONHECIMENTO (relevância {score_label}: {best_score:.2f}):\n\n"
            + _format_chunks(results)
        )

    except Exception as e:
        logger.error(f"Erro na busca RAG: {e}", exc_info=True)
        return f"Erro ao acessar base de conhecimento: {e}. Use as informações disponíveis ou transfira para humano."


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
