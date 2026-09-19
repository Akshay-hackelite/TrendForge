import json
from pathlib import Path
from google.cloud import storage
from google.oauth2 import service_account

from app.config import settings

def _get_gcs_client() -> storage.Client:
    """Initialize GCS client using either JSON string from env var or the local credentials file."""
    if settings.GCS_KEY_JSON:
        # Render/production: use the inline JSON string
        credentials_dict = json.loads(settings.GCS_KEY_JSON)
        credentials = service_account.Credentials.from_service_account_info(credentials_dict)
        return storage.Client(credentials=credentials, project=credentials.project_id)
    
    # Local: relies on GOOGLE_APPLICATION_CREDENTIALS env var
    return storage.Client()


def upload_bytes(folder: str, filename: str, data: bytes, content_type: str = "image/png") -> str:
    """Upload raw bytes to GCS and return the public URL."""
    if not settings.GCS_BUCKET_NAME:
        raise ValueError("GCS_BUCKET_NAME is not set in config.")
        
    client = _get_gcs_client()
    bucket = client.bucket(settings.GCS_BUCKET_NAME)
    
    # Ensure folder name ends with a slash if provided
    prefix = f"{folder.strip('/')}/" if folder else ""
    blob_path = f"{prefix}{filename}"
    
    blob = bucket.blob(blob_path)
    blob.upload_from_string(data, content_type=content_type)
    
    return f"https://storage.googleapis.com/{settings.GCS_BUCKET_NAME}/{blob_path}"


def upload_file(folder: str, local_path: Path | str, content_type: str = "application/pdf") -> str:
    """Upload a local file to GCS and return the public URL."""
    if not settings.GCS_BUCKET_NAME:
        raise ValueError("GCS_BUCKET_NAME is not set in config.")
        
    path = Path(local_path)
    client = _get_gcs_client()
    bucket = client.bucket(settings.GCS_BUCKET_NAME)
    
    prefix = f"{folder.strip('/')}/" if folder else ""
    blob_path = f"{prefix}{path.name}"
    
    blob = bucket.blob(blob_path)
    blob.upload_from_filename(str(path), content_type=content_type)
    
    return f"https://storage.googleapis.com/{settings.GCS_BUCKET_NAME}/{blob_path}"


def delete_file(blob_path: str) -> None:
    """Delete a file from GCS."""
    if not settings.GCS_BUCKET_NAME:
        return
        
    try:
        client = _get_gcs_client()
        bucket = client.bucket(settings.GCS_BUCKET_NAME)
        blob = bucket.blob(blob_path)
        blob.delete()
    except Exception as e:
        print(f"Failed to delete GCS file {blob_path}: {e}", flush=True)
