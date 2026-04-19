#!/usr/bin/env python3
"""
Script de deploy dos dados para o servidor Vitalmed.
Executa:
  1. Copia os PDFs de uploads/ para o servidor
  2. Chama a API de ingestão para indexar cada PDF no pgvector
  3. Exibe relatório final com status de cada arquivo

Uso:
  python scripts/deploy_data.py
"""
import asyncio
import os
import sys
import logging
from pathlib import Path

import httpx

# ── Config ────────────────────────────────────────────────────────────────────
SERVER_API = "http://37.27.208.115:8000"  # Ou via domínio
UPLOADS_DIR = Path(__file__).parent.parent / "uploads"
PDF_FILES = [
    "vitalmed.pdf",
    "Manual BOAS VINDAS (2).pdf",
    "SERVIÇOS VITALMED 2022-1.pdf",
    "scripts_vendas_vitalmed.pdf",
    "vitalmed_catalogo_textual.pdf",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("deploy_data")


async def check_api_health(client: httpx.AsyncClient) -> bool:
    """Verifica se a API está online."""
    try:
        r = await client.get(f"{SERVER_API}/health", timeout=10)
        if r.status_code == 200:
            log.info("✅ API online: %s", r.json())
            return True
    except Exception as e:
        log.error("❌ API inacessível: %s", e)
    return False


async def upload_and_index(client: httpx.AsyncClient, filename: str) -> dict:
    """Faz upload do arquivo e dispara a indexação via multipart."""
    file_path = UPLOADS_DIR / filename

    if not file_path.exists():
        log.warning("⚠️  Arquivo não encontrado localmente: %s", filename)
        return {"filename": filename, "status": "not_found"}

    log.info("📤 Enviando: %s (%.1f MB)", filename, file_path.stat().st_size / 1_048_576)

    try:
        with open(file_path, "rb") as f:
            files = {"file": (filename, f, "application/pdf")}
            data = {"reindex": "true"}
            r = await client.post(
                f"{SERVER_API}/documents/upload",
                files=files,
                data=data,
                timeout=300,  # PDFs grandes podem demorar
            )

        if r.status_code in (200, 201):
            result = r.json()
            log.info("✅ Indexado: %s | chunks=%s | status=%s",
                     filename, result.get("chunks_created"), result.get("status"))
            return result
        else:
            log.error("❌ Erro ao indexar %s: HTTP %s | %s", filename, r.status_code, r.text[:200])
            return {"filename": filename, "status": "error", "http_code": r.status_code}

    except Exception as e:
        log.error("❌ Exceção ao processar %s: %s", filename, e)
        return {"filename": filename, "status": "exception", "error": str(e)}


async def check_indexed_docs(client: httpx.AsyncClient) -> None:
    """Lista documentos já indexados no servidor."""
    try:
        r = await client.get(f"{SERVER_API}/documents", timeout=10)
        if r.status_code == 200:
            docs = r.json()
            if docs:
                log.info("\n📚 Documentos indexados no servidor:")
                for d in docs:
                    log.info("   • %s | %s chunks | %s",
                             d.get("source_file"), d.get("chunks"), d.get("indexed_at", "")[:10])
            else:
                log.info("   (nenhum documento indexado)")
    except Exception as e:
        log.warning("Não foi possível listar documentos: %s", e)


async def main():
    log.info("=" * 60)
    log.info("🚀 Deploy de Dados — Vitalmed RAG")
    log.info("=" * 60)

    async with httpx.AsyncClient() as client:
        # 1. Verifica API
        if not await check_api_health(client):
            log.error("❌ API inacessível. Verifique se o servidor está online.")
            sys.exit(1)

        # 2. Lista docs já indexados
        await check_indexed_docs(client)

        # 3. Indexa cada PDF
        results = []
        for pdf in PDF_FILES:
            result = await upload_and_index(client, pdf)
            results.append(result)

        # 4. Relatório final
        log.info("\n" + "=" * 60)
        log.info("📊 RELATÓRIO FINAL")
        log.info("=" * 60)

        total_chunks = 0
        for r in results:
            status = r.get("status", "?")
            chunks = r.get("chunks_created", 0)
            total_chunks += chunks or 0
            icon = "✅" if status == "indexed" else "❌"
            log.info("%s %-45s | chunks=%s | status=%s",
                     icon, r.get("filename", r.get("source_file", "?")), chunks, status)

        log.info("\n🎯 Total de chunks indexados: %d", total_chunks)
        log.info("=" * 60)

        # 5. Lista docs após indexação
        await check_indexed_docs(client)


if __name__ == "__main__":
    asyncio.run(main())
