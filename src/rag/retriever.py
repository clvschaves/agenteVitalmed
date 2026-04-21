from __future__ import annotations
"""
Retriever — busca semântica no pgvector usando similaridade coseno.

Dois modos:
- semantic_search()      → async, para uso no FastAPI / worker principal
- semantic_search_sync() → sync, para uso nas tools do agente (ThreadPoolExecutor)
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ─── SQL compartilhado ────────────────────────────────────────────────────────
_RAG_SQL = """
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
"""


def _rows_to_dicts(rows) -> list[dict[str, Any]]:
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


# ─── Versão ASYNC (FastAPI / worker proativo) ─────────────────────────────────

async def semantic_search(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """
    Busca semântica async — para uso no contexto assíncrono do FastAPI.
    NÃO chamar de dentro de um ThreadPoolExecutor.
    """
    from src.rag.embedder import embed_query
    from src.db.session import AsyncSessionLocal
    from sqlalchemy import text

    query_embedding = await embed_query(query)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text(_RAG_SQL),
            {"embedding": str(query_embedding), "top_k": top_k},
        )
        rows = result.fetchall()

    results = _rows_to_dicts(rows)
    if results:
        logger.debug(f"RAG async: '{query[:60]}' | {len(results)} resultados | best={results[0]['score']:.3f}")
    else:
        logger.debug(f"RAG async: '{query[:60]}' | sem resultados")
    return results


# ─── Versão SÍNCRONA (agente tools → ThreadPoolExecutor) ─────────────────────

def semantic_search_sync(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """
    Versão 100% síncrona do RAG — segura para tools do agente.

    As tools do agno rodam em ThreadPoolExecutor. Tentar usar asyncio.run() ou
    AsyncSession dentro de uma thread causa:
        RuntimeError: Future attached to a different loop
    Esta função usa apenas código síncrono:
    - google.genai síncrono para embedding
    - SyncSessionLocal (psycopg2) para query no pgvector
    """
    from src.core.config import settings
    from src.db.session import SyncSessionLocal
    from sqlalchemy import text
    import google.genai as genai

    # 1. Embedding síncrono
    try:
        client = genai.Client(api_key=settings.google_api_key)
        result = client.models.embed_content(
            model=settings.embedding_model,
            contents=query,
            config={
                "task_type": "RETRIEVAL_QUERY",
                "output_dimensionality": 768,
            },
        )
        query_embedding = result.embeddings[0].values
    except Exception as e:
        logger.error(f"[RAG sync] Erro ao gerar embedding: {e}", exc_info=True)
        raise

    # 2. Busca vetorial síncrona
    with SyncSessionLocal() as db:
        rows = db.execute(
            text(_RAG_SQL),
            {"embedding": str(query_embedding), "top_k": top_k},
        ).fetchall()

    results = _rows_to_dicts(rows)
    if results:
        logger.info(f"[RAG sync] '{query[:60]}' | {len(results)} resultados | best={results[0]['score']:.3f}")
    else:
        logger.info(f"[RAG sync] '{query[:60]}' | sem resultados")
    return results
