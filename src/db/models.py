"""
Models SQLAlchemy para o projeto Vitalmed.
Tabelas: leads, lead_status_history, conversations, knowledge_chunks, contracts, contract_dependents
"""
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text,
    DateTime, ForeignKey, JSON, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    pass


class Lead(Base):
    """
    Tabela principal de leads com ciclo de vida completo.
    Status: novo → contactado → em_atendimento → interessado → fechado
                                               → escalado
                               → sem_retorno
                               → nao_interessado / perdido
    """
    __tablename__ = "leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100))
    email = Column(String(150))
    age = Column(Integer)
    status = Column(String(30), nullable=False, default="novo", index=True)
    source = Column(String(50))                  # ex: "campanha_abril_2026"
    interested_plan = Column(String(100))        # plano de interesse detectado
    chatwoot_contact_id = Column(String(50))     # ID do contato no Chatwoot
    voice = Column(Boolean, default=False, nullable=False, server_default="false")  # canal voz

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_contact_at = Column(DateTime)

    # Relacionamentos
    status_history = relationship("LeadStatusHistory", back_populates="lead", lazy="select")
    conversations = relationship("Conversation", back_populates="lead", lazy="select")
    contracts = relationship("Contract", back_populates="lead", lazy="select")

    def __repr__(self):
        return f"<Lead {self.phone} | {self.status}>"


class LeadStatusHistory(Base):
    """
    Histórico de transições de status do lead.
    Permite auditoria completa e re-comunicação futura.
    """
    __tablename__ = "lead_status_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, index=True)
    old_status = Column(String(30))
    new_status = Column(String(30), nullable=False)
    reason = Column(Text)
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    lead = relationship("Lead", back_populates="status_history")


class Conversation(Base):
    """
    Registro de todas as mensagens trocadas (auditoria + Langfuse backup).
    """
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    agent_type = Column(String(30))    # router | assistant | doubts
    role = Column(String(10))          # user | agent
    message = Column(Text, nullable=False)
    tools_called = Column(JSON)        # lista de tools invocadas nessa mensagem
    langfuse_trace_id = Column(String(100))
    cost_usd = Column(Float)           # custo da chamada LLM em USD
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    lead = relationship("Lead", back_populates="conversations")


class KnowledgeChunk(Base):
    """
    Chunks indexados da base de conhecimento Vitalmed (RAG).
    Embedding de 768 dimensões (gemini-embedding-001 com output_dimensionality=768).
    Compatível com índice ivfflat do pgvector.
    """
    __tablename__ = "knowledge_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(768))    # pgvector — 768 dims com ivfflat

    source_file = Column(String(255), nullable=False, index=True)
    doc_type = Column(String(20))       # pdf | docx | video
    section_title = Column(String(255))
    page_number = Column(Integer)
    video_timestamp = Column(String(20))

    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index(
            "ix_knowledge_chunks_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self):
        return f"<KnowledgeChunk {self.source_file} p{self.page_number}>"


class Contract(Base):
    """
    Contrato gerado para o lead.
    tipo: individual | familiar
    status: a_enviar → enviado → assinado
    """
    __tablename__ = "contracts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, index=True)

    contract_type = Column(String(20), nullable=False)        # individual | familiar
    status = Column(String(20), nullable=False, default="a_enviar", index=True)
    # Caminho no GCS: gs://contratovitalmed/{cpf}/{filename}
    gcs_path = Column(String(500))
    filename = Column(String(255))

    # Dados do titular (JSON completo)
    titular_data = Column(JSON, nullable=False)
    # Dados do contrato (número, datas, forma pagamento)
    contract_data = Column(JSON, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    signed_at = Column(DateTime)                              # quando assinou
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lead = relationship("Lead", back_populates="contracts")
    dependents = relationship("ContractDependent", back_populates="contract", lazy="select", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Contract {self.id} | {self.contract_type} | {self.status}>"


class ContractDependent(Base):
    """
    Dependentes vinculados a um contrato familiar.
    """
    __tablename__ = "contract_dependents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id = Column(UUID(as_uuid=True), ForeignKey("contracts.id"), nullable=False, index=True)

    nome_completo = Column(String(150), nullable=False)
    cpf = Column(String(14))
    rg = Column(String(20))
    data_nascimento = Column(String(20))
    idade = Column(Integer)
    parentesco = Column(String(50))      # filho, cônjuge, etc.
    faixa_etaria = Column(String(30))
    valor_plano = Column(String(30))

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    contract = relationship("Contract", back_populates="dependents")

    def __repr__(self):
        return f"<ContractDependent {self.nome_completo} | {self.parentesco}>"
