from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Google AI
    google_api_key: str = Field(..., env="GOOGLE_API_KEY")
    gemini_flash_model: str = Field("gemini-1.5-flash", env="GEMINI_FLASH_MODEL")
    gemini_pro_model: str = Field("gemini-1.5-pro", env="GEMINI_PRO_MODEL")
    embedding_model: str = Field("text-embedding-004", env="EMBEDDING_MODEL")

    # Database
    database_url: str = Field(..., env="DATABASE_URL")
    database_url_sync: str = Field(..., env="DATABASE_URL_SYNC")

    # Redis
    redis_url: str = Field("redis://redis:6379/0", env="REDIS_URL")
    job_ttl_seconds: int = Field(300, env="JOB_TTL_SECONDS")

    # Langfuse
    langfuse_secret_key: str = Field("", env="LANGFUSE_SECRET_KEY")
    langfuse_public_key: str = Field("", env="LANGFUSE_PUBLIC_KEY")
    langfuse_host: str = Field("https://us.cloud.langfuse.com", env="LANGFUSE_BASE_URL")

    # Chatwoot
    chatwoot_api_url: str = Field("", env="CHATWOOT_API_URL")
    chatwoot_api_token: str = Field("", env="CHATWOOT_API_TOKEN")
    chatwoot_account_id: int = Field(1, env="CHATWOOT_ACCOUNT_ID")
    chatwoot_label_interested: str = Field("interessado", env="CHATWOOT_LABEL_INTERESTED")
    chatwoot_label_closed: str = Field("fechado", env="CHATWOOT_LABEL_CLOSED")
    chatwoot_label_escalated: str = Field("escalado_para_humano", env="CHATWOOT_LABEL_ESCALATED")
    chatwoot_local_mode: bool = Field(True, env="CHATWOOT_LOCAL_MODE")

    # N8N / Webhook de resposta
    n8n_webhook_url: str = Field("", env="N8N_WEBHOOK_URL")

    # Whisper
    whisper_mode: str = Field("local", env="WHISPER_MODE")
    whisper_model_size: str = Field("base", env="WHISPER_MODEL_SIZE")
    openai_api_key: str = Field("", env="OPENAI_API_KEY")

    # RAG
    rag_chunk_size: int = Field(512, env="RAG_CHUNK_SIZE")
    rag_chunk_overlap: float = Field(0.20, env="RAG_CHUNK_OVERLAP")
    rag_top_k: int = Field(5, env="RAG_TOP_K")
    rag_min_score: float = Field(0.70, env="RAG_MIN_SCORE")
    uploads_dir: str = Field("./uploads", env="UPLOADS_DIR")

    # App
    app_env: str = Field("development", env="APP_ENV")
    app_port: int = Field(8000, env="APP_PORT")
    log_level: str = Field("INFO", env="LOG_LEVEL")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
