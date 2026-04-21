"""
Tools do ContractAgent:
- generate_and_upload_contract: preenche o template e sobe ao GCS
"""
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

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
    return "\n".join(rows) if rows else "| — | — | — | — | — | — |"


def _md_to_pdf_bytes(md_content: str) -> bytes:
    """
    Converte Markdown para PDF.
    Tenta usar weasyprint; se não disponível, retorna o md como UTF-8 bytes
    e sinaliza com extensão .md (fallback para testes locais).
    """
    try:
        import markdown2
        from weasyprint import HTML
        html = f"""
        <html><head>
        <meta charset="utf-8">
        <style>
          body {{ font-family: Arial, sans-serif; font-size: 11px; margin: 2cm; }}
          h1 {{ font-size: 14px; }} h2 {{ font-size: 13px; }} h3 {{ font-size: 12px; }}
          table {{ border-collapse: collapse; width: 100%; font-size: 10px; }}
          th, td {{ border: 1px solid #ccc; padding: 4px; }}
        </style></head>
        <body>{markdown2.markdown(md_content, extras=["tables"])}</body></html>
        """
        return HTML(string=html).write_pdf(), "pdf"
    except ImportError:
        logger.warning("weasyprint/markdown2 não disponível — enviando .md para GCS")
        return md_content.encode("utf-8"), "md"


# ─── tool principal ──────────────────────────────────────────────────────────

@tool
def generate_and_upload_contract(
    contract_type: str,
    titular: dict,
    contract_info: dict,
    dependentes: list | None = None,
    resumo: dict | None = None,
) -> dict:
    """
    Gera o contrato preenchido e faz upload para o GCS.

    Args:
        contract_type: "individual" ou "familiar"
        titular: dicionário com todos os campos do contratante
        contract_info: dicionário com dados do contrato (numero, datas, forma_pagamento, etc.)
        dependentes: lista de dicionários de dependentes (apenas para "familiar")
        resumo: dicionário com valores financeiros

    Returns:
        dict com gcs_path e filename do contrato gerado
    """
    from src.core.gcs_client import upload_contract_to_gcs
    from src.db.session import SyncSessionLocal
    from src.db.models import Contract, ContractDependent, Lead

    # ── 1. Descobrir o lead_id pelo telefone (cpf pode não estar no Lead)
    cpf_raw = titular.get("cpf", "sem_cpf")
    cpf_clean = re.sub(r"[^\d]", "", cpf_raw) or "sem_cpf"

    # ── 2. Montar número de contrato e datas automáticas se não fornecidos
    hoje = datetime.now()
    contract_info.setdefault("numero", f"VTM-{hoje.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}")
    contract_info.setdefault("data_emissao", hoje.strftime("%d/%m/%Y"))
    contract_info.setdefault("data_assinatura", hoje.strftime("%d/%m/%Y"))
    contract_info.setdefault("local_emissao", "São Luís - MA")
    contract_info.setdefault("local_assinatura", "São Luís - MA")
    contract_info.setdefault("codigo_associado", f"VM-{cpf_clean[-4:]}")
    contract_info.setdefault("data_inicio_vigencia", hoje.strftime("%d/%m/%Y"))
    contract_info.setdefault("dia_vencimento", "10")

    resumo = resumo or {}
    resumo.setdefault("descontos", "Não aplicável")
    resumo.setdefault("valor_dependentes", "Não aplicável")
    resumo.setdefault("valor_adesao", "R$ 0,00")
    resumo.setdefault("total_ato_contratacao", resumo.get("valor_adesao", "R$ 0,00"))

    # ── 3. Escolher template
    tpl_name = "template_familiar.md" if contract_type == "familiar" else "template_individual.md"
    template_path = _TEMPLATES_DIR / tpl_name

    # ── 4. Montar flat dict de substituição
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

    # ── 5. Tabela de dependentes (template familiar)
    if contract_type == "familiar" and dependentes:
        flat["dependentes_tabela"] = _build_dependentes_tabela(dependentes)

    # ── 6. Preencher template
    md_content = _fill_template(template_path, flat)

    # ── 7. Converter para PDF (ou md fallback)
    file_bytes, ext = _md_to_pdf_bytes(md_content)
    filename = f"contrato_{contract_info['numero'].replace('/', '-')}.{ext}"

    # ── 8. Upload GCS
    gcs_path = upload_contract_to_gcs(
        cpf=cpf_clean,
        filename=filename,
        content=file_bytes,
        content_type="application/pdf" if ext == "pdf" else "text/markdown",
    )

    # ── 9. Persistir no banco
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
                cd = ContractDependent(
                    contract_id=contract.id,
                    nome_completo=dep.get("nome_completo", ""),
                    cpf=dep.get("cpf", ""),
                    rg=dep.get("rg", ""),
                    data_nascimento=dep.get("data_nascimento", ""),
                    idade=dep.get("idade"),
                    parentesco=dep.get("parentesco", ""),
                    faixa_etaria=dep.get("faixa_etaria", ""),
                    valor_plano=dep.get("valor_plano", ""),
                )
                db.add(cd)

        db.commit()
        contract_id = str(contract.id)

    logger.info(f"✅ Contrato {contract_info['numero']} gerado | GCS: {gcs_path}")
    return {
        "success": True,
        "contract_id": contract_id,
        "gcs_path": gcs_path,
        "filename": filename,
        "contract_number": contract_info["numero"],
    }
