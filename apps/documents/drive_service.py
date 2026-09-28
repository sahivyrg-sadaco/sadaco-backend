"""
Google Drive service using a service account (NOT user OAuth).

All files are stored under the company's Drive account.
The app controls access entirely — Google Drive sharing is NOT used for
access control.

Required env vars:
  GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON  — full service account JSON as a string
  GOOGLE_DRIVE_ROOT_FOLDER_ID        — ID of the /ERP root folder in Drive
"""
import io
import json
import logging
from functools import lru_cache

from django.conf import settings

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive']


@lru_cache(maxsize=1)
def _get_service():
    """Build and cache the Drive API client. Called once per process."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    sa_json = settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON
    sa_file = settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE

    if sa_json:
        info  = json.loads(sa_json)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES,
        )
    elif sa_file:
        creds = service_account.Credentials.from_service_account_file(
            sa_file, scopes=SCOPES,
        )
    else:
        raise RuntimeError(
            'Google Drive service account not configured. Set '
            'GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON or GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE.'
        )

    return build('drive', 'v3', credentials=creds, cache_discovery=False)


def get_or_create_folder(name: str, parent_id: str) -> str:
    """
    Return the Drive folder ID for `name` under `parent_id`.
    Creates the folder if it doesn't exist.
    """
    service = _get_service()
    query = (
        f"name='{name}' "
        f"and mimeType='application/vnd.google-apps.folder' "
        f"and '{parent_id}' in parents "
        f"and trashed=false"
    )
    results = service.files().list(q=query, fields='files(id,name)').execute()
    files   = results.get('files', [])
    if files:
        return files[0]['id']

    meta = {
        'name':     name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents':  [parent_id],
    }
    folder = service.files().create(body=meta, fields='id').execute()
    logger.info(f"Created Drive folder: {name} -> {folder['id']}")
    return folder['id']


def get_client_folder(client_id: int, subfolder: str) -> str:
    """
    Return (creating if needed) the ID for:
        /ERP/Clients/{client_id}/{subfolder}
    """
    from apps.clients.models import Client

    root   = settings.GOOGLE_DRIVE_ROOT_FOLDER_ID
    client = Client.objects.get(pk=client_id)

    if not client.drive_folder_id:
        clients_folder = get_or_create_folder('Clients', root)
        client_folder  = get_or_create_folder(str(client_id), clients_folder)
        client.drive_folder_id = client_folder
        client.save(update_fields=['drive_folder_id'])

    return get_or_create_folder(subfolder, client.drive_folder_id)


def get_deal_folder(deal_id: int) -> str:
    """
    Return (creating if needed) the folder ID for:
        /ERP/Deals/{deal_id}
    """
    from apps.deals.models import Deal

    root = settings.GOOGLE_DRIVE_ROOT_FOLDER_ID
    deal = Deal.objects.get(pk=deal_id)

    if not deal.drive_folder_id:
        deals_folder = get_or_create_folder('Deals', root)
        deal_folder  = get_or_create_folder(str(deal_id), deals_folder)
        deal.drive_folder_id = deal_folder
        deal.save(update_fields=['drive_folder_id'])
    return deal.drive_folder_id


def upload_file(file_bytes: bytes, file_name: str, mime_type: str,
                folder_id: str) -> dict:
    """
    Upload a file to Drive. Returns:
        {drive_file_id, web_view_link, file_name, file_size_bytes}
    """
    from googleapiclient.http import MediaIoBaseUpload

    service = _get_service()
    meta    = {'name': file_name, 'parents': [folder_id]}
    media   = MediaIoBaseUpload(
        io.BytesIO(file_bytes), mimetype=mime_type, resumable=True,
    )
    result = service.files().create(
        body=meta, media_body=media,
        fields='id,name,webViewLink,size',
    ).execute()

    # Anyone with link can view (no Drive auth required)
    service.permissions().create(
        fileId=result['id'],
        body={'type': 'anyone', 'role': 'reader'},
    ).execute()

    return {
        'drive_file_id':   result['id'],
        'web_view_link':   result.get('webViewLink', ''),
        'file_name':       result.get('name', file_name),
        'file_size_bytes': int(result.get('size', 0) or 0),
    }


def delete_file(drive_file_id: str) -> bool:
    """Delete a file from Drive. Returns True on success."""
    try:
        _get_service().files().delete(fileId=drive_file_id).execute()
        return True
    except Exception as e:
        logger.error(f'Drive delete failed {drive_file_id}: {e}')
        return False


def replace_file(drive_file_id: str, file_bytes: bytes, mime_type: str) -> dict:
    """Replace the contents of an existing Drive file."""
    from googleapiclient.http import MediaIoBaseUpload

    service = _get_service()
    media   = MediaIoBaseUpload(
        io.BytesIO(file_bytes), mimetype=mime_type, resumable=True,
    )
    result = service.files().update(
        fileId=drive_file_id, media_body=media,
        fields='id,name,webViewLink',
    ).execute()
    return {
        'drive_file_id': result['id'],
        'web_view_link': result.get('webViewLink', ''),
    }


def get_file_metadata(drive_file_id: str) -> dict:
    """Fetch metadata for one file."""
    return _get_service().files().get(
        fileId=drive_file_id,
        fields='id,name,webViewLink,size,mimeType,createdTime',
    ).execute()


def download_file_bytes(drive_file_id: str) -> bytes:
    """Download a file's raw bytes."""
    from googleapiclient.http import MediaIoBaseDownload

    service    = _get_service()
    request    = service.files().get_media(fileId=drive_file_id)
    buf        = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()
