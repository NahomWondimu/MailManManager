# run fastapi with
# uvicorn main:app --reload

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

import os
import pathlib
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import google.auth.transport.requests

app = FastAPI()

# Optional: Allow frontend to connect during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Config ----
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # for dev over HTTP
BASE_DIR = pathlib.Path(__file__).resolve().parent
CLIENT_SECRET_FILE = BASE_DIR / "client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
REDIRECT_URI = "http://localhost:8000/auth/callback"
SESSION_TOKEN = {}  # Temporary in-memory store

# ---- Step 1: Start OAuth Flow ----
@app.get("/auth/login")
def login():
    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRET_FILE),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    auth_url, _ = flow.authorization_url(prompt="consent")
    return RedirectResponse(auth_url)

# ---- Step 2: Handle OAuth Callback ----
@app.get("/auth/callback")
def callback(request: Request):
    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRET_FILE),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    flow.fetch_token(authorization_response=str(request.url))

    credentials = flow.credentials
    SESSION_TOKEN["credentials"] = credentials_to_dict(credentials)
    emailList = get_emails()
    # return {"message": "Login successful! You can now fetch emails."}
    return {"message": emailList}

# ---- Step 3: Fetch Emails ----
@app.get("/emails")
def get_emails():
    if "credentials" not in SESSION_TOKEN:
        return {"error": "Not logged in."}

    creds = SESSION_TOKEN["credentials"]
    service = build("gmail", "v1", credentials=google.oauth2.credentials.Credentials(**creds))

    results = service.users().messages().list(userId='me', maxResults=10).execute()
    messages = results.get("messages", [])

    emails = []
    for msg in messages:
        msg_data = service.users().messages().get(userId='me', id=msg['id'], format='metadata').execute()
        headers = msg_data.get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(No Subject)")
        emails.append(subject)

    return {"emails": emails}

def credentials_to_dict(creds):
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes
    }
