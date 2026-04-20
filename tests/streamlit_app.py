"""
Streamlit App — Agente Vitalmed (v2)
Abas:
  1. 📁 Admin RAG       — upload e gestão de documentos vetoriais
  2. 💬 Simulador       — testa o agente como um lead real
  3. 👤 Leads           — gestão e filtros de leads
  4. 🧠 Memória         — visualiza e edita memória longa dos leads
  5. 🤖 Construtor      — cria/atualiza contexto dos agentes
  6. 🔌 MCP             — integração rápida com servidores MCP
"""
import time
import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime

import requests
import streamlit as st
import pandas as pd

# ─── Path setup ───────────────────────────────────────────────────
# ─── Funções de detecção (devem vir ANTES dos blocos de inicialização) ─────────────

def _test_db_connection(db_url: str) -> tuple[bool, str]:
    """Testa conexao com o banco de forma totalmente silenciosa."""
    import sys
    import io
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.pool import NullPool
        devnull = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = devnull
        try:
            engine = create_engine(
                db_url,
                poolclass=NullPool,
                connect_args={"connect_timeout": 3},
                echo=False,
            )
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True, ""
        finally:
            sys.stderr = old_stderr
    except Exception as e:
        msg = str(e).split("\n")[0][:120]
        return False, msg


def _test_service(url: str, path: str = "/health") -> bool:
    """Testa se um endpoint HTTP está respondendo, de forma silenciosa."""
    if not url:
        return False
    try:
        r = requests.get(f"{url.rstrip('/')}{path}", timeout=2)
        return r.status_code < 500
    except Exception:
        return False


# ─── Ambientes pré-definidos ──────────────────────────────────────────────────
# Detecta se está rodando DENTRO do Docker no servidor (API_URL injetada pelo compose)
_DOCKER_API_URL = os.environ.get("API_URL", "")
_DOCKER_DB_URL = (
    os.environ.get("DATABASE_URL_SYNC", "")
    or os.environ.get("DATABASE_URL", "").replace("+asyncpg", "")
)

ENVIRONMENTS = {
    "🏠 Local (docker-compose)": {
        "api_url": "http://localhost:8000",
        "db_url": "postgresql://vitalmed:vitalmed123@localhost:5433/vitalmed_db",
    },
    "💻 Local sem banco (só memória/agentes)": {
        "api_url": "http://localhost:8000",
        "db_url": "",
    },
    "🚀 Servidor (37.27.208.115)": {
        "api_url": "http://37.27.208.115:8000",
        "db_url": "postgresql://vitalmed:vitalmed123@37.27.208.115:5435/vitalmed_db",
    },
    "⚙️ Custom": {
        "api_url": "",
        "db_url": "",
    },
}

# Inicializa ambiente na sessão (só uma vez)
if "env_name" not in st.session_state:
    # Se estiver dentro do Docker no servidor, usa as variáveis de ambiente
    if _DOCKER_API_URL and "api" in _DOCKER_API_URL:
        # Rodando no servidor via docker-compose
        _auto_env = "🚀 Servidor (37.27.208.115)"
        _auto_api = _DOCKER_API_URL
        _auto_db = _DOCKER_DB_URL
    else:
        # Rodando localmente — detecta qual ambiente responde
        _auto_env = "💻 Local sem banco (só memória/agentes)"
        _auto_api = ENVIRONMENTS[_auto_env]["api_url"]
        _auto_db = ""
        for _name, _cfg in ENVIRONMENTS.items():
            if _name == "⚙️ Custom":
                continue
            if _test_service(_cfg["api_url"]):
                _auto_env = _name
                _auto_api = _cfg["api_url"]
                _auto_db = _cfg["db_url"]
                break

    st.session_state["env_name"] = _auto_env
    st.session_state["api_url"] = _auto_api
    st.session_state["db_url_override"] = _auto_db
    # No servidor, sobrescreve o preset com a URL interna real
    if _DOCKER_API_URL:
        ENVIRONMENTS["🚀 Servidor (37.27.208.115)"]["api_url"] = _DOCKER_API_URL
    if _DOCKER_DB_URL:
        ENVIRONMENTS["🚀 Servidor (37.27.208.115)"]["db_url"] = _DOCKER_DB_URL

# Detecta DB
if "db_available" not in st.session_state:
    _db_url = st.session_state["db_url_override"]
    if _db_url:
        _ok, _err = _test_db_connection(_db_url)
    else:
        _ok, _err = False, "Sem URL configurada"
    st.session_state["db_available"] = _ok
    st.session_state["db_url"] = _db_url

API_URL: str = st.session_state["api_url"]
DB_URL: str = st.session_state["db_url"]
DB_AVAILABLE: bool = st.session_state["db_available"]
PALACE_DIR = Path(__file__).parent.parent / "src" / "memory" / "palace" / "leads"
AGENTS_DIR = Path(__file__).parent.parent / "src" / "agents"

st.set_page_config(
    page_title="Vitalmed — Painel de Agentes",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
.stTabs [data-baseweb="tab-list"] { gap: 8px; }
.stTabs [data-baseweb="tab"] {
    padding: 8px 16px;
    border-radius: 8px 8px 0 0;
    font-weight: 500;
}
.memory-card {
    background: #f8f9fa;
    border-left: 3px solid #2196F3;
    padding: 10px 14px;
    border-radius: 4px;
    margin: 6px 0;
    font-family: monospace;
    font-size: 13px;
}
.agent-card {
    background: #f0f7ff;
    border: 1px solid #bbdefb;
    border-radius: 8px;
    padding: 12px;
    margin: 8px 0;
}
</style>
""", unsafe_allow_html=True)

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏥 Vitalmed")
    st.markdown("**Painel de Agentes**")
    st.markdown("---")

    # ─── Seletor de ambiente ──────────────────────────────────────────
    st.markdown("##### 🌍 Ambiente")
    env_choice = st.selectbox(
        "Ambiente",
        list(ENVIRONMENTS.keys()),
        index=list(ENVIRONMENTS.keys()).index(
            st.session_state.get("env_name", "💻 Local sem banco (só memória/agentes)")
        ),
        key="env_selector",
        label_visibility="collapsed",
    )

    # Campo custom só aparece no modo Custom
    if env_choice == "⚙️ Custom":
        custom_api = st.text_input("API URL", value=st.session_state.get("api_url", ""), key="custom_api")
        custom_db = st.text_input("DB URL", value=st.session_state.get("db_url", ""), key="custom_db", type="password")
        ENVIRONMENTS["⚙️ Custom"]["api_url"] = custom_api
        ENVIRONMENTS["⚙️ Custom"]["db_url"] = custom_db

    if st.button("🔄 Aplicar ambiente", use_container_width=True):
        cfg = ENVIRONMENTS[env_choice]
        st.session_state["env_name"] = env_choice
        st.session_state["api_url"] = cfg["api_url"]
        st.session_state["db_url_override"] = cfg["db_url"]
        # Redefine cache de DB para detectar novamente
        for k in ["db_available", "db_url"]:
            st.session_state.pop(k, None)
        st.rerun()

    st.markdown("---")

    # ─── Status contextual ───────────────────────────────────────────
    st.markdown("##### 📡 Status")
    _env_name = st.session_state.get("env_name", "")
    _is_local_docker = "docker-compose" in _env_name
    _is_server = "Servidor" in _env_name

    _api_status = _test_service(API_URL)

    if _api_status:
        st.markdown("✅ **API:** Online")
    else:
        st.markdown("⚠️ **API:** Offline")
        if _is_local_docker:
            st.caption("▶ Inicie o Docker: `docker compose up -d`")
        elif _is_server:
            st.caption("▶ Verifique conectividade com o servidor")

    if DB_AVAILABLE:
        st.markdown("✅ **Banco:** Online")
    elif not DB_URL:
        st.markdown("ℹ️ **Banco:** Não usado neste modo")
    else:
        st.markdown("⚠️ **Banco:** Offline")
        if _is_local_docker:
            st.caption("▶ `docker compose up -d postgres`")

    st.caption(f"🌐 `{API_URL}`")
    st.markdown("---")
    st.caption("v2.0.0 | Agno + Gemini")
    st.caption("💡 Memória/Agentes: sem banco necessário")



# ─── Helpers DB ───────────────────────────────────────────────────────────────
def _get_sync_engine():
    from sqlalchemy import create_engine
    return create_engine(DB_URL, connect_args={"connect_timeout": 5})

def _db_offline_notice(key: str = "reconnect_db"):
    """Mostra aviso amigável quando banco está offline — sem erros técnicos."""
    env_name = st.session_state.get("env_name", "")
    st.info(
        "🗄️ **Banco de dados não disponível neste ambiente.**\n\n"
        "Esta aba requer conexão com o PostgreSQL.\n\n"
        "👈 Na sidebar, selecione **🚀 Servidor** e clique em **Aplicar ambiente** "
        "para conectar ao banco de produção — ou inicie o Docker localmente."
    )
    if st.button("🔄 Reconectar", key=key):
        for k in ["db_available", "db_url"]:
            st.session_state.pop(k, None)
        st.rerun()

def _fetch_leads_sync():
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
# ABAS
# ═══════════════════════════════════════════════════════════════════════════════
tab_rag, tab_simulator, tab_leads, tab_memory, tab_builder, tab_mcp = st.tabs([
    "📁 Admin RAG",
    "💬 Simulador de Agente",
    "👤 Leads",
    "🧠 Memória dos Leads",
    "🤖 Construtor de Agentes",
    "🔌 Integração MCP",
])


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

        if not DB_AVAILABLE:
            _db_offline_notice(key="reconnect_db_rag")
        else:
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
                st.caption("Certifique-se que PostgreSQL está rodando.")


# ═══════════════════════════════════════════════════════════════════════════════
# ABA 2: SIMULADOR DE AGENTE
# ═══════════════════════════════════════════════════════════════════════════════
with tab_simulator:
    st.header("💬 Simulador de Conversa com Agente")
    st.markdown("Simule uma mensagem de lead chegando pelo WhatsApp e observe o agente processar e responder.")

    col_form, col_result = st.columns([1, 1])

    with col_form:
        st.subheader("📋 Dados do Lead (simulado)")

        preset_leads = {
            "João Carlos Mendes (5511991110001)": ("5511991110001", "João Carlos Mendes"),
            "Maria Aparecida Silva (5511991110002)": ("5511991110002", "Maria Aparecida Silva"),
            "Carlos Eduardo Martins (5511991110007)": ("5511991110007", "Carlos Eduardo Martins"),
            "Josefina (5511999990003)": ("5511999990003", "Josefina"),
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
                        "role": "user", "phone": sim_phone,
                        "name": sim_name, "content": sim_message,
                    })
                    st.success(f"✅ Mensagem enviada! Job: `{data['job_id']}`")
                except Exception as e:
                    st.error(f"❌ Erro ao enviar: {e}")

    with col_result:
        st.subheader("📨 Resposta do Agente")

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

            for attempt in range(40):
                try:
                    r = requests.get(f"{API_URL}/webhook/status/{job_id}", timeout=5)
                    r.raise_for_status()
                    status_data = r.json()
                    status = status_data.get("status", "processing")

                    if status == "processing":
                        status_placeholder.info(f"⏳ Agente pensando... ({attempt + 1}/40)")
                        time.sleep(polling_interval)
                        continue
                    elif status == "done":
                        status_placeholder.empty()
                        response = status_data.get("response", "")
                        agent = status_data.get("agent_used", "agente")
                        tools = ", ".join(status_data.get("tools_called", [])) or "nenhuma"
                        if "sim_messages" not in st.session_state:
                            st.session_state["sim_messages"] = []
                        st.session_state["sim_messages"].append({
                            "role": "assistant",
                            "agent": f"AssistantAgent ({agent})",
                            "content": response, "tools": tools,
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

    if not DB_AVAILABLE:
        _db_offline_notice(key="reconnect_db_leads")
    else:
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
            st.caption("Certifique-se que o PostgreSQL está rodando e as migrations foram aplicadas.")


# ═══════════════════════════════════════════════════════════════════════════════
# ABA 4: MEMÓRIA DOS LEADS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_memory:
    st.header("🧠 Memória de Longo Prazo dos Leads")
    st.markdown("Visualize e edite os arquivos de memória (palace) de cada lead. Esses dados são injetados no contexto do agente a cada mensagem.")

    col_sel, col_mem = st.columns([1, 2])

    with col_sel:
        st.subheader("Selecionar Lead")

        # Lista de leads com memória
        if PALACE_DIR.exists():
            available_leads = sorted([d.name for d in PALACE_DIR.iterdir() if d.is_dir()])
        else:
            available_leads = []

        if not available_leads:
            st.warning("Nenhuma memória de lead encontrada.")
            st.caption(f"Esperado em: `{PALACE_DIR}`")
        else:
            selected_lead = st.selectbox(
                f"Leads com memória ({len(available_leads)})",
                available_leads,
                key="memory_lead_select"
            )

            lead_dir = PALACE_DIR / selected_lead

            # Arquivos de memória disponíveis
            memory_files = {
                "👤 Perfil": "profile.md",
                "📋 Fatos Confirmados": "hall_facts.md",
                "📅 Histórico de Sessões": "hall_events.md",
                "⭐ Preferências": "hall_preferences.md",
            }

            selected_file_label = st.radio(
                "Arquivo de memória",
                list(memory_files.keys()),
                key="memory_file_select"
            )

            # Stats rápidos
            st.markdown("---")
            st.caption("**Resumo desta memória:**")
            for label, fname in memory_files.items():
                fpath = lead_dir / fname
                if fpath.exists():
                    lines = [l for l in fpath.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
                    st.caption(f"{label}: {len(lines)} entradas")

    with col_mem:
        if available_leads and selected_lead:
            st.subheader(f"📄 {selected_file_label} — `{selected_lead}`")

            selected_fname = memory_files[selected_file_label]
            fpath = lead_dir / selected_fname

            if fpath.exists():
                current_content = fpath.read_text(encoding="utf-8")
            else:
                current_content = f"# {selected_file_label} — {selected_lead}\n\n_Arquivo não encontrado._\n"

            # Editor
            new_content = st.text_area(
                "Conteúdo (edite diretamente):",
                value=current_content,
                height=400,
                key=f"mem_editor_{selected_lead}_{selected_fname}"
            )

            col_save, col_clear = st.columns([1, 1])
            with col_save:
                if st.button("💾 Salvar alterações", type="primary", key="save_mem"):
                    try:
                        fpath.parent.mkdir(parents=True, exist_ok=True)
                        fpath.write_text(new_content, encoding="utf-8")
                        st.success("✅ Memória salva com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao salvar: {e}")

            with col_clear:
                if st.button("🗑️ Limpar arquivo", key="clear_mem"):
                    header = f"# {selected_file_label} — {selected_lead}\n\n"
                    try:
                        fpath.write_text(header, encoding="utf-8")
                        st.success("✅ Arquivo limpo!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro: {e}")

            # Preview formatado
            st.markdown("---")
            st.subheader("👁️ Preview")
            entries = [l for l in current_content.splitlines() if l.strip() and not l.startswith("#")]
            if entries:
                for entry in entries:
                    st.markdown(f'<div class="memory-card">{entry}</div>', unsafe_allow_html=True)
            else:
                st.info("Sem entradas neste arquivo.")


# ═══════════════════════════════════════════════════════════════════════════════
# ABA 5: CONSTRUTOR DE AGENTES
# ═══════════════════════════════════════════════════════════════════════════════
with tab_builder:
    st.header("🤖 Construtor e Editor de Agentes")
    st.markdown("Visualize e atualize o contexto e o prompt dos agentes do sistema. As alterações são aplicadas no próximo restart da API.")

    AGENT_NAMES = {
        "🛒 SalesAgent (Vendas)": "sales",
        "❓ DoubtsAgent (Dúvidas)": "doubts",
        "🤝 AssistantAgent (Atendimento)": "assistant",
        "🔀 RouterAgent (Roteador)": "router",
    }

    col_ag_sel, col_ag_edit = st.columns([1, 2])

    with col_ag_sel:
        st.subheader("Selecionar Agente")
        selected_agent_label = st.selectbox("Agente", list(AGENT_NAMES.keys()))
        agent_key = AGENT_NAMES[selected_agent_label]
        agent_dir = AGENTS_DIR / agent_key

        # Arquivos editáveis
        editable_files = {}
        context_md = agent_dir / "CONTEXT.md"
        agent_py = agent_dir / "agent.py"

        if context_md.exists():
            editable_files["📋 CONTEXT.md (Prompt/Instruções)"] = context_md
        if agent_py.exists():
            editable_files["⚙️ agent.py (Configuração)"] = agent_py

        selected_file_label_ag = st.radio(
            "Arquivo do agente",
            list(editable_files.keys()) if editable_files else ["Nenhum arquivo disponível"],
            key="agent_file_select"
        )

        st.markdown("---")
        st.info("💡 **Dica:** Edite o `CONTEXT.md` para ajustar o prompt, personalidade e regras de negócio do agente. O `agent.py` configura o modelo e parâmetros.")

        # Criar novo agente
        st.markdown("---")
        st.subheader("➕ Novo Agente")
        with st.expander("Criar um novo agente"):
            new_agent_name = st.text_input("Nome do agente (ex: support)", key="new_agent_name")
            new_agent_role = st.text_area(
                "Descrição / papel do agente",
                placeholder="Ex: Agente especializado em suporte técnico pós-venda...",
                height=80,
                key="new_agent_role"
            )
            new_agent_model = st.selectbox(
                "Modelo LLM",
                ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
                key="new_agent_model"
            )

            if st.button("🚀 Criar Agente", type="primary", key="create_agent_btn"):
                if not new_agent_name.strip():
                    st.error("Nome do agente é obrigatório.")
                else:
                    try:
                        new_dir = AGENTS_DIR / new_agent_name.strip().lower()
                        new_dir.mkdir(parents=True, exist_ok=True)

                        # __init__.py
                        (new_dir / "__init__.py").write_text("", encoding="utf-8")

                        # CONTEXT.md
                        context_content = f"""# {new_agent_name.title()} — Contexto e Instruções

## Papel
{new_agent_role or f'Agente {new_agent_name.title()} da Vitalmed.'}

## Modelo
`{new_agent_model}`

## Instruções
- Você é um agente da Vitalmed, especializado em {new_agent_name}.
- Responda sempre em português brasileiro.
- Seja claro, objetivo e empático.

## Regras de Negócio
- (adicione as regras aqui)

## Exemplos de Conversa
**Lead:** Olá
**Agente:** Olá! Como posso ajudá-lo hoje?
"""
                        (new_dir / "CONTEXT.md").write_text(context_content, encoding="utf-8")

                        # agent.py básico
                        agent_py_content = f'''from __future__ import annotations
"""
{new_agent_name.title()} — agente criado via Streamlit Builder.
"""
import logging
from pathlib import Path
from agno.agent import Agent
from agno.models.google import Gemini

logger = logging.getLogger(__name__)

_CONTEXT_PATH = Path(__file__).parent / "CONTEXT.md"


def create_{new_agent_name.lower()}_agent() -> Agent:
    """Cria e retorna o {new_agent_name.title()}."""
    context = _CONTEXT_PATH.read_text(encoding="utf-8") if _CONTEXT_PATH.exists() else ""

    return Agent(
        name="{new_agent_name.title()}",
        model=Gemini(id="{new_agent_model}"),
        instructions=context,
        add_history_to_context=True,
        markdown=True,
    )
'''
                        (new_dir / "agent.py").write_text(agent_py_content, encoding="utf-8")

                        st.success(f"✅ Agente `{new_agent_name}` criado em `src/agents/{new_agent_name}/`!")
                        st.code(f"src/agents/{new_agent_name}/\n  ├── __init__.py\n  ├── CONTEXT.md\n  └── agent.py")
                        st.info("Para ativar o agente, edite o `RouterAgent` para incluí-lo no time.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erro ao criar agente: {e}")

    with col_ag_edit:
        st.subheader(f"Editando: {selected_agent_label}")

        if editable_files and selected_file_label_ag in editable_files:
            edit_path = editable_files[selected_file_label_ag]
            current_ag_content = edit_path.read_text(encoding="utf-8")

            new_ag_content = st.text_area(
                f"Conteúdo de `{edit_path.name}`:",
                value=current_ag_content,
                height=480,
                key=f"ag_editor_{agent_key}_{edit_path.name}"
            )

            col_save_ag, col_diff_ag = st.columns([1, 1])
            with col_save_ag:
                if st.button("💾 Salvar", type="primary", key="save_agent_ctx"):
                    try:
                        edit_path.write_text(new_ag_content, encoding="utf-8")
                        st.success(f"✅ `{edit_path.name}` salvo!")
                        st.info("♻️ Reinicie a API para aplicar as mudanças: `docker restart vitalmed_api`")
                    except Exception as e:
                        st.error(f"❌ Erro: {e}")

            with col_diff_ag:
                if new_ag_content != current_ag_content:
                    st.warning("⚠️ Há mudanças não salvas")
                else:
                    st.success("✅ Sem alterações pendentes")

            # Estatísticas rápidas
            st.markdown("---")
            lines = new_ag_content.splitlines()
            words = len(new_ag_content.split())
            col_s1, col_s2, col_s3 = st.columns(3)
            col_s1.metric("Linhas", len(lines))
            col_s2.metric("Palavras", words)
            col_s3.metric("Caracteres", len(new_ag_content))
        else:
            st.info("Selecione um agente e arquivo para editar.")


# ═══════════════════════════════════════════════════════════════════════════════
# ABA 6: INTEGRAÇÃO MCP
# ═══════════════════════════════════════════════════════════════════════════════
with tab_mcp:
    st.header("🔌 Integração com Servidores MCP")
    st.markdown("Configure e teste servidores MCP (Model Context Protocol) para expandir as capacidades dos agentes com ferramentas externas.")

    col_mcp_cfg, col_mcp_test = st.columns([1, 1])

    with col_mcp_cfg:
        st.subheader("⚙️ Configuração do Servidor MCP")

        # Tipo de servidor
        mcp_type = st.selectbox(
            "Tipo de servidor MCP",
            ["HTTP/SSE (FastAPI/Express)", "Stdio (CLI/script local)", "WebSocket"],
            key="mcp_type"
        )

        mcp_name = st.text_input("Nome da integração", placeholder="Ex: vitalmed-crm", key="mcp_name")
        mcp_url = st.text_input(
            "URL do servidor MCP" if "HTTP" in mcp_type else "Comando (stdio)",
            placeholder="http://localhost:8001/mcp" if "HTTP" in mcp_type else "python -m meu_servidor_mcp",
            key="mcp_url"
        )

        st.markdown("**Headers de autenticação** (opcional)")
        col_h1, col_h2 = st.columns(2)
        with col_h1:
            mcp_header_key = st.text_input("Header", placeholder="Authorization", key="mcp_hk")
        with col_h2:
            mcp_header_val = st.text_input("Valor", placeholder="Bearer token...", type="password", key="mcp_hv")

        # Seleção de agente para vincular
        mcp_target_agent = st.multiselect(
            "Vincular ao(s) agente(s)",
            ["SalesAgent", "DoubtsAgent", "AssistantAgent", "RouterAgent"],
            default=["DoubtsAgent"],
            key="mcp_agents"
        )

        if st.button("🔍 Testar Conexão", key="mcp_test_conn"):
            if not mcp_url:
                st.error("URL ou comando é obrigatório.")
            else:
                with st.spinner("Testando conexão..."):
                    try:
                        headers = {}
                        if mcp_header_key and mcp_header_val:
                            headers[mcp_header_key] = mcp_header_val

                        if "HTTP" in mcp_type:
                            # Testa endpoint de listagem de tools
                            test_url = mcp_url.rstrip("/")
                            # Tenta diferentes endpoints padrão MCP
                            for endpoint in ["/tools/list", "/tools", "/list-tools", ""]:
                                try:
                                    r = requests.get(f"{test_url}{endpoint}", headers=headers, timeout=5)
                                    if r.status_code in (200, 405):  # 405 = method not allowed mas existe
                                        st.success(f"✅ Servidor MCP acessível em `{test_url}{endpoint}` (HTTP {r.status_code})")
                                        if r.status_code == 200:
                                            try:
                                                st.json(r.json())
                                            except Exception:
                                                st.code(r.text[:500])
                                        break
                                except Exception:
                                    continue
                            else:
                                st.warning("⚠️ Servidor respondeu mas nenhum endpoint padrão retornou 200")
                        else:
                            st.info("Servidor stdio — não é possível testar via UI. Configure e reinicie a API.")
                    except Exception as e:
                        st.error(f"❌ Falha na conexão: {e}")

        if st.button("💾 Salvar Configuração MCP", type="primary", key="mcp_save"):
            if not mcp_name or not mcp_url:
                st.error("Nome e URL são obrigatórios.")
            else:
                # Salvar configuração em arquivo JSON
                mcp_config_path = Path(__file__).parent.parent / "src" / "core" / "mcp_config.json"
                try:
                    if mcp_config_path.exists():
                        mcp_configs = json.loads(mcp_config_path.read_text())
                    else:
                        mcp_configs = {"servers": []}

                    # Remove entrada com mesmo nome se existir
                    mcp_configs["servers"] = [s for s in mcp_configs["servers"] if s.get("name") != mcp_name]

                    new_server = {
                        "name": mcp_name,
                        "type": mcp_type,
                        "url": mcp_url,
                        "agents": mcp_target_agent,
                        "headers": {mcp_header_key: "***"} if mcp_header_key else {},
                        "created_at": datetime.utcnow().isoformat(),
                    }
                    mcp_configs["servers"].append(new_server)
                    mcp_config_path.write_text(json.dumps(mcp_configs, indent=2, ensure_ascii=False))

                    st.success(f"✅ Integração `{mcp_name}` salva!")
                    st.code(json.dumps(new_server, indent=2, ensure_ascii=False), language="json")
                    st.info("Para usar o MCP nos agentes, importe o cliente MCP no `agent.py` e adicione como tool.")
                except Exception as e:
                    st.error(f"❌ Erro ao salvar: {e}")

    with col_mcp_test:
        st.subheader("🧪 Testar Tool MCP Manualmente")

        # Carregar servidores salvos
        mcp_config_path = Path(__file__).parent.parent / "src" / "core" / "mcp_config.json"
        if mcp_config_path.exists():
            saved_configs = json.loads(mcp_config_path.read_text()).get("servers", [])
        else:
            saved_configs = []

        if saved_configs:
            st.markdown("**Servidores Configurados:**")
            for srv in saved_configs:
                st.markdown(f"""<div class="agent-card">
                    <strong>🔌 {srv['name']}</strong><br>
                    <small>Tipo: {srv['type']} | Agentes: {', '.join(srv.get('agents', []))}</small><br>
                    <code>{srv['url']}</code>
                </div>""", unsafe_allow_html=True)

            st.markdown("---")
            selected_server = st.selectbox(
                "Servidor para testar",
                [s["name"] for s in saved_configs],
                key="mcp_server_select"
            )

        else:
            st.info("Nenhum servidor MCP configurado ainda.\n\nConfigure um servidor à esquerda.")
            selected_server = None

        st.markdown("---")
        st.subheader("📖 Guia Rápido MCP")

        with st.expander("Como integrar um MCP ao agente", expanded=True):
            st.markdown("""
**1. Servidor MCP HTTP (FastAPI):**
```python
# No agent.py, após criar o agente:
from agno.tools.mcp import MCPTools

mcp_tools = MCPTools(url="http://meu-servidor:8001/mcp")
agent = Agent(..., tools=[mcp_tools])
```

**2. Servidor MCP Stdio:**
```python
from agno.tools.mcp import MCPTools
import subprocess

mcp_tools = MCPTools(
    command=["python", "-m", "meu_servidor_mcp"]
)
agent = Agent(..., tools=[mcp_tools])
```

**3. Estrutura de um Servidor MCP simples:**
```python
# servidor_mcp.py
from fastapi import FastAPI
app = FastAPI()

@app.get("/tools/list")
def list_tools():
    return {"tools": [
        {"name": "buscar_cliente", "description": "Busca dados do cliente"}
    ]}

@app.post("/tools/call")
def call_tool(tool_name: str, args: dict):
    if tool_name == "buscar_cliente":
        return {"result": "dados do cliente..."}
```

**4. Iniciar servidor:**
```bash
uvicorn servidor_mcp:app --port 8001
```
            """)

        with st.expander("MCPs disponíveis na Vitalmed"):
            st.markdown("""
| MCP | Função | Endpoint |
|---|---|---|
| **Chatwoot MCP** | Gestão de conversas | `/mcp/chatwoot` |
| **CRM MCP** | Leads e follow-up | `/mcp/crm` |
| **Calendar MCP** | Agendamentos | `/mcp/calendar` |
| **Docs MCP** | Busca em documentos | `/mcp/docs` |

> Configure um servidor MCP para cada integração desejada e vincule ao agente correspondente.
            """)
