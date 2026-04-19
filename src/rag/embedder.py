from __future__ import annotations
"""
Embedder — gera embeddings com gemini-embedding-001 e salva no pgvector.
Usa a nova API google.genai (google-genai>=1.x).
"""
import asyncio
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

BATCH_SIZE = 20   # Google API suporta até 100 por chamada
EMBED_DIM = 768   # output_dimensionality=768 com gemini-embedding-001 (compatível com ivfflat)


async def embed_and_save_chunks(chunks: list[dict]) -> int:
    """
    Gera embeddings para todos os chunks e persiste no PostgreSQL/pgvector.

    Args:
        chunks: Lista de dicts com {content, source_file, doc_type, ...}

    Returns:
        Número de chunks salvos com sucesso.
    """
    saved_count = 0
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i: i + BATCH_SIZE]
        texts = [c["content"] for c in batch]

        try:
            embeddings = await _embed_batch(texts)
            saved = await _save_batch(batch, embeddings)
            saved_count += saved
            logger.debug(f"Batch {i // BATCH_SIZE + 1}: {saved} chunks salvos")
            await asyncio.sleep(0.2)   # respeitar rate limit

        except Exception as e:
            logger.error(f"Erro no batch {i // BATCH_SIZE + 1}: {e}", exc_info=True)

    return saved_count


async def _embed_batch(texts: list[str]) -> list[list[float]]:
    """Gera embeddings para uma lista de textos via gemini-embedding-001."""
    from src.core.config import settings
    import google.genai as genai

    loop = asyncio.get_event_loop()

    def _sync_embed():
        client = genai.Client(api_key=settings.google_api_key)
        result = client.models.embed_content(
            model=settings.embedding_model,
            contents=texts,
            config={
                "task_type": "RETRIEVAL_DOCUMENT",
                "output_dimensionality": EMBED_DIM,  # Reduzido para compat com ivfflat
            },
        )
        return [e.values for e in result.embeddings]

    return await loop.run_in_executor(None, _sync_embed)


async def embed_query(query: str) -> list[float]:
    """Gera embedding para uma query de busca."""
    from src.core.config import settings
    import google.genai as genai

    loop = asyncio.get_event_loop()

    def _sync_embed():
        client = genai.Client(api_key=settings.google_api_key)
        result = client.models.embed_content(
            model=settings.embedding_model,
            contents=query,
            config={
                "task_type": "RETRIEVAL_QUERY",
                "output_dimensionality": EMBED_DIM,
            },
        )
        return result.embeddings[0].values

    return await loop.run_in_executor(None, _sync_embed)


async def _save_batch(chunks: list[dict], embeddings: list[list[float]]) -> int:
    """Salva batch de chunks com embeddings no PostgreSQL."""
    from src.db.session import AsyncSessionLocal
    from src.db.models import KnowledgeChunk

    async with AsyncSessionLocal() as db:
        for chunk_data, embedding in zip(chunks, embeddings):
            chunk = KnowledgeChunk(
                id=uuid.uuid4(),
                content=chunk_data["content"],
                embedding=embedding,
                source_file=chunk_data["source_file"],
                doc_type=chunk_data.get("doc_type"),
                section_title=chunk_data.get("section_title"),
                page_number=chunk_data.get("page_number"),
                video_timestamp=chunk_data.get("video_timestamp"),
                is_active=True,
                created_at=datetime.utcnow(),
            )
            db.add(chunk)
        await db.commit()

    return len(chunks)
