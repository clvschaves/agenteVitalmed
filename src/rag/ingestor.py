from __future__ import annotations
"""
Pipeline RAG completo: parser → chunker → embedder → pgvector.
Orquestra a ingestão de documentos PDF, DOCX e vídeo.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def ingest_document(file_path: str, doc_type: str, reindex: bool = False) -> dict:
    """
    Pipeline completo de ingestão de um documento.

    1. Parse o arquivo conforme o tipo
    2. Divide em chunks semânticos
    3. Gera embeddings (text-embedding-004)
    4. Salva no pgvector

    Args:
        file_path: Caminho absoluto do arquivo
        doc_type: "pdf", "docx" ou "video"
        reindex: Se True, remove chunks antigos antes de reinserir

    Returns:
        {"filename": str, "chunks_created": int, "status": str}
    """
    path = Path(file_path)
    filename = path.name

    try:
        # ─── 1. Parse ─────────────────────────────────────────────────────
        logger.info(f"📄 Iniciando ingestão: {filename} ({doc_type})")

        if doc_type == "pdf":
            from src.rag.parsers.pdf_parser import parse_pdf
            sections = parse_pdf(str(path))
        elif doc_type == "docx":
            from src.rag.parsers.docx_parser import parse_docx
            sections = parse_docx(str(path))
        elif doc_type == "video":
            from src.rag.parsers.video_transcriber import transcribe_video
            sections = await transcribe_video(str(path))
        else:
            raise ValueError(f"Tipo não suportado: {doc_type}")

        logger.info(f"   ✅ Parse: {len(sections)} seções extraídas")

        # ─── 2. Chunk ─────────────────────────────────────────────────────
        from src.rag.chunker import chunk_sections
        chunks = chunk_sections(sections, filename=filename, doc_type=doc_type)
        logger.info(f"   ✅ Chunking: {len(chunks)} chunks gerados")

        # ─── 3. Remover chunks antigos se reindex ─────────────────────────
        if reindex:
            await _deactivate_old_chunks(filename)

        # ─── 4. Embed + Salvar ────────────────────────────────────────────
        from src.rag.embedder import embed_and_save_chunks
        saved = await embed_and_save_chunks(chunks)
        logger.info(f"   ✅ Indexação completa: {saved} chunks salvos | {filename}")

        return {
            "filename": filename,
            "chunks_created": saved,
            "status": "indexed",
        }

    except Exception as e:
        logger.error(f"❌ Erro na ingestão de {filename}: {e}", exc_info=True)
        return {
            "filename": filename,
            "chunks_created": 0,
            "status": "error",
            "error": str(e),
        }


async def _deactivate_old_chunks(filename: str) -> None:
    """Remove (soft delete) chunks antigos do arquivo antes de re-indexar."""
    from src.db.session import AsyncSessionLocal
    from src.db.models import KnowledgeChunk
    from sqlalchemy import update

    async with AsyncSessionLocal() as db:
        await db.execute(
            update(KnowledgeChunk)
            .where(KnowledgeChunk.source_file == filename)
            .values(is_active=False)
        )
        await db.commit()
    logger.info(f"🗑️  Chunks antigos desativados: {filename}")
