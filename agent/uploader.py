"""Uploads a finished video to YouTube as PRIVATE, so a human reviews it before it goes public.

Setup (once): create a Google Cloud project, enable "YouTube Data API v3", create an OAuth client
of type "Desktop app", download it as client_secret.json. The first run opens a browser to log in
and saves token.json. Videos from unaudited API projects stay private anyway:
https://developers.google.com/youtube/v3/docs/videos/insert
"""

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
EDUCATION_CATEGORY = "27"


def _youtube():
    token = Path("token.json")
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            secret = os.getenv("YOUTUBE_CLIENT_SECRET", "client_secret.json")
            creds = InstalledAppFlow.from_client_secrets_file(secret, SCOPES).run_local_server(port=0)
        token.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload(video: Path, title: str, description: str, tags: list[str],
           synthetic: bool = False, thumbnail: Path | None = None) -> str:
    yt = _youtube()
    body = {
        "snippet": {"title": title[:100], "description": description[:5000],
                    "tags": tags[:30], "categoryId": EDUCATION_CATEGORY},
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": synthetic},
    }
    request = yt.videos().insert(part="snippet,status", body=body,
                                 media_body=MediaFileUpload(str(video), resumable=True, chunksize=-1))
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  uploading... {int(status.progress() * 100)}%")
    video_id = response["id"]
    if thumbnail and thumbnail.exists():
        try:
            yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(thumbnail))).execute()
        except Exception as e:  # custom thumbnails need a phone-verified channel
            print(f"  ! thumbnail not set ({e}); upload it in YouTube Studio")
    return video_id
