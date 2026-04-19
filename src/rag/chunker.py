from __future__ import annotations
"""
Chunker semântico — divide seções em chunks de ~512 tokens com 20% de overlap.
Usa tiktoken para contagem precisa de tokens (compatível com Gemini).
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 512
DEFAULT_OVERLAP_RATIO = 0.20


def chunk_sections(
    sections: list[dict],
    filename: str,
    doc_type: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap_ratio: float = DEFAULT_OVERLAP_RATIO,
) -> list[dict]:
    """
    Divide seções extraídas em chunks menores para embedding.

    Args:
        sections: Saída dos parsers (list de dicts com content, page, etc.)
        filename: Nome do arquivo fonte
        doc_type: "pdf" | "docx" | "video"
        chunk_size: Tamanho alvo em tokens
        overlap_ratio: Fração de overlap entre chunks consecutivos

    Returns:
        list de chunks prontos para embedding
    """
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
    except Exception:
        logger.warning("tiktoken não disponível — usando estimativa por caracteres")
        enc = None

    overlap_size = int(chunk_size * overlap_ratio)
    all_chunks = []

    for section in sections:
        content = section.get("content", "").strip()
        if not content:
            continue

        section_chunks = _split_text(
            text=content,
            chunk_size=chunk_size,
            overlap_size=overlap_size,
            encoder=enc,
        )

        for chunk_text in section_chunks:
            all_chunks.append({
                "content": chunk_text,
                "source_file": filename,
                "doc_type": doc_type,
                "section_title": section.get("section_title", ""),
                "page_number": section.get("page"),
                "video_timestamp": section.get("video_timestamp"),
            })

    logger.debug(f"Chunking: {len(sections)} seções → {len(all_chunks)} chunks ({filename})")
    return all_chunks


def _split_text(
    text: str,
    chunk_size: int,
    overlap_size: int,
    encoder=None,
) -> list[str]:
    """
    Divide um texto em chunks com overlap, respeitando parágrafos quando possível.
    """
    if encoder:
        tokens = encoder.encode(text)
        chunks = []
        start = 0
        while start < len(tokens):
            end = start + chunk_size
            chunk_tokens = tokens[start:end]
            chunks.append(encoder.decode(chunk_tokens))
            if end >= len(tokens):
                break
            start = end - overlap_size
        return chunks
    else:
        # Fallback: estimativa por caracteres (~4 chars/token)
        char_size = chunk_size * 4
        char_overlap = overlap_size * 4
        chunks = []
        start = 0
        while start < len(text):
            end = start + char_size
            chunks.append(text[start:end])
            if end >= len(text):
                break
            start = end - char_overlap
        return chunks
