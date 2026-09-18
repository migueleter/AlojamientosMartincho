"""Login OAuth de solo lectura contra Gmail, compartido por los scripts de este directorio."""

import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PRIVATE_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~/.local")),
    "AlojamientosMartincho",
)
CREDENTIALS_PATH = os.environ.get(
    "ALOJAMIENTOS_GMAIL_CREDENTIALS",
    os.path.join(PRIVATE_DIR, "credentials.json"),
)
TOKEN_PATH = os.environ.get(
    "ALOJAMIENTOS_GMAIL_TOKEN",
    os.path.join(PRIVATE_DIR, "token.json"),
)


def get_gmail_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise SystemExit(
                    f"Falta {CREDENTIALS_PATH}.\n"
                    "Descarga las credenciales OAuth (tipo Desktop app) desde Google Cloud "
                    "Console y guárdalas en la ruta privada indicada por "
                    "ALOJAMIENTOS_GMAIL_CREDENTIALS."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)
