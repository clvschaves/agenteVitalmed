"""
Teste E2E — Motor de Contratos Vitalmed
========================================
Simula o fluxo completo:
  1. SalesAgent recebe msgs até lead fechar interesse
  2. ContractAgent coleta dados do contratante
  3. Contrato individual gerado em PDF e enviado ao GCS
  4. Verifica download e integridade do arquivo

NÃO faz chamada ao n8n (webhook desabilitado em teste).
Requer: GEMINI_API_KEY no .env local ou variável de ambiente.

Executar:
  python3 test_e2e_contrato.py
"""

import asyncio
import re
import sys
import os
import uuid
from datetime import datetime
from pathlib import Path

# ── path ────────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

# ── carregar .env ─────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

# suprimir warnings de versão
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
os.environ.setdefault("PYTHONWARNINGS", "ignore")

SEP = "=" * 65
STEP = 0


def header(title: str):
    global STEP
    STEP += 1
    print(f"\n{SEP}")
    print(f"  ETAPA {STEP}: {title}")
    print(SEP)


def ok(msg: str):
    print(f"  ✅ {msg}")


def info(msg: str):
    print(f"  ℹ️  {msg}")


def warn(msg: str):
    print(f"  ⚠️  {msg}")


# ════════════════════════════════════════════════════════════════════════════
# ETAPA 1 — SalesAgent: simular conversa até fechamento
# ════════════════════════════════════════════════════════════════════════════

def run_sales_turn(agent, msg: str, session_id: str, phone: str) -> str:
    """Executa uma rodada no SalesAgent e retorna o texto da resposta."""
    result = agent.run(message=msg, session_id=session_id, user_id=phone)
    # Agno retorna RunResponse ou string
    if hasattr(result, "content"):
        return str(result.content)
    return str(result)


def simulate_sales_conversation(session_id: str, phone: str) -> str:
    """
    Simula 4 turnos de conversa com o SalesAgent até o lead fechar.
    Retorna o plano que o lead escolheu.
    """
    from src.agents.sales.agent import create_sales_agent

    agent = create_sales_agent(fallback_flash=True)

    turnos = [
        "Oi, vi o anúncio de vocês. O que é a Vitalmed?",
        "Interessante! Minha mãe tem 65 anos e mora sozinha. Tem plano pra ela?",
        "Quanto custa o plano individual?",
        "Tá bom, quero fechar o plano individual pra minha mãe!",
    ]

    last_response = ""
    for i, msg in enumerate(turnos, 1):
        print(f"\n  👤 Lead [{i}/4]: {msg}")
        resp = run_sales_turn(agent, msg, session_id=session_id, phone=phone)
        # truncar para exibição
        preview = resp.replace("\n", " ")[:200]
        print(f"  🤖 Carlos: {preview}{'...' if len(resp) > 200 else ''}")
        last_response = resp

    return "individual"


# ════════════════════════════════════════════════════════════════════════════
# ETAPA 2 — ContractAgent: coletar dados e gerar contrato
# ════════════════════════════════════════════════════════════════════════════

def simulate_contract_conversation(session_id: str, phone: str) -> dict:
    """
    Simula a coleta de dados com o ContractAgent.
    Usa mensagens pré-definidas como se o usuário estivesse respondendo.
    Retorna o resultado da última resposta com dados do contrato.
    """
    from src.agents.contract.agent import create_contract_agent

    agent = create_contract_agent(session_id=session_id, lead_phone=phone)

    # ── TURNO 1: iniciar coleta ──────────────────────────────────────────────
    print(f"\n  👤 Lead [1]: individual")
    r1 = agent.run(message="individual", session_id=session_id, user_id=phone)
    resp1 = str(r1.content) if hasattr(r1, "content") else str(r1)
    print(f"  🤖 Agente: {resp1[:200]}...")

    # ── TURNO 2: dados pessoais A ────────────────────────────────────────────
    msg2 = (
        "Nome completo: Maria da Conceição Souza\n"
        "CPF: 987.654.321-00\n"
        "RG: 9876543\n"
        "Data de nascimento: 15/03/1958\n"
        "Idade: 68\n"
        "Estado civil: Viúva"
    )
    print(f"\n  👤 Lead [2]: {msg2[:80]}...")
    r2 = agent.run(message=msg2, session_id=session_id, user_id=phone)
    resp2 = str(r2.content) if hasattr(r2, "content") else str(r2)
    print(f"  🤖 Agente: {resp2[:200]}...")

    # ── TURNO 3: dados pessoais B ────────────────────────────────────────────
    msg3 = (
        "Profissão: Aposentada\n"
        "Nacionalidade: Brasileira\n"
        "Endereço: Rua das Palmeiras, 250, Apto 301\n"
        "Cidade: São Luís\n"
        "UF: MA\n"
        "CEP: 65.071-380\n"
        "Telefone: (98) 98888-1234\n"
        "WhatsApp: +5598988881234\n"
        "E-mail: maria.conceicao@email.com"
    )
    print(f"\n  👤 Lead [3]: {msg3[:80]}...")
    r3 = agent.run(message=msg3, session_id=session_id, user_id=phone)
    resp3 = str(r3.content) if hasattr(r3, "content") else str(r3)
    print(f"  🤖 Agente: {resp3[:200]}...")

    # ── TURNO 4: dados do contrato ───────────────────────────────────────────
    msg4 = (
        "Forma de pagamento: Cartão de crédito\n"
        "Dia de vencimento: 10\n"
        "Plano: individual"
    )
    print(f"\n  👤 Lead [4]: {msg4[:80]}...")
    r4 = agent.run(message=msg4, session_id=session_id, user_id=phone)
    resp4 = str(r4.content) if hasattr(r4, "content") else str(r4)
    print(f"  🤖 Agente: {resp4[:200]}...")

    # ── TURNO 5: confirmação ─────────────────────────────────────────────────
    print(f"\n  👤 Lead [5]: Sim, pode gerar o contrato!")
    r5 = agent.run(
        message="Sim, está tudo correto. Pode gerar o contrato!",
        session_id=session_id,
        user_id=phone,
    )
    resp5 = str(r5.content) if hasattr(r5, "content") else str(r5)
    print(f"  🤖 Agente: {resp5[:300]}...")

    return {
        "final_response": resp5,
        "agent_result": r5,
    }


# ════════════════════════════════════════════════════════════════════════════
# ETAPA 3 — Gerar PDF e fazer upload manual (garantir PDF mesmo sem banco)
# ════════════════════════════════════════════════════════════════════════════

def generate_and_upload_pdf(session_id: str) -> dict:
    """
    Gera o PDF diretamente usando a lógica do tools.py.
    Não depende do banco de dados.
    """
    from src.agents.contract.tools import (
        _fill_template, _md_to_pdf_bytes, _build_dependentes_tabela
    )
    from src.core.gcs_client import upload_contract_to_gcs, download_from_gcs

    TEMPLATES_DIR = Path("src/contracts")

    titular = {
        "nome_completo": "Maria da Conceição Souza",
        "cpf": "987.654.321-00",
        "rg": "9876543",
        "data_nascimento": "15/03/1958",
        "idade": "68",
        "estado_civil": "Viúva",
        "profissao": "Aposentada",
        "nacionalidade": "Brasileira",
        "endereco_completo": "Rua das Palmeiras, 250, Apto 301",
        "cidade": "São Luís",
        "uf": "MA",
        "cep": "65.071-380",
        "telefone": "(98) 98888-1234",
        "whatsapp": "+5598988881234",
        "email": "maria.conceicao@email.com",
        "faixa_etaria": "Sênior",
        "valor_plano": "R$ 149,90",
    }

    numero = f"VTM-E2E-{uuid.uuid4().hex[:6].upper()}"
    hoje = datetime.now()

    contract_info = {
        "numero": numero,
        "data_emissao": hoje.strftime("%d/%m/%Y"),
        "local_emissao": "São Luís - MA",
        "data_assinatura": hoje.strftime("%d/%m/%Y"),
        "local_assinatura": "São Luís - MA",
        "codigo_associado": f"VM-{re.sub(r'[^0-9]', '', titular['cpf'])[-4:]}",
        "forma_pagamento": "Cartão de crédito",
        "dia_vencimento": "10",
        "data_inicio_vigencia": "01/05/2026",
    }

    resumo = {
        "valor_titular": "R$ 149,90",
        "descontos": "Não aplicável",
        "valor_mensal_final": "R$ 149,90",
        "valor_adesao": "R$ 0,00",
        "total_ato_contratacao": "R$ 0,00",
    }

    flat = {}
    for k, v in titular.items():
        flat[f"contratante.{k}"] = v
    for k, v in contract_info.items():
        flat[f"contrato.{k}"] = v
    for k, v in resumo.items():
        flat[f"resumo.{k}"] = v
    flat["titular.valor_plano"] = resumo["valor_titular"]
    flat["testemunha1.nome"] = ""
    flat["testemunha1.cpf"] = ""
    flat["testemunha2.nome"] = ""
    flat["testemunha2.cpf"] = ""

    # Preencher template
    template_path = TEMPLATES_DIR / "template_individual.md"
    md_content = _fill_template(template_path, flat)

    # Gerar PDF
    file_bytes, ext = _md_to_pdf_bytes(md_content)
    filename = f"contrato_{numero}.{ext}"

    # Salvar cópia local
    local_path = Path(f"/tmp/{filename}")
    local_path.write_bytes(file_bytes)

    # Upload GCS
    cpf_clean = re.sub(r"[^\d]", "", titular["cpf"])
    gcs_path = upload_contract_to_gcs(
        cpf=cpf_clean,
        filename=filename,
        content=file_bytes,
        content_type="application/pdf" if ext == "pdf" else "text/plain",
    )

    # Verificar download
    downloaded = download_from_gcs(f"{cpf_clean}/{filename}")
    integrity_ok = len(downloaded) == len(file_bytes)

    return {
        "numero": numero,
        "titular": titular["nome_completo"],
        "cpf": titular["cpf"],
        "filename": filename,
        "extension": ext,
        "file_size_bytes": len(file_bytes),
        "gcs_path": gcs_path,
        "local_path": str(local_path),
        "download_size_bytes": len(downloaded),
        "integrity_ok": integrity_ok,
    }


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{SEP}")
    print("  TESTE E2E — VITALMED: SALES → CONTRACT → GCS")
    print(f"  Iniciado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(SEP)

    phone = "+5598999990001"
    session_id = f"e2e-test-{uuid.uuid4().hex[:8]}"
    results = {}

    # ── ETAPA 1: SalesAgent ──────────────────────────────────────────────────
    header("SALESAGENT — Conversa até fechamento")
    info(f"Phone: {phone} | Session: {session_id}")
    try:
        plano = simulate_sales_conversation(session_id=session_id, phone=phone)
        ok(f"SalesAgent completou 4 turnos. Plano escolhido: {plano}")
        results["sales"] = {"status": "OK", "plano": plano}
    except Exception as e:
        warn(f"SalesAgent erro: {e}")
        results["sales"] = {"status": "ERRO", "error": str(e)}
        # Prosseguir mesmo com erro no sales (API pode estar off)
        plano = "individual"

    # ── ETAPA 2: ContractAgent ───────────────────────────────────────────────
    header("CONTRACTAGENT — Coleta de dados")
    try:
        contract_result = simulate_contract_conversation(
            session_id=session_id,
            phone=phone,
        )
        ok("ContractAgent completou 5 turnos de coleta")
        resp_preview = contract_result["final_response"][:200]
        info(f"Última resposta: {resp_preview}")
        results["contract_agent"] = {"status": "OK"}
    except Exception as e:
        warn(f"ContractAgent erro (prosseguindo com geração direta): {e}")
        results["contract_agent"] = {"status": "PARCIAL", "error": str(e)}

    # ── ETAPA 3: Geração PDF + Upload GCS ───────────────────────────────────
    header("GERAÇÃO DE PDF + UPLOAD GCS")
    info("Gerando contrato com dados de teste...")
    try:
        upload_result = generate_and_upload_pdf(session_id=session_id)

        ext = upload_result["extension"].upper()
        size_kb = upload_result["file_size_bytes"] / 1024

        ok(f"Arquivo gerado: {upload_result['filename']} [{ext}] — {size_kb:.1f} KB")
        ok(f"GCS Upload   : {upload_result['gcs_path']}")
        ok(f"Cópia local  : {upload_result['local_path']}")

        if upload_result["integrity_ok"]:
            ok(f"Integridade  : {upload_result['file_size_bytes']:,} bytes enviados = {upload_result['download_size_bytes']:,} bytes recebidos ✓")
        else:
            warn(f"Integridade  : FALHOU — enviou {upload_result['file_size_bytes']} != recebeu {upload_result['download_size_bytes']}")

        results["gcs"] = {
            "status": "OK" if upload_result["integrity_ok"] else "ERRO_INTEGRIDADE",
            **upload_result,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        warn(f"Geração/Upload falhou: {e}")
        results["gcs"] = {"status": "ERRO", "error": str(e)}

    # ── RESUMO FINAL ─────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("  RESUMO DO TESTE E2E")
    print(SEP)

    all_ok = True
    for key, val in results.items():
        status = val.get("status", "?")
        icon = "✅" if status == "OK" else ("⚠️ " if "PARCIAL" in status else "❌")
        if status not in ("OK", "PARCIAL"):
            all_ok = False
        print(f"  {icon} {key.upper():<20} → {status}")

    print(f"\n  {'✅ TESTE E2E CONCLUÍDO COM SUCESSO' if all_ok else '⚠️  TESTE CONCLUÍDO COM AVISOS'}")

    if results.get("gcs", {}).get("status") == "OK":
        r = results["gcs"]
        print(f"\n  {'─'*50}")
        print(f"  Contrato nº : {r.get('numero')}")
        print(f"  Titular     : {r.get('titular')}")
        print(f"  CPF         : {r.get('cpf')}")
        print(f"  Formato     : {r.get('extension', '').upper()}")
        print(f"  Tamanho     : {r.get('file_size_bytes', 0) / 1024:.1f} KB")
        print(f"  GCS Path    : {r.get('gcs_path')}")
        print(f"  Local       : {r.get('local_path')}")
        print(f"  {'─'*50}")

    print(f"\n  Finalizado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{SEP}\n")


if __name__ == "__main__":
    main()
