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
import google.oauth2.credentials

from requestFromAI import getFolderRecommendation

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
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"  # allow scope mismatch without invalidating token

BASE_DIR = pathlib.Path(__file__).resolve().parent
CLIENT_SECRET_FILE = BASE_DIR / "client_secret.json"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels"
]
REDIRECT_URI = "http://localhost:8000/auth/callback"
SESSION_TOKEN = {}  # Temporary in-memory store

# ---- Fetch Emails ----
@app.get("/emails")
def get_emails():
    if "credentials" not in SESSION_TOKEN:
        return {"error": "Not logged in."}

    creds = SESSION_TOKEN["credentials"]
    service = build("gmail", "v1", credentials=google.oauth2.credentials.Credentials(**creds))

    query = "is:unread"
    email_contents = []
    message_ids = []
    page_token = None
    max_total = 200

    while True:
        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=100,
            pageToken=page_token
        ).execute()

        messages = results.get("messages", [])
        if not messages:
            break

        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
            snippet = msg_data.get("snippet", "")
            email_contents.append(snippet)
            message_ids.append(msg['id'])

            if max_total and len(email_contents) >= max_total:
                return {"emails": email_contents[:max_total], "message_ids": message_ids[:max_total]}

        page_token = results.get("nextPageToken")
        if not page_token:
            break

    return {"emails": email_contents, "message_ids": message_ids}

# ---- Label Management ----
def create_labels_if_missing(service, required_labels):
    existing_labels = service.users().labels().list(userId='me').execute().get("labels", [])
    existing_names = {label["name"]: label["id"] for label in existing_labels}
    label_ids = {}

    for name in required_labels:
        if name in existing_names:
            label_ids[name] = existing_names[name]
        else:
            label_obj = {
                "name": name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show"
            }
            new_label = service.users().labels().create(userId='me', body=label_obj).execute()
            label_ids[name] = new_label["id"]

    return label_ids

# ---- Categorize and Label Emails ----
def emailToFolderRec():
    if "credentials" not in SESSION_TOKEN:
        return {"error": "Not logged in."}

    creds = SESSION_TOKEN["credentials"]
    service = build("gmail", "v1", credentials=google.oauth2.credentials.Credentials(**creds))

    data = get_emails()
    emails = data.get("emails", [])
    message_ids = data.get("message_ids", [])

    folderRecDict = getFolderRecommendation(emails)  # expects 1-based indices
    label_ids = create_labels_if_missing(service, ["Time Sensitive", "For Review", "Junk"])

    changed_messages = 0

    # Apply labels to messages
    for folder, indices in folderRecDict.items():
        for i in map(lambda x: int(x.replace("Email ", "").strip()), indices):
            if 1 <= i <= len(message_ids):
                msg_id = message_ids[i - 1]  # adjust for 0-based indexing
                service.users().messages().modify(
                    userId='me',
                    id=msg_id,
                    body={
                        "addLabelIds": [label_ids[folder]],
                        "removeLabelIds": ["INBOX"]
                    }
                ).execute()

                changed_messages += 1

    return {
        "categorized": folderRecDict,
        "message": f"Successfully labeled {changed_messages} message(s) in your Gmail account."
    }

# ---- Start OAuth Flow ----
@app.get("/auth/login")
def login():
    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRET_FILE),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    auth_url, _ = flow.authorization_url(
        prompt="consent",  # force full re-consent
        include_granted_scopes=False  # disable scope merging (prevents silent token reuse)
    )
    return RedirectResponse(auth_url)

# ---- Handle OAuth Callback ----
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
    result = emailToFolderRec()
    return {"message": result["message"], "details": result["categorized"]}

# ---- Token Serialization ----
def credentials_to_dict(creds):
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes
    }