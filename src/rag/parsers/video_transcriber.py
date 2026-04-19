from __future__ import annotations
"""
Transcritor de vídeo — usa Whisper para transcrição offline.
Suporta MP4, MKV, MOV e outros formatos aceitos pelo ffmpeg.
"""
import asyncio
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


async def transcribe_video(file_path: str) -> list[dict]:
    """
    Transcreve o áudio de um vídeo usando Whisper.
    Executa em thread pool para não bloquear o event loop.

    Returns:
        list de dicts: [{"content": str, "video_timestamp": str, "section_title": str}]
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _transcribe_sync, file_path)


def _transcribe_sync(file_path: str) -> list[dict]:
    """Transcrição síncrona com Whisper."""
    from src.core.config import settings

    if settings.whisper_mode == "openai_api":
        return _transcribe_openai_api(file_path)
    else:
        return _transcribe_local(file_path, settings.whisper_model_size)


def _transcribe_local(file_path: str, model_size: str = "base") -> list[dict]:
    """Transcrição com Whisper local (offline)."""
    try:
        import whisper
    except ImportError:
        raise ImportError("openai-whisper não instalado. Execute: pip install openai-whisper")

    logger.info(f"🎬 Transcrevendo vídeo com Whisper ({model_size}): {Path(file_path).name}")
    model = whisper.load_model(model_size)
    result = model.transcribe(file_path, language="pt", verbose=False)

    sections = []
    for segment in result.get("segments", []):
        start = segment["start"]
        minutes = int(start // 60)
        seconds = int(start % 60)
        timestamp = f"{minutes:02d}:{seconds:02d}"

        sections.append({
            "content": segment["text"].strip(),
            "video_timestamp": timestamp,
            "section_title": f"Transcrição vídeo — {timestamp}",
            "page": None,
        })

    logger.info(f"✅ Transcrição concluída: {len(sections)} segmentos")
    return sections


def _transcribe_openai_api(file_path: str) -> list[dict]:
    """Transcrição via API Whisper da OpenAI (quando whisper_mode=openai_api)."""
    try:
        import openai
        from src.core.config import settings

        client = openai.OpenAI(api_key=settings.openai_api_key)

        with open(file_path, "rb") as f:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="pt",
                response_format="verbose_json",
            )

        sections = []
        for segment in response.segments:
            start = segment["start"]
            minutes = int(start // 60)
            seconds = int(start % 60)
            timestamp = f"{minutes:02d}:{seconds:02d}"

            sections.append({
                "content": segment["text"].strip(),
                "video_timestamp": timestamp,
                "section_title": f"Transcrição vídeo — {timestamp}",
                "page": None,
            })

        return sections

    except Exception as e:
        logger.error(f"Erro na transcrição via API: {e}")
        raise
