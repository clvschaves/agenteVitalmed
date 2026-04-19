from __future__ import annotations
"""
Parser de PDF — extrai texto por página com metadados.
Suporta dois modos:
  1. Texto nativo (PyMuPDF): PDFs com texto selecionável
  2. OCR via Gemini Vision: PDFs escaneados (imagens)
"""
import logging
import base64
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Mínimo de chars por página para considerar que tem texto nativo
_MIN_TEXT_CHARS = 50


def parse_pdf(file_path: str) -> list[dict]:
    """
    Extrai texto de um PDF, página por página.
    Detecta automaticamente se precisa de OCR (páginas-imagem).

    Returns:
        list de dicts: [{"content": str, "page": int, "section_title": str}]
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError("PyMuPDF não instalado. Execute: pip install pymupdf")

    doc = fitz.open(file_path)
    total_pages = len(doc)
    filename = Path(file_path).name

    logger.info(f"PDF aberto: {filename} | {total_pages} páginas")

    # Amostragem: verificar se o PDF tem texto nativo
    sample_text = ""
    for i in range(min(3, total_pages)):
        sample_text += doc[i].get_text("text").strip()

    is_scanned = len(sample_text) < _MIN_TEXT_CHARS
    logger.info(f"{'📷 PDF escaneado (OCR)' if is_scanned else '📄 PDF com texto nativo'}: {filename}")

    if is_scanned:
        sections = _parse_with_ocr(doc, file_path)
    else:
        sections = _parse_native_text(doc)

    doc.close()
    logger.info(f"PDF parseado: {filename} | {len(sections)} seções")
    return sections


def _parse_native_text(doc) -> list[dict]:
    """Extrai texto nativo página a página via PyMuPDF."""
    sections = []
    current_title = "Conteúdo"

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text").strip()

        if not text or len(text) < 10:
            continue

        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if lines:
            first_line = lines[0]
            if len(first_line) < 80 and (first_line.isupper() or first_line.endswith(":")):
                current_title = first_line

        sections.append({
            "content": text,
            "page": page_num + 1,
            "section_title": current_title,
        })

    return sections


def _parse_with_ocr(doc, file_path: str) -> list[dict]:
    """
    OCR via Gemini Vision para PDFs escaneados.
    Converte cada página em imagem e extrai texto com o modelo.
    """
    import google.genai as genai
    from src.core.config import settings

    client = genai.Client(api_key=settings.google_api_key)
    filename = Path(file_path).name
    sections = []

    logger.info(f"🔍 Iniciando OCR com Gemini Vision: {filename} ({len(doc)} páginas)")

    for page_num in range(len(doc)):
        page = doc[page_num]
        logger.info(f"  OCR página {page_num + 1}/{len(doc)}...")

        try:
            # Renderiza página como imagem PNG (150 DPI — bom para OCR)
            mat = page.get_pixmap(dpi=150)
            img_bytes = mat.tobytes("png")
            img_b64 = base64.b64encode(img_bytes).decode()

            # Chamar Gemini Vision para extrair texto
            response = client.models.generate_content(
                model=settings.gemini_flash_model,
                contents=[
                    {
                        "parts": [
                            {
                                "inline_data": {
                                    "mime_type": "image/png",
                                    "data": img_b64,
                                }
                            },
                            {
                                "text": (
                                    "Extraia TODO o texto desta página de documento, "
                                    "mantendo a estrutura e formatação original. "
                                    "Retorne apenas o texto extraído, sem comentários. "
                                    "Se a página estiver em branco ou ilegível, retorne: [PÁGINA SEM CONTEÚDO]"
                                )
                            },
                        ]
                    }
                ],
            )

            text = response.text.strip() if response.text else ""

            if not text or text == "[PÁGINA SEM CONTEÚDO]":
                logger.debug(f"  Pág {page_num + 1}: sem conteúdo legível")
                continue

            # Detectar título da seção
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            section_title = "Conteúdo"
            if lines:
                first_line = lines[0]
                if len(first_line) < 100 and (first_line.isupper() or first_line.endswith(":")):
                    section_title = first_line

            sections.append({
                "content": text,
                "page": page_num + 1,
                "section_title": section_title,
            })

            logger.info(f"  ✅ Pág {page_num + 1}: {len(text)} chars extraídos via OCR")

            # Rate limit: 1 req/s para não saturar a API
            time.sleep(1.0)

        except Exception as e:
            logger.error(f"  ❌ Erro OCR pág {page_num + 1}: {e}")
            continue

    return sections
