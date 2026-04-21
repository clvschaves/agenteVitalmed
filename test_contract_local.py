"""
Teste local end-to-end do motor de contratos:
  1. Preenche template_individual.md com dados fictícios
  2. Converte para PDF (weasyprint) ou fallback .md
  3. Faz upload para gs://contratovitalmed
  4. Faz download e verifica integridade
  5. Imprime resumo com GCS path

Executar com:
  python3 test_contract_local.py
"""
import sys
import re
import uuid
from pathlib import Path
from datetime import datetime

# ─── Garantir que o src/ está no path ────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

TEMPLATES_DIR = Path("src/contracts")

# ══════════════════════════════════════════════════════════════════════════════
#  1. DADOS DE TESTE
# ══════════════════════════════════════════════════════════════════════════════
TITULAR = {
    "nome_completo": "Maria da Conceição Souza",
    "cpf": "987.654.321-00",
    "rg": "9876543",
    "data_nascimento": "15/03/1980",
    "idade": "46",
    "estado_civil": "Casada",
    "profissao": "Professora",
    "nacionalidade": "Brasileira",
    "endereco_completo": "Rua das Palmeiras, 250, Apto 301",
    "cidade": "São Luís",
    "uf": "MA",
    "cep": "65.071-380",
    "telefone": "(98) 98888-1234",
    "whatsapp": "+5598988881234",
    "email": "maria.conceicao@email.com",
    "faixa_etaria": "Adulto I",
    "valor_plano": "R$ 89,90",
}

CONTRACT_INFO = {
    "numero": f"VTM-TESTE-{uuid.uuid4().hex[:6].upper()}",
    "data_emissao": datetime.now().strftime("%d/%m/%Y"),
    "local_emissao": "São Luís - MA",
    "data_assinatura": datetime.now().strftime("%d/%m/%Y"),
    "local_assinatura": "São Luís - MA",
    "codigo_associado": "VM-3210",
    "forma_pagamento": "Débito automático",
    "dia_vencimento": "10",
    "data_inicio_vigencia": "01/05/2026",
}

RESUMO = {
    "valor_titular": "R$ 89,90",
    "descontos": "Não aplicável",
    "valor_mensal_final": "R$ 89,90",
    "valor_adesao": "R$ 0,00",
    "total_ato_contratacao": "R$ 0,00",
}

CPF_CLEAN = re.sub(r"[^\d]", "", TITULAR["cpf"])


# ══════════════════════════════════════════════════════════════════════════════
#  2. PREENCHER TEMPLATE
# ══════════════════════════════════════════════════════════════════════════════
def fill_template(template_path: Path, flat: dict) -> str:
    content = template_path.read_text(encoding="utf-8")
    for key, value in flat.items():
        content = content.replace("{{" + key + "}}", str(value) if value else "")
    # Limpa placeholders não preenchidos
    remaining = re.findall(r"\{\{[^}]+\}\}", content)
    if remaining:
        print(f"  ⚠️  Placeholders não preenchidos: {remaining}")
    content = re.sub(r"\{\{[^}]+\}\}", "", content)
    return content


def build_flat_dict(titular: dict, contract_info: dict, resumo: dict) -> dict:
    flat = {}
    for k, v in titular.items():
        flat[f"contratante.{k}"] = v
    for k, v in contract_info.items():
        flat[f"contrato.{k}"] = v
    for k, v in resumo.items():
        flat[f"resumo.{k}"] = v
    flat["titular.valor_plano"] = resumo.get("valor_titular", "")
    flat["testemunha1.nome"] = ""
    flat["testemunha1.cpf"] = ""
    flat["testemunha2.nome"] = ""
    flat["testemunha2.cpf"] = ""
    return flat


# ══════════════════════════════════════════════════════════════════════════════
#  3. CONVERTER PARA PDF
# ══════════════════════════════════════════════════════════════════════════════
def md_to_bytes(md_content: str):
    """Retorna (bytes, extensão) — tenta PDF com weasyprint/markdown2."""
    try:
        import markdown2
        from weasyprint import HTML

        html = f"""<html><head>
        <meta charset="utf-8">
        <style>
          body {{ font-family: Arial, sans-serif; font-size: 11px; margin: 2cm; line-height: 1.5; }}
          h1 {{ font-size: 14px; text-align: center; }} h2 {{ font-size: 13px; }} h3 {{ font-size: 12px; }}
          table {{ border-collapse: collapse; width: 100%; font-size: 10px; }}
          th, td {{ border: 1px solid #ccc; padding: 4px; }}
          th {{ background: #f0f0f0; }}
        </style></head>
        <body>{markdown2.markdown(md_content, extras=["tables"])}</body></html>"""

        pdf_bytes = HTML(string=html).write_pdf()
        return pdf_bytes, "pdf"
    except Exception as e:
        print(f"  ⚠️  PDF indisponível ({type(e).__name__}: {e}) — usando fallback .md")
        return md_content.encode("utf-8"), "md"


# ══════════════════════════════════════════════════════════════════════════════
#  4. UPLOAD GCS
# ══════════════════════════════════════════════════════════════════════════════
def upload_and_verify(cpf: str, filename: str, content: bytes, content_type: str) -> str:
    from src.core.gcs_client import upload_contract_to_gcs, download_from_gcs

    # Upload
    gcs_path = upload_contract_to_gcs(
        cpf=cpf,
        filename=filename,
        content=content,
        content_type=content_type,
    )

    # Verificar fazendo download imediato
    blob_name = f"{cpf}/{filename}"
    downloaded = download_from_gcs(blob_name)
    assert len(downloaded) > 0, "Download retornou vazio!"
    assert len(downloaded) == len(content), (
        f"Tamanho inconsistente: enviou {len(content)} bytes, recebeu {len(downloaded)} bytes"
    )
    return gcs_path


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    sep = "=" * 60
    print(f"\n{sep}")
    print("  TESTE LOCAL — MOTOR DE CONTRATOS VITALMED")
    print(f"{sep}\n")

    # ── ETAPA 1: Preencher template ──────────────────────────────
    print("📄 [1/4] Preenchendo template individual...")
    template_path = TEMPLATES_DIR / "template_individual.md"
    flat = build_flat_dict(TITULAR, CONTRACT_INFO, RESUMO)
    md_content = fill_template(template_path, flat)
    print(f"  ✅ Template preenchido — {len(md_content)} caracteres")

    # Preview das primeiras linhas
    preview_lines = md_content.strip().split("\n")[:6]
    print("  📝 Preview:")
    for line in preview_lines:
        if line.strip():
            print(f"     {line[:80]}")

    # ── ETAPA 2: Converter para PDF ──────────────────────────────
    print("\n🖨️  [2/4] Convertendo para PDF...")
    file_bytes, ext = md_to_bytes(md_content)
    content_type = "application/pdf" if ext == "pdf" else "text/markdown"
    filename = f"contrato_{CONTRACT_INFO['numero']}.{ext}"
    print(f"  ✅ Arquivo gerado: {filename} ({len(file_bytes):,} bytes) [{ext.upper()}]")

    # Salvar cópia local para inspeção visual
    local_path = Path(f"/tmp/{filename}")
    local_path.write_bytes(file_bytes)
    print(f"  💾 Cópia local salva: {local_path}")

    # ── ETAPA 3: Upload GCS ──────────────────────────────────────
    print("\n☁️  [3/4] Fazendo upload para GCS...")
    gcs_path = upload_and_verify(
        cpf=CPF_CLEAN,
        filename=filename,
        content=file_bytes,
        content_type=content_type,
    )
    print(f"  ✅ Upload concluído: {gcs_path}")

    # ── ETAPA 4: Verificar download ──────────────────────────────
    print("\n🔍 [4/4] Verificando download do GCS...")
    from src.core.gcs_client import download_from_gcs
    blob_name = f"{CPF_CLEAN}/{filename}"
    downloaded = download_from_gcs(blob_name)
    print(f"  ✅ Download OK — {len(downloaded):,} bytes recebidos (esperado: {len(file_bytes):,})")

    # ── RESUMO FINAL ─────────────────────────────────────────────
    print(f"\n{sep}")
    print("  ✅ TODOS OS TESTES PASSARAM")
    print(f"{sep}")
    print(f"  Contrato  : {CONTRACT_INFO['numero']}")
    print(f"  Titular   : {TITULAR['nome_completo']}")
    print(f"  CPF       : {TITULAR['cpf']}")
    print(f"  Arquivo   : {filename}")
    print(f"  GCS Path  : {gcs_path}")
    print(f"  Cópia local: {local_path}")
    print(f"{sep}\n")


if __name__ == "__main__":
    main()
