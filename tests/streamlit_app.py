"""
Streamlit App — Agente Vitalmed
Três abas:
  1. 📁 Admin RAG: upload, indexação e gerenciamento de documentos
  2. 💬 Simulador: testa o agente enviando mensagens como se fosse um lead
  3. 👤 Leads: gestão de leads via conexão síncrona ao PostgreSQL
"""
import time
import os
import sys
from pathlib import Path

import requests
import streamlit as st
import pandas as pd

# ─── Path setup ───────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

# ─── Configuração ─────────────────────────────────────────────────────────────
API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Vitalmed — Painel de Agentes",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Sidebar
with st.sidebar:
    st.markdown("## 🏥 Vitalmed")
    st.markdown("---")
    st.markdown("**Sistema Multi-Agentes de Vendas**")
    st.markdown(f"API: `{API_URL}`")

    if st.button("🔍 Verificar API"):
        try:
            r = requests.get(f"{API_URL}/health", timeout=3)
            if r.status_code == 200:
                st.success("✅ API online")
            else:
                st.error(f"❌ API retornou {r.status_code}")
        except Exception as e:
            st.error(f"❌ API offline: {e}")

    st.markdown("---")
    st.caption("v0.1.0 | Agno + Gemini + pgvector")

# ─── Abas principais ──────────────────────────────────────────────────────────
tab_rag, tab_simulator, tab_leads = st.tabs(
    ["📁 Admin RAG", "💬 Simulador de Agente", "👤 Leads"]
)


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: Conexão síncrona ao banco (sem asyncio — compatível com Streamlit)
# ═══════════════════════════════════════════════════════════════════════════════

def _get_sync_engine():
    """Cria engine síncrona para Streamlit (não usa asyncio)."""
    from sqlalchemy import create_engine
    from src.core.config import settings
    return create_engine(settings.database_url_sync)


def _fetch_leads_sync():
    """Busca leads de forma totalmente síncrona."""
    from sqlalchemy import text
    engine = _get_sync_engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT phone, name, status, interested_plan, source,
                   last_contact_at, created_at
            FROM leads
            ORDER BY COALESCE(last_contact_at, created_at) DESC
            LIMIT 200
        """))
        return result.fetchall(), result.keys()


def _fetch_documents_sync():
    """Busca documentos indexados de forma síncrona."""
    from sqlalchemy import text
    engine = _get_sync_engine()
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT source_file, doc_type, COUNT(*) as chunks,
                   MAX(created_at) as indexed_at
            FROM knowledge_chunks
            WHERE is_active = true
            GROUP BY source_file, doc_type
            ORDER BY indexed_at DESC
        """))
        return result.fetchall(), result.keys()


# ═══════════════════════════════════════════════════════════════════════════════
# ABA 1: ADMIN RAG
# ═══════════════════════════════════════════════════════════════════════════════
with tab_rag:
    st.header("📁 Gerenciamento da Base de Conhecimento RAG")
    st.markdown("Faça upload de documentos PDF, DOCX ou vídeos para indexação na base vetorial da Vitalmed.")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("📤 Upload de Documento")
        uploaded_file = st.file_uploader(
            "Selecione um arquivo",
            type=["pdf", "docx", "mp4", "mkv", "mov"],
            help="PDFs e DOCX são indexados diretamente. Vídeos passam por transcrição.",
        )

        if uploaded_file and st.button("🚀 Indexar Documento", type="primary"):
            with st.spinner(f"Enviando {uploaded_file.name} para indexação..."):
                try:
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                    r = requests.post(f"{API_URL}/admin/upload", files=files, timeout=60)
                    r.raise_for_status()
                    data = r.json()
                    st.success(f"✅ **{data['filename']}** enviado para indexação!")
                    st.info(f"Status: `{data['status']}` | Tipo: `{data['doc_type']}`")
                    st.caption("O pipeline roda em background. Atualize a lista em alguns segundos.")
                except Exception as e:
                    st.error(f"❌ Erro no upload: {e}")

    with col2:
        st.subheader("📋 Documentos Indexados")

        if st.button("🔄 Atualizar Lista", key="refresh_docs"):
            st.rerun()

        try:
            rows, keys = _fetch_documents_sync()
            if not rows:
                st.info("Nenhum documento indexado ainda.\n\nFaça upload de PDFs ou DOCX da Vitalmed para começar.")
            else:
                df_docs = pd.DataFrame(rows, columns=list(keys))
                df_docs.columns = ["Arquivo", "Tipo", "Chunks", "Indexado em"]
                df_docs["Indexado em"] = df_docs["Indexado em"].astype(str).str[:16]
                st.dataframe(df_docs, use_container_width=True, hide_index=True)
                st.caption(f"Total: {df_docs['Chunks'].sum()} chunks indexados em {len(df_docs)} documento(s)")

        except Exception as e:
            st.warning(f"Não foi possível carregar documentos: {e}")
            st.caption("Certifique-se que PostgreSQL está rodando na porta 5433.")


# ═══════════════════════════════════════════════════════════════════════════════
# ABA 2: SIMULADOR DE AGENTE
# ═══════════════════════════════════════════════════════════════════════════════
with tab_simulator:
    st.header("💬 Simulador de Conversa com Agente")
    st.markdown("Simule uma mensagem de lead chegando pelo WhatsApp e observe o agente processar e responder.")

    col_form, col_result = st.columns([1, 1])

    with col_form:
        st.subheader("📋 Dados do Lead (simulado)")

        # Preset de leads mockados
        preset_leads = {
            "João Carlos Mendes (5511991110001)": ("5511991110001", "João Carlos Mendes"),
            "Maria Aparecida Silva (5511991110002)": ("5511991110002", "Maria Aparecida Silva"),
            "Carlos Eduardo Martins (5511991110007)": ("5511991110007", "Carlos Eduardo Martins"),
            "Personalizado": ("", ""),
        }
        preset = st.selectbox("Lead pré-cadastrado", list(preset_leads.keys()))
        preset_phone, preset_name = preset_leads[preset]

        sim_phone = st.text_input("Telefone", value=preset_phone or "5511999990001")
        sim_name = st.text_input("Nome", value=preset_name or "Novo Lead Teste")
        sim_message = st.text_area(
            "Mensagem do lead",
            value="Olá, vi que vocês têm plano de UTI móvel. Quanto custa para uma família de 4 pessoas?",
            height=120,
        )
        polling_interval = st.slider("Intervalo de polling (s)", 2, 10, 3)

        if st.button("📤 Enviar mensagem ao agente", type="primary"):
            with st.spinner("Enviando para o agente..."):
                try:
                    payload = {
                        "phone": sim_phone,
                        "name": sim_name,
                        "message": sim_message,
                        "source": "streamlit_simulator",
                    }
                    r = requests.post(f"{API_URL}/webhook/message", json=payload, timeout=10)
                    r.raise_for_status()
                    data = r.json()
                    st.session_state["current_job_id"] = data["job_id"]
                    st.session_state["polling"] = True
                    st.session_state["sim_messages"] = st.session_state.get("sim_messages", [])
                    st.session_state["sim_messages"].append({
                        "role": "user",
                        "phone": sim_phone,
                        "name": sim_name,
                        "content": sim_message,
                    })
                    st.success(f"✅ Mensagem enviada! Job: `{data['job_id']}`")
                except Exception as e:
                    st.error(f"❌ Erro ao enviar: {e}")

    with col_result:
        st.subheader("📨 Resposta do Agente")

        # Histórico de conversa
        if "sim_messages" in st.session_state and st.session_state["sim_messages"]:
            for msg in st.session_state["sim_messages"]:
                if msg["role"] == "user":
                    st.chat_message("user").markdown(f"**{msg.get('name', 'Lead')}**\n\n{msg['content']}")
                else:
                    with st.chat_message("assistant"):
                        st.markdown(f"**{msg.get('agent', 'Agente')}**\n\n{msg['content']}")
                        if msg.get("tools"):
                            st.caption(f"🔧 Tools: {msg['tools']}")

        if "current_job_id" in st.session_state and st.session_state.get("polling"):
            job_id = st.session_state["current_job_id"]
            status_placeholder = st.empty()

            max_attempts = 40
            for attempt in range(max_attempts):
                try:
                    r = requests.get(f"{API_URL}/webhook/status/{job_id}", timeout=5)
                    r.raise_for_status()
                    status_data = r.json()
                    status = status_data.get("status", "processing")

                    if status == "processing":
                        status_placeholder.info(f"⏳ Agente pensando... ({attempt + 1}/{max_attempts})")
                        time.sleep(polling_interval)
                        continue

                    elif status == "done":
                        status_placeholder.empty()
                        response = status_data.get("response", "")
                        agent = status_data.get("agent_used", "agente")
                        tools = ", ".join(status_data.get("tools_called", [])) or "nenhuma"

                        # Adicionar ao histórico
                        if "sim_messages" not in st.session_state:
                            st.session_state["sim_messages"] = []
                        st.session_state["sim_messages"].append({
                            "role": "assistant",
                            "agent": f"AssistantAgent ({agent})",
                            "content": response,
                            "tools": tools,
                        })
                        st.session_state["polling"] = False
                        st.rerun()
                        break

                    elif status == "error":
                        status_placeholder.error(f"❌ Erro: {status_data.get('response', 'Erro desconhecido')}")
                        st.session_state["polling"] = False
                        break

                except Exception as e:
                    status_placeholder.warning(f"Polling tentativa {attempt + 1}: {e}")
                    time.sleep(2)
            else:
                status_placeholder.error("⏱️ Timeout — agente não respondeu.")
                st.session_state["polling"] = False

        elif "sim_messages" not in st.session_state or not st.session_state.get("sim_messages"):
            st.info("💡 Selecione um lead pré-cadastrado e envie uma mensagem para iniciar a simulação.")

        if st.session_state.get("sim_messages"):
            if st.button("🗑️ Limpar chat", key="clear_chat"):
                st.session_state["sim_messages"] = []
                st.session_state.pop("current_job_id", None)
                st.session_state["polling"] = False
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# ABA 3: LEADS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_leads:
    st.header("👤 Gestão de Leads")
    st.markdown("Visualize o status e histórico dos leads que interagiram com o sistema.")

    col_refresh, col_stats = st.columns([1, 3])
    with col_refresh:
        if st.button("🔄 Atualizar", key="refresh_leads"):
            st.rerun()

    try:
        rows, keys = _fetch_leads_sync()

        if not rows:
            st.info("Nenhum lead registrado ainda.")
        else:
            df = pd.DataFrame(rows, columns=list(keys))
            df.columns = ["Telefone", "Nome", "Status", "Plano Interesse", "Fonte", "Último contato", "Criado em"]
            df["Nome"] = df["Nome"].fillna("—")
            df["Plano Interesse"] = df["Plano Interesse"].fillna("—")
            df["Fonte"] = df["Fonte"].fillna("—")
            df["Último contato"] = df["Último contato"].astype(str).str[:16].replace("None", "—")

            # Stats rápidos
            with col_stats:
                status_counts = df["Status"].value_counts()
                cols = st.columns(min(len(status_counts), 5))
                status_colors = {
                    "novo": "🟡", "em_atendimento": "🔵", "interessado": "🟢",
                    "fechado": "✅", "escalado": "🟠", "perdido": "🔴",
                    "nao_interessado": "⚫", "sem_retorno": "⬜",
                }
                for i, (status, count) in enumerate(status_counts.items()):
                    if i < 5:
                        icon = status_colors.get(status, "⚪")
                        cols[i].metric(f"{icon} {status}", count)

            st.markdown("---")

            # Filtros
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                status_filter = st.multiselect("Filtrar por status", sorted(df["Status"].unique().tolist()))
            with col_f2:
                search = st.text_input("🔍 Buscar por nome ou telefone")

            if status_filter:
                df = df[df["Status"].isin(status_filter)]
            if search:
                mask = (
                    df["Nome"].str.contains(search, case=False, na=False) |
                    df["Telefone"].str.contains(search, na=False)
                )
                df = df[mask]

            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption(f"Total: {len(df)} leads | Filtros ativos: {'Sim' if status_filter or search else 'Não'}")

    except Exception as e:
        st.warning(f"Não foi possível carregar leads: {e}")
        st.caption("Certifique-se que o PostgreSQL está rodando (porta 5433) e as migrations foram aplicadas.")
