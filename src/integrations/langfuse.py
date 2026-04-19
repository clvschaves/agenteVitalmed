from __future__ import annotations
"""
Observabilidade com Langfuse v3.
API: start_as_current_span / start_generation / update_current_trace

Rastreia por conversa:
  - Span completo (session_id / lead / latência)
  - Geração LLM (tokens input/output + custo USD)
  - Tool calls e RAG lookups
  - Erros
"""
import logging
import time
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

# ─── Preços Gemini 2.5 (USD por 1M tokens) ────────────────────────────────────
GEMINI_PRICING: dict[str, dict[str, float]] = {
    "gemini-2.5-flash": {"input": 0.15,  "output": 0.60},
    "gemini-2.5-pro":   {"input": 1.25,  "output": 10.00},
    "gemini-embedding-001": {"input": 0.025, "output": 0.0},
    "default":          {"input": 0.15,  "output": 0.60},
}


@lru_cache(maxsize=1)
def _get_lf():
    """Singleton Langfuse v3."""
    try:
        import langfuse as lf_module
        from src.core.config import settings

        client = lf_module.Langfuse(
            secret_key=settings.langfuse_secret_key,
            public_key=settings.langfuse_public_key,
            host=settings.langfuse_host,
        )
        if client.auth_check():
            logger.info("✅ Langfuse v3 conectado | %s", settings.langfuse_host)
            return client
        logger.warning("⚠️ Langfuse auth_check falhou")
        return None
    except Exception as e:
        logger.warning("⚠️ Langfuse indisponível: %s", e)
        return None


def calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    price = GEMINI_PRICING.get(model, GEMINI_PRICING["default"])
    return (
        (input_tokens  / 1_000_000) * price["input"] +
        (output_tokens / 1_000_000) * price["output"]
    )


# ─── Classe principal de trace ────────────────────────────────────────────────

class ConversationTrace:
    """
    Registra uma conversa completa no Langfuse v3.

    Uso:
        ct = ConversationTrace(session_id, phone, message, name)
        ct.__enter__()
        ...
        ct.finish(response, agent_used, model, input_tokens, output_tokens, tools)
        ct.__exit__(None, None, None)
    """

    def __init__(
        self,
        session_id: str,
        lead_phone: str,
        user_message: str,
        lead_name: str | None = None,
    ):
        self.session_id = session_id
        self.lead_phone = lead_phone
        self.user_message = user_message
        self.lead_name = lead_name or "N/A"
        self._span_ctx = None
        self._span = None
        self._t0 = time.perf_counter()

    def __enter__(self):
        lf = _get_lf()
        if lf:
            try:
                self._span_ctx = lf.start_as_current_span(
                    name="conversa_vitalmed",
                    input=self.user_message,
                )
                self._span = self._span_ctx.__enter__()
                # Anotar metadados na trace raiz
                lf.update_current_trace(
                    session_id=self.session_id,
                    user_id=self.lead_phone,
                    tags=["vitalmed", "whatsapp"],
                    metadata={
                        "lead_name": self.lead_name,
                        "lead_phone": self.lead_phone,
                    },
                )
            except Exception as e:
                logger.debug("Langfuse __enter__ error: %s", e)
        return self

    def finish(
        self,
        response: str,
        agent_used: str = "unknown",
        model: str = "gemini-2.5-flash",
        input_tokens: int = 0,
        output_tokens: int = 0,
        tools_called: list[str] | None = None,
        rag_chunks: int = 0,
        rag_best_score: float = 0.0,
        error: str | None = None,
    ) -> float:
        """Fecha o span e registra todos os metadados. Retorna custo USD."""
        elapsed = time.perf_counter() - self._t0
        cost_usd = calc_cost(model, input_tokens, output_tokens)
        lf = _get_lf()

        if lf and self._span:
            try:
                # Registrar geração LLM (filho do span) — com usage_details e cost_details (API v3)
                input_cost  = calc_cost(model, input_tokens, 0)
                output_cost = calc_cost(model, 0, output_tokens)

                with lf.start_as_current_generation(
                    name=f"llm_{agent_used}",
                    model=model,
                    input=self.user_message,
                    output=response,
                    usage_details={
                        "input":  input_tokens,
                        "output": output_tokens,
                        "total":  input_tokens + output_tokens,
                    },
                    cost_details={
                        "input":  round(input_cost,  8),
                        "output": round(output_cost, 8),
                        "total":  round(cost_usd,    8),
                    },
                    metadata={
                        "tools_called": tools_called or [],
                        "rag_chunks":   rag_chunks,
                    },
                ):
                    pass   # dados já passados na criação

                # Atualizar span principal com output e resultados
                self._span.update(
                    output=response,
                    metadata={
                        "agent_used": agent_used,
                        "model": model,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cost_usd": round(cost_usd, 6),
                        "latency_s": round(elapsed, 2),
                        "tools_called": tools_called or [],
                        "rag_chunks": rag_chunks,
                        "error": error,
                    },
                )

                # Atualizar trace raiz com output final
                lf.update_current_trace(
                    output=response,
                    metadata={
                        "cost_usd": round(cost_usd, 6),
                        "latency_s": round(elapsed, 2),
                        "agent_used": agent_used,
                        "model": model,
                        "error": error,
                    },
                )

                # ─── Scores no trace (visíveis no dashboard Langfuse) ────────────
                if rag_best_score > 0:
                    lf.score_current_trace(
                        name="rag_relevance",
                        value=round(rag_best_score, 4),
                        data_type="NUMERIC",
                        comment=f"Cosine similarity do chunk mais relevante ({rag_chunks} chunks buscados)",
                    )

                lf.score_current_trace(
                    name="response_latency_s",
                    value=round(elapsed, 2),
                    data_type="NUMERIC",
                    comment=f"Latência total da conversa em segundos",
                )

                lf.score_current_trace(
                    name="cost_usd",
                    value=round(cost_usd, 6),
                    data_type="NUMERIC",
                    comment=f"{input_tokens} tokens input + {output_tokens} output | modelo {model}",
                )

                if error:
                    lf.score_current_trace(
                        name="error",
                        value="error",
                        data_type="CATEGORICAL",
                        comment=error[:200],
                    )

            except Exception as e:
                logger.debug("Langfuse finish error: %s", e)

        logger.info(
            "📊 Langfuse | session=%s | agent=%s | tokens=%d+%d | cost=$%.4f | %.1fs",
            self.session_id, agent_used, input_tokens, output_tokens, cost_usd, elapsed,
        )
        return cost_usd

    def __exit__(self, *args):
        lf = _get_lf()
        if self._span_ctx:
            try:
                self._span_ctx.__exit__(*args)
            except Exception as e:
                logger.debug("Langfuse __exit__ error: %s", e)
        if lf:
            try:
                lf.flush()
            except Exception:
                pass

    def log_error(self, error: str):
        """Registra erro como evento no span atual."""
        lf = _get_lf()
        if lf:
            try:
                lf.update_current_span(
                    metadata={"error": error},
                    level="ERROR",
                )
                lf.update_current_trace(metadata={"error": error})
            except Exception:
                pass

    def log_rag(self, query: str, chunks_found: int, best_score: float):
        """Registra RAG lookup como span filho."""
        lf = _get_lf()
        if lf:
            try:
                with lf.start_as_current_span(name="rag_retrieval", input=query) as s:
                    s.update(
                        output=f"{chunks_found} chunks | score={best_score:.3f}",
                        metadata={"chunks_found": chunks_found, "best_score": best_score},
                    )
            except Exception:
                pass


# ─── Eventos de indexação ─────────────────────────────────────────────────────

def log_indexing(
    filename: str,
    doc_type: str,
    chunks_saved: int,
    pages: int,
    ocr_used: bool,
    elapsed_s: float,
) -> None:
    """Registra evento de indexação de documento no Langfuse."""
    lf = _get_lf()
    if not lf:
        return
    try:
        with lf.start_as_current_span(name="doc_indexing", input=filename) as span:
            span.update(
                output=f"{chunks_saved} chunks de {pages} páginas",
                metadata={
                    "doc_type": doc_type,
                    "chunks_saved": chunks_saved,
                    "pages": pages,
                    "ocr_used": ocr_used,
                    "elapsed_s": round(elapsed_s, 2),
                },
            )
            lf.update_current_trace(
                session_id=f"indexing_{filename}",
                tags=["vitalmed", "rag", "indexing"],
            )
        lf.flush()
        logger.info("📊 Langfuse indexing trace | %s | %d chunks", filename, chunks_saved)
    except Exception as e:
        logger.debug("Langfuse indexing error: %s", e)
