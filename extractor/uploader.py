"""
Upload parsed WhatsApp conversations to the server.
"""

import json
import requests

from config import BACKUP_UPLOAD_URL


class UploadError(Exception):
    pass


def upload_conversations(conversations: list[dict], server_url: str = None) -> dict:
    """
    Upload parsed conversations as JSON to the server.

    Args:
        conversations: List of conversation dicts from msgstore_parser
        server_url: Override server URL (uses config default if None)

    Returns:
        Server response dict

    Raises:
        UploadError: If upload fails
    """
    url = server_url or BACKUP_UPLOAD_URL

    try:
        response = requests.post(
            url,
            json=conversations,
            headers={"Content-Type": "application/json"},
            timeout=120,
        )
        response.raise_for_status()
        return response.json()
    except requests.ConnectionError:
        raise UploadError(
            "Nao foi possivel conectar ao servidor.\n"
            "Verifique sua conexao com a internet."
        )
    except requests.Timeout:
        raise UploadError(
            "Tempo de conexao esgotado.\n"
            "Os dados sao muito grandes ou o servidor esta lento."
        )
    except requests.HTTPError as e:
        raise UploadError(f"Servidor retornou erro: {e.response.status_code}")
    except Exception as e:
        raise UploadError(f"Erro no envio: {e}")
