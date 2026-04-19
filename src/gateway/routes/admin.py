from __future__ import annotations
"""
Admin routes — upload e gerenciamento de documentos para RAG.
Usado pelo Streamlit e opcionalmente por integrações externas.
"""
import os
import logging
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from pydantic import BaseModel

from src.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "video/mp4": "video",
    "video/x-matroska": "video",
    "video/quicktime": "video",
}


class DocumentInfo(BaseModel):
    filename: str
    doc_type: str
    status: str   # pending | indexing | indexed | error
    chunks_count: int | None = None
    uploaded_at: str | None = None


@router.post("/upload", response_model=DocumentInfo)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """
    Faz upload de um documento (PDF, DOCX ou vídeo) e inicia a indexação RAG.
    O arquivo é salvo em /uploads e o pipeline de ingestão roda em background.
    """
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo não suportado: {file.content_type}. Use PDF, DOCX ou MP4.",
        )

    doc_type = ALLOWED_TYPES[file.content_type]
    uploads_path = Path(settings.uploads_dir)
    uploads_path.mkdir(parents=True, exist_ok=True)

    file_path = uploads_path / file.filename
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    logger.info(f"📄 Arquivo recebido: {file.filename} ({doc_type})")

    # Importação lazy para evitar circular imports
    from src.rag.ingestor import ingest_document
    background_tasks.add_task(ingest_document, str(file_path), doc_type)

    return DocumentInfo(
        filename=file.filename,
        doc_type=doc_type,
        status="indexing",
    )


@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents():
    """Lista os documentos indexados na base RAG."""
    from src.db.session import AsyncSessionLocal
    from src.db.models import KnowledgeChunk
    from sqlalchemy import select, func, distinct

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(
                    KnowledgeChunk.source_file,
                    KnowledgeChunk.doc_type,
                    func.count(KnowledgeChunk.id).label("chunks_count"),
                    func.min(KnowledgeChunk.created_at).label("uploaded_at"),
                )
                .where(KnowledgeChunk.is_active == True)
                .group_by(KnowledgeChunk.source_file, KnowledgeChunk.doc_type)
                .order_by(func.min(KnowledgeChunk.created_at).desc())
            )
            rows = result.all()

        return [
            DocumentInfo(
                filename=row.source_file,
                doc_type=row.doc_type or "unknown",
                status="indexed",
                chunks_count=row.chunks_count,
                uploaded_at=row.uploaded_at.isoformat() if row.uploaded_at else None,
            )
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Erro ao listar documentos: {e}")
        return []


@router.delete("/documents/{filename}")
async def delete_document(filename: str):
    """Remove (soft delete) todos os chunks de um documento da base RAG."""
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

    logger.info(f"🗑️  Documento removido da RAG: {filename}")
    return {"message": f"Documento '{filename}' removido com sucesso."}


@router.post("/documents/{filename}/reindex")
async def reindex_document(filename: str, background_tasks: BackgroundTasks):
    """Re-indexa um documento já existente (atualiza chunks)."""
    file_path = Path(settings.uploads_dir) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Arquivo '{filename}' não encontrado em uploads/")

    ext = file_path.suffix.lower()
    ext_to_type = {".pdf": "pdf", ".docx": "docx", ".mp4": "video", ".mkv": "video", ".mov": "video"}
    doc_type = ext_to_type.get(ext, "pdf")

    from src.rag.ingestor import ingest_document
    background_tasks.add_task(ingest_document, str(file_path), doc_type, reindex=True)

    return {"message": f"Re-indexação de '{filename}' iniciada."}
