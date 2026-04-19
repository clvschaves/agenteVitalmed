from __future__ import annotations
"""
Parser de DOCX — extrai texto por parágrafo e seção.
Usa python-docx para extração estruturada.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_docx(file_path: str) -> list[dict]:
    """
    Extrai texto de um arquivo DOCX preservando estrutura de seções.

    Returns:
        list de dicts: [{"content": str, "page": None, "section_title": str}]
    """
    try:
        from docx import Document
    except ImportError:
        raise ImportError("python-docx não instalado. Execute: pip install python-docx")

    doc = Document(file_path)
    sections = []
    current_section = "Geral"
    buffer_paragraphs = []

    def flush_buffer(title: str):
        """Agrupa parágrafo no buffer como uma seção."""
        content = "\n".join(buffer_paragraphs).strip()
        if content:
            sections.append({
                "content": content,
                "page": None,
                "section_title": title,
            })

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        # Detectar headings como início de nova seção
        if para.style.name.startswith("Heading"):
            flush_buffer(current_section)
            buffer_paragraphs = []
            current_section = text
        else:
            buffer_paragraphs.append(text)

    flush_buffer(current_section)  # Flush final

    logger.info(f"DOCX parseado: {Path(file_path).name} | {len(sections)} seções")
    return sections
