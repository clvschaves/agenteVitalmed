"""
Tools do ContractAgent:
- generate_and_upload_contract: preenche o template e sobe ao GCS
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from agno.tools import tool

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "contracts"


# ─── helpers ────────────────────────────────────────────────────────────────

def _fill_template(template_path: Path, data: dict) -> str:
    """Substitui todos os {{chave}} pelo valor correspondente no dict."""
    content = template_path.read_text(encoding="utf-8")
    for key, value in data.items():
        content = content.replace("{{" + key + "}}", str(value) if value else "")
    # Remove placeholders não preenchidos
    content = re.sub(r"\{\{[^}]+\}\}", "", content)
    return content


def _build_dependentes_tabela(dependentes: list[dict]) -> str:
    """Gera as linhas da tabela de dependentes para o template familiar."""
    rows = []
    for d in dependentes:
        row = (
            f"| {d.get('nome_completo', '')} "
            f"| {d.get('parentesco', '')} "
            f"| {d.get('data_nascimento', '')} "
            f"| {d.get('cpf', '')} "
            f"| {d.get('faixa_etaria', '')} "
            f"| {d.get('valor_plano', '')} |"
        )
        rows.append(row)
    return "\n".join(rows) if rows else "| - | - | - | - | - | - |"


def _md_to_pdf_bytes(md_content: str) -> tuple[bytes, str]:
    """
    Converte Markdown para PDF usando fpdf2 (pure Python).
    Tabelas são convertidas em texto corrido (Campo: Valor) para máxima estabilidade.
    Retorna (bytes, extensão).
    """
    try:
        from fpdf import FPDF
        import re as _re

        # ── Transliteração Latin-1 ──────────────────────────────────────────────
        def safe_text(t: str) -> str:
            """Transliterate PT-BR chars to Latin-1 (Helvetica)."""
            r = {
                "\u2014": "-", "\u2013": "-", "\u2019": "'", "\u2018": "'",
                "\u201c": '"', "\u201d": '"', "\xa0": " ", "\u2026": "...",
                "\u00e0": "a", "\u00e1": "a", "\u00e2": "a", "\u00e3": "a",
                "\u00e4": "a", "\u00e5": "a", "\u00e6": "ae",
                "\u00c0": "A", "\u00c1": "A", "\u00c2": "A", "\u00c3": "A",
                "\u00e8": "e", "\u00e9": "e", "\u00ea": "e", "\u00eb": "e",
                "\u00c8": "E", "\u00c9": "E", "\u00ca": "E",
                "\u00ec": "i", "\u00ed": "i", "\u00ee": "i", "\u00ef": "i",
                "\u00cc": "I", "\u00cd": "I", "\u00ce": "I",
                "\u00f2": "o", "\u00f3": "o", "\u00f4": "o", "\u00f5": "o",
                "\u00d3": "O", "\u00d4": "O", "\u00d5": "O",
                "\u00f9": "u", "\u00fa": "u", "\u00fb": "u", "\u00fc": "u",
                "\u00da": "U", "\u00db": "U", "\u00dc": "U",
                "\u00e7": "c", "\u00c7": "C",
                "\u00f1": "n", "\u00d1": "N",
                "\u00df": "ss",
            }
            for k, v in r.items():
                t = t.replace(k, v)
            return t.encode("latin-1", errors="replace").decode("latin-1")

        # ── Pré-processamento: tabelas → texto corrido ──────────────────────────
        def table_to_text(md: str) -> str:
            """
            Converte tabelas Markdown em linhas "Campo: Valor".
            Cabeçalho da tabela vira prefixo; separadores (---) são removidos.
            """
            out_lines = []
            raw_lines = md.split("\n")
            i = 0
            while i < len(raw_lines):
                line = raw_lines[i]
                if line.strip().startswith("|"):
                    # Coletar bloco de tabela
                    block = []
                    while i < len(raw_lines) and raw_lines[i].strip().startswith("|"):
                        block.append(raw_lines[i])
                        i += 1
                    # Filtrar separadores (|---|)
                    rows = [r for r in block
                            if not _re.match(r"^\s*\|[-| :]+\|\s*$", r)]
                    if not rows:
                        continue
                    headers = [c.strip() for c in rows[0].strip().strip("|").split("|")]
                    # Se só cabeçalho (sem dados), escrever como itens de lista
                    if len(rows) == 1:
                        for h in headers:
                            clean_h = _re.sub(r"\*\*(.+?)\*\*", r"\1", h)
                            out_lines.append(f"  {clean_h}")
                    else:
                        for row in rows[1:]:
                            vals = [c.strip() for c in row.strip().strip("|").split("|")]
                            for h, v in zip(headers, vals):
                                clean_h = _re.sub(r"\*\*(.+?)\*\*", r"\1", h)
                                clean_v = _re.sub(r"\*\*(.+?)\*\*", r"\1", v)
                                if clean_v.strip():
                                    out_lines.append(f"{clean_h}: {clean_v}")
                    out_lines.append("")  # espaço após bloco
                else:
                    out_lines.append(line)
                    i += 1
            return "\n".join(out_lines)

        # Pré-processar o Markdown
        processed = table_to_text(md_content)

        # ── Classe PDF ──────────────────────────────────────────────────────────
        class ContractPDF(FPDF):
            def header(self):
                self.set_font("Helvetica", "B", 9)
                self.set_text_color(100, 100, 100)
                self.cell(0, 6, "VITALMED - CONTRATO DE PRESTACAO DE SERVICOS", align="C")
                self.ln(3)
                self.set_draw_color(200, 200, 200)
                self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
                self.ln(4)

            def footer(self):
                self.set_y(-12)
                self.set_font("Helvetica", "I", 8)
                self.set_text_color(150, 150, 150)
                self.cell(0, 6, f"Pagina {self.page_no()}", align="C")

        pdf = ContractPDF(orientation="P", unit="mm", format="A4")
        pdf.set_margins(15, 22, 15)
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        _pw = pdf.w - pdf.l_margin - pdf.r_margin

        # ── Renderização linha a linha ──────────────────────────────────────────
        lines = processed.split("\n")
        for line in lines:
            text = line.rstrip()

            if text.startswith("### "):
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(20, 20, 60)
                pdf.ln(3)
                pdf.multi_cell(_pw, 5, safe_text(text[4:]), align="L")
                pdf.ln(1)

            elif text.startswith("## "):
                pdf.set_font("Helvetica", "B", 12)
                pdf.set_text_color(10, 10, 80)
                pdf.ln(4)
                pdf.multi_cell(_pw, 6, safe_text(text[3:]), align="L")
                pdf.set_draw_color(100, 100, 180)
                pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
                pdf.ln(3)

            elif text.startswith("# "):
                pdf.set_font("Helvetica", "B", 14)
                pdf.set_text_color(10, 10, 80)
                pdf.ln(5)
                pdf.multi_cell(_pw, 7, safe_text(text[2:]), align="C")
                pdf.ln(4)

            elif text.strip() == "---":
                pdf.set_draw_color(180, 180, 180)
                pdf.ln(2)
                pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
                pdf.ln(3)

            elif text.strip() == "":
                pdf.ln(2)

            else:
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(30, 30, 30)
                # Converter **negrito** → texto normal (sem formatação no fpdf2 básico)
                clean = _re.sub(r"\*\*(.+?)\*\*", r"\1", text)
                # Bullets * → •
                clean = _re.sub(r"^\*\s+", "  > ", clean)
                pdf.multi_cell(_pw, 5, safe_text(clean), align="L")

        return bytes(pdf.output()), "pdf"

    except Exception as e:
        logger.warning(f"fpdf2 erro ({e}) — enviando .md para GCS")
        return md_content.encode("utf-8"), "md"



# ─── tool principal ──────────────────────────────────────────────────────────

@tool
def generate_and_upload_contract(
    contract_type: str,
    titular_json: str,
    contract_info_json: str,
    dependentes_json: str = "[]",
    resumo_json: str = "{}",
) -> str:
    """
    Gera o contrato preenchido e faz upload para o GCS.

    Args:
        contract_type: "individual" ou "familiar"
        titular_json: JSON com campos do contratante (nome_completo, cpf, rg, data_nascimento,
                      idade, estado_civil, profissao, nacionalidade, endereco_completo,
                      cidade, uf, cep, telefone, whatsapp, email, faixa_etaria, valor_plano)
        contract_info_json: JSON com dados do contrato (forma_pagamento, dia_vencimento, etc.)
        dependentes_json: JSON array de dependentes (apenas para contrato familiar)
        resumo_json: JSON com valores financeiros (valor_titular, valor_mensal_final, etc.)

    Returns:
        JSON string com gcs_path, filename e contract_number do contrato gerado
    """
    import json
    from src.core.gcs_client import upload_contract_to_gcs

    titular = json.loads(titular_json)
    contract_info = json.loads(contract_info_json)
    dependentes = json.loads(dependentes_json) if dependentes_json else []
    resumo = json.loads(resumo_json) if resumo_json else {}

    # ── 1. CPF limpo para path no GCS
    cpf_raw = titular.get("cpf", "sem_cpf")
    cpf_clean = re.sub(r"[^\d]", "", cpf_raw) or "sem_cpf"

    # ── 2. Defaults automáticos
    hoje = datetime.now()
    contract_info.setdefault("numero", f"VTM-{hoje.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}")
    contract_info.setdefault("data_emissao", hoje.strftime("%d/%m/%Y"))
    contract_info.setdefault("data_assinatura", hoje.strftime("%d/%m/%Y"))
    contract_info.setdefault("local_emissao", "Sao Luis - MA")
    contract_info.setdefault("local_assinatura", "Sao Luis - MA")
    contract_info.setdefault("codigo_associado", f"VM-{cpf_clean[-4:]}")
    contract_info.setdefault("data_inicio_vigencia", hoje.strftime("%d/%m/%Y"))
    contract_info.setdefault("dia_vencimento", "10")

    resumo.setdefault("descontos", "Nao aplicavel")
    resumo.setdefault("valor_dependentes", "Nao aplicavel")
    resumo.setdefault("valor_adesao", "R$ 0,00")
    resumo.setdefault("total_ato_contratacao", resumo.get("valor_adesao", "R$ 0,00"))

    # ── 3. Template
    tpl_name = "template_familiar.md" if contract_type == "familiar" else "template_individual.md"
    template_path = _TEMPLATES_DIR / tpl_name

    # ── 4. Flat dict para substituição
    flat: dict = {}
    for k, v in titular.items():
        flat[f"contratante.{k}"] = v
    for k, v in contract_info.items():
        flat[f"contrato.{k}"] = v
    for k, v in resumo.items():
        flat[f"resumo.{k}"] = v
    flat["titular.valor_plano"] = resumo.get("valor_titular", "A definir")
    flat["testemunha1.nome"] = ""
    flat["testemunha1.cpf"] = ""
    flat["testemunha2.nome"] = ""
    flat["testemunha2.cpf"] = ""

    if contract_type == "familiar" and dependentes:
        flat["dependentes_tabela"] = _build_dependentes_tabela(dependentes)

    # ── 5. Preencher + gerar PDF
    md_content = _fill_template(template_path, flat)
    file_bytes, ext = _md_to_pdf_bytes(md_content)
    filename = f"contrato_{contract_info['numero'].replace('/', '-')}.{ext}"

    # ── 6. Upload GCS
    gcs_path = upload_contract_to_gcs(
        cpf=cpf_clean,
        filename=filename,
        content=file_bytes,
        content_type="application/pdf" if ext == "pdf" else "text/plain",
    )

    # ── 7. Persistir no banco (opcional — não bloqueia se DB estiver off)
    contract_id = "sem-db"
    try:
        from src.db.session import SyncSessionLocal
        from src.db.models import Contract, ContractDependent, Lead

        with SyncSessionLocal() as db:
            lead = db.query(Lead).filter(Lead.phone == titular.get("whatsapp", "")).first()
            lead_id = lead.id if lead else None

            contract = Contract(
                lead_id=lead_id,
                contract_type=contract_type,
                status="enviado",
                gcs_path=gcs_path,
                filename=filename,
                titular_data=titular,
                contract_data=contract_info,
            )
            db.add(contract)
            db.flush()

            if contract_type == "familiar" and dependentes:
                for dep in dependentes:
                    db.add(ContractDependent(
                        contract_id=contract.id,
                        nome_completo=dep.get("nome_completo", ""),
                        cpf=dep.get("cpf", ""),
                        rg=dep.get("rg", ""),
                        data_nascimento=dep.get("data_nascimento", ""),
                        idade=dep.get("idade"),
                        parentesco=dep.get("parentesco", ""),
                        faixa_etaria=dep.get("faixa_etaria", ""),
                        valor_plano=dep.get("valor_plano", ""),
                    ))

            db.commit()
            contract_id = str(contract.id)
    except Exception as e_db:
        logger.warning(f"DB persist ignorado (teste/sem-DB): {e_db}")

    logger.info(f"Contrato {contract_info['numero']} gerado | GCS: {gcs_path}")
    result = {
        "success": True,
        "contract_id": contract_id,
        "gcs_path": gcs_path,
        "filename": filename,
        "contract_number": contract_info["numero"],
        "format": ext,
    }
    import json as _json
    return _json.dumps(result, ensure_ascii=False)



