from __future__ import annotations
"""
Retriever — busca semântica no pgvector usando similaridade coseno.
"""
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def semantic_search(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """
    Busca semântica na base de conhecimento RAG.

    1. Gera embedding da query (task_type=RETRIEVAL_QUERY)
    2. Busca no pgvector os top_k chunks mais similares (cosine distance)
    3. Retorna com score normalizado [0, 1] onde 1 = idêntico

    Args:
        query: Pergunta do lead em linguagem natural
        top_k: Número de chunks a retornar

    Returns:
        list de dicts com content, source_file, page, score
    """
    from src.rag.embedder import embed_query

    query_embedding = await embed_query(query)
    results = await _vector_search(query_embedding, top_k)

    if results:
        logger.debug(f"RAG: '{query[:60]}' | {len(results)} resultados | best={results[0]['score']:.3f}")
    else:
        logger.debug(f"RAG: '{query[:60]}' | sem resultados")

    return results


async def _vector_search(
    query_embedding: list[float],
    top_k: int,
) -> list[dict[str, Any]]:
    """
    Executa busca vetorial coseno no pgvector.
    Filtra apenas chunks ativos e ordena por menor distância coseno.
    """
    from src.db.session import AsyncSessionLocal
    from src.db.models import KnowledgeChunk
    from sqlalchemy import select, text

    async with AsyncSessionLocal() as db:
        # pgvector: <=> é distância coseno (0 = idêntico, 2 = oposto)
        # Convertemos para similaridade: score = 1 - (distance / 2)
        query = text("""
            SELECT
                id,
                content,
                source_file,
                doc_type,
                section_title,
                page_number,
                video_timestamp,
                1 - (embedding <=> CAST(:embedding AS vector)) AS score
            FROM knowledge_chunks
            WHERE is_active = true
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
        """)

        result = await db.execute(
            query,
            {"embedding": str(query_embedding), "top_k": top_k},
        )
        rows = result.fetchall()

    return [
        {
            "id": str(row.id),
            "content": row.content,
            "source_file": row.source_file,
            "doc_type": row.doc_type,
            "section_title": row.section_title,
            "page_number": row.page_number,
            "video_timestamp": row.video_timestamp,
            "score": float(row.score),
        }
        for row in rows
    ]
