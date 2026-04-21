"""
Cliente Google Cloud Storage para upload de contratos Vitalmed.
Bucket: gs://contratovitalmed
Estrutura: {cpf}/{nome_arquivo}
"""
import logging
import os
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


def upload_contract_to_gcs(cpf: str, filename: str, content: bytes, content_type: str = "application/pdf") -> str:
    """
    Faz upload do contrato para gs://contratovitalmed/{cpf}/{filename}.
    Retorna o caminho público no bucket: gs://contratovitalmed/{cpf}/{filename}
    """
    client = _get_client()
    bucket = client.bucket(_GCS_BUCKET)
    blob_name = f"{cpf}/{filename}"
    blob = bucket.blob(blob_name)
    blob.upload_from_string(content, content_type=content_type)
    gcs_path = f"gs://{_GCS_BUCKET}/{blob_name}"
    logger.info(f"✅ Contrato enviado ao GCS: {gcs_path}")
    return gcs_path


def download_from_gcs(blob_name: str) -> bytes:
    """Faz download de um blob do bucket (para testes)."""
    client = _get_client()
    bucket = client.bucket(_GCS_BUCKET)
    return bucket.blob(blob_name).download_as_bytes()
