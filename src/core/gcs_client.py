"""
Cliente Google Cloud Storage para upload de contratos Vitalmed.
Bucket: gs://contratovitalmed
Estrutura: {cpf}/{nome_arquivo}
"""
import logging
from pathlib import Path

from google.cloud import storage
from google.oauth2 import service_account

logger = logging.getLogger(__name__)

_GCS_BUCKET = "contratovitalmed"
_CREDENTIALS_PATH = Path(__file__).parent.parent.parent / "credentials" / "gcs_service_account.json"


def _get_client() -> storage.Client:
    creds = service_account.Credentials.from_service_account_file(
        str(_CREDENTIALS_PATH),
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    return storage.Client(credentials=creds, project="universal-team-401112")


def upload_contract_to_gcs(
    cpf: str,
    filename: str,
    content: bytes,
    content_type: str = "application/pdf",
) -> tuple[str, str]:
    """
    Faz upload do contrato para gs://contratovitalmed/{cpf}/{filename}.

    Retorna uma tupla (gcs_path, download_url) onde:
      - gcs_path:     gs://contratovitalmed/{cpf}/{filename}  (sempre disponível)
      - download_url: Signed URL HTTPS se possível, caso contrário igual ao gcs_path

    O n8n usa suas próprias credenciais GCS para baixar via gcs_path e enviar ao WhatsApp.
    """
    from datetime import timedelta

    creds = service_account.Credentials.from_service_account_file(
        str(_CREDENTIALS_PATH),
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    client = storage.Client(credentials=creds, project="universal-team-401112")
    bucket = client.bucket(_GCS_BUCKET)
    blob_name = f"{cpf}/{filename}"
    blob = bucket.blob(blob_name)
    blob.upload_from_string(content, content_type=content_type)
    gcs_path = f"gs://{_GCS_BUCKET}/{blob_name}"

    logger.info(f"✅ Contrato enviado ao GCS: {gcs_path}")

    # Tentar gerar Signed URL para download direto via HTTPS
    # Pode falhar se a service account não tiver permissão de signing
    download_url = gcs_path  # fallback: mesma URL gs://
    try:
        signed = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(days=7),
            method="GET",
            credentials=creds,
            response_disposition=f'attachment; filename="{filename}"',
        )
        download_url = signed
        logger.info(f"🔗 Signed URL gerada (7d): {signed[:80]}...")
    except Exception as e:
        logger.warning(
            f"⚠️  Signed URL indisponível ({type(e).__name__}): {e}. "
            f"Usando gcs_path no payload — n8n baixa via credenciais próprias."
        )

    return gcs_path, download_url


def download_from_gcs(blob_name: str) -> bytes:
    """Faz download de um blob do bucket (para testes)."""
    client = _get_client()
    bucket = client.bucket(_GCS_BUCKET)
    return bucket.blob(blob_name).download_as_bytes()
