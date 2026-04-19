from __future__ import annotations
"""
Módulo de memória de longo prazo por lead — estilo MemPalace.
Cada lead tem um "palácio" de arquivos .md em memory/palace/leads/{phone}/

Estrutura:
    profile.md          → dados básicos + plano de interesse + status atual
    hall_facts.md       → decisões e fatos confirmados
    hall_events.md      → histórico de sessões com timestamps
    hall_preferences.md → tom preferido, objeções recorrentes
"""
import asyncio
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

PALACE_BASE = Path(__file__).parent / "palace" / "leads"


class LongTermMemory:
    """
    Gerencia a memória de longo prazo de um lead em arquivos .md.
    Leitura no início da sessão; escrita ao final ou sob demanda.
    """

    def __init__(self, phone: str):
        self.phone = phone
        self.palace_dir = PALACE_BASE / phone
        self.palace_dir.mkdir(parents=True, exist_ok=True)

        self._profile_path = self.palace_dir / "profile.md"
        self._facts_path = self.palace_dir / "hall_facts.md"
        self._events_path = self.palace_dir / "hall_events.md"
        self._prefs_path = self.palace_dir / "hall_preferences.md"

        self._init_files()

    def _init_files(self):
        """Cria arquivos .md vazios se não existirem."""
        templates = {
            self._profile_path: f"# Perfil do Lead — {self.phone}\n\n_Sem dados ainda._\n",
            self._facts_path: f"# Fatos Confirmados — {self.phone}\n\n",
            self._events_path: f"# Histórico de Sessões — {self.phone}\n\n",
            self._prefs_path: f"# Preferências — {self.phone}\n\n",
        }
        for path, content in templates.items():
            if not path.exists():
                path.write_text(content, encoding="utf-8")

    async def load(self) -> dict[str, str]:
        """
        Carrega todo o conteúdo do palácio do lead.
        Retorna dicionário com as seções para injetar no contexto do agente.
        """
        loop = asyncio.get_event_loop()
        content = await loop.run_in_executor(None, self._read_all)
        return content

    def _read_all(self) -> dict[str, str]:
        return {
            "profile": self._profile_path.read_text(encoding="utf-8"),
            "facts": self._facts_path.read_text(encoding="utf-8"),
            "events": self._events_path.read_text(encoding="utf-8"),
            "preferences": self._prefs_path.read_text(encoding="utf-8"),
        }

    async def update_profile(self, **fields) -> None:
        """
        Atualiza o profile.md com os dados fornecidos.
        Chamado pelo AssistantAgent quando coleta novos dados do lead.
        """
        lines = [f"# Perfil do Lead — {self.phone}\n"]
        lines.append(f"_Atualizado em: {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC_\n\n")
        for key, value in fields.items():
            if value:
                lines.append(f"- **{key}**: {value}\n")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self._profile_path.write_text,
            "".join(lines),
            "utf-8",
        )
        logger.debug(f"📝 Perfil atualizado: {self.phone}")

    async def append_fact(self, fact: str) -> None:
        """
        Adiciona um fato confirmado ao hall_facts.md.
        Ex: "Lead escolheu o Plano Família Premium"
        """
        entry = f"- [{datetime.utcnow().strftime('%d/%m/%Y %H:%M')}] {fact}\n"
        await self._append_to_file(self._facts_path, entry)

    async def append_event(self, event: str) -> None:
        """
        Registra um evento de sessão no hall_events.md.
        Ex: "Sessão 12/04/2026 — primeira abordagem"
        """
        entry = f"- {event}\n"
        await self._append_to_file(self._events_path, entry)

    async def append_preference(self, preference: str) -> None:
        """
        Registra uma preferência do lead no hall_preferences.md.
        Ex: "Prefere mensagens curtas", "Objeção: preço alto"
        """
        entry = f"- [{datetime.utcnow().strftime('%d/%m/%Y %H:%M')}] {preference}\n"
        await self._append_to_file(self._prefs_path, entry)

    async def _append_to_file(self, path: Path, text: str) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._write_append, path, text)

    @staticmethod
    def _write_append(path: Path, text: str) -> None:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)

    def build_context_summary(self, memory: dict[str, str]) -> str:
        """
        Monta um texto consolidado para injetar no contexto do agente.
        Formato compacto para não inflar o contexto desnecessariamente.
        """
        summary_parts = ["## Memória do Lead\n"]

        if "Sem dados ainda" not in memory.get("profile", "Sem dados"):
            summary_parts.append(memory["profile"])

        facts = memory.get("facts", "")
        if facts.strip() and len(facts.splitlines()) > 1:
            summary_parts.append("\n### Fatos importantes\n" + facts)

        events = memory.get("events", "")
        if events.strip() and len(events.splitlines()) > 1:
            # Apenas os últimos 5 eventos para não sobrecarregar
            event_lines = [l for l in events.splitlines() if l.startswith("-")][-5:]
            if event_lines:
                summary_parts.append("\n### Sessões recentes\n" + "\n".join(event_lines))

        prefs = memory.get("preferences", "")
        if prefs.strip() and len(prefs.splitlines()) > 1:
            summary_parts.append("\n### Preferências\n" + prefs)

        return "\n".join(summary_parts)
