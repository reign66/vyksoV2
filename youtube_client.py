import os
import json
import pickle
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Scopes required for YouTube upload
SCOPES = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly']

class YouTubeClient:
    def __init__(self):
        # We expect client_secrets to be loaded from env or file
        # For Railway/Production, we usually put the JSON content in an ENV var
        self.client_secrets_file = "/tmp/client_secrets.json"
        self.redirect_uri = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/youtube-callback"
        
        # Write secrets to temp file if in env
        if os.getenv("GOOGLE_CLIENT_SECRETS_JSON"):
            with open(self.client_secrets_file, "w") as f:
                f.write(os.getenv("GOOGLE_CLIENT_SECRETS_JSON"))
        
    def get_auth_url(self, user_id: str):
        """
        Generates the OAuth 2.0 authorization URL.
        """
        if not os.path.exists(self.client_secrets_file):
            raise ValueError("Google Client Secrets not found. Set GOOGLE_CLIENT_SECRETS_JSON env var.")

        flow = Flow.from_client_secrets_file(
            self.client_secrets_file,
            scopes=SCOPES,
            redirect_uri=self.redirect_uri
        )
        
        # Enable offline access to get a refresh token
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            state=user_id
        )
        return auth_url

    def get_credentials_from_code(self, code: str):
        """
        Exchanges the auth code for credentials.
        """
        flow = Flow.from_client_secrets_file(
            self.client_secrets_file,
            scopes=SCOPES,
            redirect_uri=self.redirect_uri
        )
        flow.fetch_token(code=code)
        return flow.credentials

    def upload_video(self, file_path: str, title: str, description: str, credentials_dict: dict):
        """
        Uploads a video to YouTube using the provided credentials.
        credentials_dict should contain: token, refresh_token, token_uri, client_id, client_secret, scopes
        """
        import google.oauth2.credentials
        
        creds = google.oauth2.credentials.Credentials(
            **credentials_dict
        )

        youtube = build('youtube', 'v3', credentials=creds)

        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': ['Vykso', 'AI Video'],
                'categoryId': '22'
            },
            'status': {
                'privacyStatus': 'private', # Default to private for safety
                'selfDeclaredMadeForKids': False,
            }
        }

        media = MediaFileUpload(file_path, chunksize=-1, resumable=True)

        request = youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"Uploaded {int(status.progress() * 100)}%")

        return response
