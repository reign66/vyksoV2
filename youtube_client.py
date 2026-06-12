import os
import json
import hmac
import time
import hashlib
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import google.oauth2.credentials

# Scopes required for YouTube upload and thumbnail management
SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/youtube.force-ssl',  # Required for thumbnails
]

# Lifetime of an OAuth state token (CSRF protection, F-34)
OAUTH_STATE_TTL_SECONDS = 600  # 10 minutes


def _oauth_state_secret() -> bytes:
    """HMAC key for OAuth state signing: OAUTH_STATE_SECRET, with fallback
    to the Supabase service key (always present in this deployment)."""
    secret = (
        os.getenv("OAUTH_STATE_SECRET")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SERVICE_KEY")
        or ""
    )
    return secret.encode("utf-8")


def make_oauth_state(user_id: str) -> str:
    """Build a signed OAuth state token: '{user_id}:{expiry_ts}:{hmac_sha256_hex}'.

    The HMAC (key = OAUTH_STATE_SECRET, fallback Supabase service key) covers
    'user_id:expiry_ts'. Expiry = now + 10 minutes. Used as the `state`
    parameter of the OAuth flow to prevent CSRF (F-34).
    """
    expiry_ts = int(time.time()) + OAUTH_STATE_TTL_SECONDS
    payload = f"{user_id}:{expiry_ts}"
    signature = hmac.new(_oauth_state_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def verify_oauth_state(state: str) -> Optional[str]:
    """Verify a state token built by make_oauth_state.

    Returns the user_id if the signature is valid and the token is not
    expired, else None. Uses hmac.compare_digest (constant-time).
    """
    try:
        user_id, expiry_str, signature = state.rsplit(":", 2)
        expiry_ts = int(expiry_str)
    except (AttributeError, ValueError):
        return None

    payload = f"{user_id}:{expiry_ts}"
    expected = hmac.new(_oauth_state_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    if time.time() > expiry_ts:
        return None
    return user_id


class YouTubeUploadResult:
    """
    Result object for YouTube upload operations.
    """
    def __init__(
        self,
        success: bool,
        youtube_id: Optional[str] = None,
        youtube_url: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        scheduled_for: Optional[str] = None,
        scheduled_for_display: Optional[str] = None,
        error: Optional[str] = None,
        thumbnail_uploaded: bool = False
    ):
        self.success = success
        self.youtube_id = youtube_id
        self.youtube_url = youtube_url
        self.title = title
        self.description = description
        self.scheduled_for = scheduled_for
        self.scheduled_for_display = scheduled_for_display
        self.error = error
        self.thumbnail_uploaded = thumbnail_uploaded
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "youtube_id": self.youtube_id,
            "youtube_url": self.youtube_url,
            "title": self.title,
            "description": self.description,
            "scheduled_for": self.scheduled_for,
            "scheduled_for_display": self.scheduled_for_display,
            "error": self.error,
            "thumbnail_uploaded": self.thumbnail_uploaded
        }


class YouTubeClient:
    def __init__(self):
        # F-38: client secrets are read directly from the env var — no shared
        # /tmp file (world-readable on multi-tenant hosts).
        self.redirect_uri = f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/youtube-callback"

    def _build_flow(self, scopes: List[str]) -> Flow:
        """Builds an OAuth Flow directly from the GOOGLE_CLIENT_SECRETS_JSON env var (F-38)."""
        secrets_json = os.getenv("GOOGLE_CLIENT_SECRETS_JSON")
        if not secrets_json:
            raise ValueError("Google Client Secrets not found. Set GOOGLE_CLIENT_SECRETS_JSON env var.")

        return Flow.from_client_config(
            json.loads(secrets_json),
            scopes=scopes,
            redirect_uri=self.redirect_uri
        )

    def get_auth_url(self, user_id: str):
        """
        Generates the OAuth 2.0 authorization URL.

        Note: `user_id` is used as the OAuth `state` value. For CSRF protection,
        pass a signed token built with make_oauth_state(user_id) and verify it
        in the callback with verify_oauth_state() (F-34).
        """
        flow = self._build_flow(SCOPES)

        # Enable offline access to get a refresh token
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            state=user_id,
            prompt='consent'  # Force consent to ensure we get a refresh token
        )
        return auth_url

    def get_credentials_from_code(self, code: str):
        """
        Exchanges the auth code for credentials.
        Google may return additional scopes (userinfo.email, userinfo.profile, openid)
        that we need to accept to avoid scope validation errors.
        """
        # Include scopes that Google automatically adds to avoid validation errors
        extended_scopes = SCOPES + [
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile',
            'openid'
        ]

        flow = self._build_flow(extended_scopes)
        flow.fetch_token(code=code)
        return flow.credentials

    @staticmethod
    def credentials_to_dict(creds: google.oauth2.credentials.Credentials) -> Dict[str, Any]:
        """Serializes credentials to a dict, INCLUDING `expiry` (ISO format)
        so proactive refresh can work (F-35)."""
        return {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': list(creds.scopes) if creds.scopes else SCOPES,
            'expiry': creds.expiry.isoformat() if creds.expiry else None,
        }

    @staticmethod
    def _credentials_from_dict(credentials_dict: Dict[str, Any]) -> google.oauth2.credentials.Credentials:
        """Reconstructs Credentials from a dict, parsing the optional `expiry`
        ISO string into the naive-UTC datetime google-auth expects (F-35)."""
        cred_kwargs = {k: v for k, v in credentials_dict.items() if k != 'expiry'}
        expiry_raw = credentials_dict.get('expiry')
        expiry_dt = None
        if expiry_raw:
            try:
                expiry_dt = datetime.fromisoformat(str(expiry_raw).replace('Z', '+00:00'))
                if expiry_dt.tzinfo is not None:
                    # google-auth expects a naive UTC datetime
                    expiry_dt = expiry_dt.astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                print(f"⚠️ Could not parse credentials expiry '{expiry_raw}', treating as unknown")
                expiry_dt = None

        return google.oauth2.credentials.Credentials(expiry=expiry_dt, **cred_kwargs)

    def _validate_credentials_dict(self, credentials_dict: Dict[str, Any]) -> tuple[bool, str]:
        """
        Validates that the credentials dict contains all required fields.
        
        Returns:
            (is_valid, error_message)
        """
        required_fields = ['token', 'refresh_token', 'token_uri', 'client_id', 'client_secret']
        missing_fields = [f for f in required_fields if not credentials_dict.get(f)]
        
        if missing_fields:
            return False, f"Missing required credential fields: {', '.join(missing_fields)}. Please reconnect your YouTube account."
        
        return True, ""

    def _get_youtube_service(self, credentials_dict: Dict[str, Any]):
        """
        Creates an authenticated YouTube API service.
        """
        # Validate credentials before attempting to use them
        is_valid, error_msg = self._validate_credentials_dict(credentials_dict)
        if not is_valid:
            raise ValueError(error_msg)

        creds = self._credentials_from_dict(credentials_dict)

        # F-35: refresh proactively when the token is expired OR when the
        # expiry is unknown (legacy dicts saved without `expiry`).
        if creds.refresh_token and (creds.expired or creds.expiry is None):
            creds.refresh(Request())

        return build('youtube', 'v3', credentials=creds), creds

    def upload_video(
        self,
        file_path: str,
        title: str,
        description: str,
        credentials_dict: Dict[str, Any],
        privacy: str = 'public',
        tags: Optional[List[str]] = None,
        schedule_time: Optional[str] = None,
        category_id: str = '22'  # People & Blogs
    ) -> YouTubeUploadResult:
        """
        Uploads a video to YouTube using the provided credentials.
        
        Args:
            file_path: Path to the video file
            title: Video title
            description: Video description
            credentials_dict: OAuth credentials dict with token, refresh_token, etc.
            privacy: 'public', 'private', or 'unlisted'
            tags: List of tags for the video
            schedule_time: ISO 8601 formatted datetime for scheduling (requires private privacy)
            category_id: YouTube category ID (default: '22' for People & Blogs)
            
        Returns:
            YouTubeUploadResult with upload details
        """
        try:
            youtube, creds = self._get_youtube_service(credentials_dict)
            
            # Determine privacy status
            # When scheduling, video MUST be private
            if schedule_time:
                actual_privacy = 'private'
            else:
                actual_privacy = privacy if privacy in ['public', 'private', 'unlisted'] else 'public'
            
            # Build request body
            body = {
                'snippet': {
                    'title': title[:100],  # YouTube limit
                    'description': description[:5000],  # YouTube limit
                    'tags': tags or ['Shorts', 'AI', 'Vykso'],
                    'categoryId': category_id
                },
                'status': {
                    'privacyStatus': actual_privacy,
                    'selfDeclaredMadeForKids': False,
                    'embeddable': True,
                    'publicStatsViewable': True
                }
            }
            
            # Add scheduling if provided
            if schedule_time:
                body['status']['publishAt'] = schedule_time
            
            # Create media upload
            media = MediaFileUpload(
                file_path,
                chunksize=1024 * 1024,  # 1MB chunks
                resumable=True,
                mimetype='video/mp4'
            )

            request = youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    print(f"📤 Upload progress: {int(status.progress() * 100)}%")

            video_id = response.get('id')
            video_url = f"https://www.youtube.com/shorts/{video_id}"
            
            print(f"✅ Video uploaded successfully: {video_url}")
            
            return YouTubeUploadResult(
                success=True,
                youtube_id=video_id,
                youtube_url=video_url,
                title=title,
                description=description,
                scheduled_for=schedule_time
            )

        except Exception as e:
            print(f"❌ YouTube upload error: {e}")
            return YouTubeUploadResult(
                success=False,
                error=str(e)
            )

    def upload_thumbnail(
        self,
        video_id: str,
        thumbnail_path: str,
        credentials_dict: Dict[str, Any]
    ) -> bool:
        """
        Uploads a custom thumbnail for a YouTube video.
        
        Args:
            video_id: The YouTube video ID
            thumbnail_path: Path to the thumbnail image file (JPEG or PNG)
            credentials_dict: OAuth credentials dict
            
        Returns:
            True if successful, False otherwise
        """
        try:
            youtube, creds = self._get_youtube_service(credentials_dict)
            
            # Determine content type
            if thumbnail_path.lower().endswith('.png'):
                mime_type = 'image/png'
            else:
                mime_type = 'image/jpeg'
            
            media = MediaFileUpload(
                thumbnail_path,
                mimetype=mime_type,
                resumable=True
            )
            
            request = youtube.thumbnails().set(
                videoId=video_id,
                media_body=media
            )
            
            response = request.execute()
            
            print(f"✅ Thumbnail uploaded for video {video_id}")
            return True
            
        except Exception as e:
            print(f"❌ Thumbnail upload error: {e}")
            return False

    def upload_video_with_thumbnail(
        self,
        file_path: str,
        title: str,
        description: str,
        credentials_dict: Dict[str, Any],
        privacy: str = 'public',
        tags: Optional[List[str]] = None,
        schedule_time: Optional[str] = None,
        thumbnail_bytes: Optional[bytes] = None,
        thumbnail_path: Optional[str] = None
    ) -> YouTubeUploadResult:
        """
        Complete workflow: Upload video and then upload thumbnail.
        
        Args:
            file_path: Path to the video file
            title: Video title
            description: Video description
            credentials_dict: OAuth credentials dict
            privacy: 'public', 'private', or 'unlisted'
            tags: List of tags
            schedule_time: ISO 8601 datetime for scheduling
            thumbnail_bytes: Thumbnail image as bytes (optional)
            thumbnail_path: Path to existing thumbnail file (optional)
            
        Returns:
            YouTubeUploadResult with complete details
        """
        # Step 1: Upload the video
        result = self.upload_video(
            file_path=file_path,
            title=title,
            description=description,
            credentials_dict=credentials_dict,
            privacy=privacy,
            tags=tags,
            schedule_time=schedule_time
        )
        
        if not result.success or not result.youtube_id:
            return result
        
        # Step 2: Upload thumbnail if provided
        thumbnail_uploaded = False
        temp_thumbnail_path = None
        
        try:
            if thumbnail_bytes:
                # Save bytes to temp file
                temp_thumbnail_path = f"/tmp/thumbnail_{result.youtube_id}.png"
                with open(temp_thumbnail_path, 'wb') as f:
                    f.write(thumbnail_bytes)
                thumbnail_path = temp_thumbnail_path
            
            if thumbnail_path:
                thumbnail_uploaded = self.upload_thumbnail(
                    video_id=result.youtube_id,
                    thumbnail_path=thumbnail_path,
                    credentials_dict=credentials_dict
                )
                
        except Exception as e:
            # Don't fail the entire operation if thumbnail fails
            print(f"⚠️ Thumbnail upload failed but video was uploaded: {e}")
            
        finally:
            # Clean up temp file
            if temp_thumbnail_path and os.path.exists(temp_thumbnail_path):
                try:
                    os.remove(temp_thumbnail_path)
                except:
                    pass
        
        result.thumbnail_uploaded = thumbnail_uploaded
        return result

    def refresh_credentials(self, credentials_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Refreshes the credentials (F-35: actually refreshes).

        The access token is force-refreshed whenever a refresh_token is
        available, and the returned dict always includes `expiry` (ISO format)
        so callers can persist it and proactive refresh works next time.

        Args:
            credentials_dict: The current credentials dict

        Returns:
            Updated credentials dict (with fresh token + expiry) or None if refresh failed
        """
        try:
            # Validate credentials first
            is_valid, error_msg = self._validate_credentials_dict(credentials_dict)
            if not is_valid:
                print(f"❌ Invalid credentials: {error_msg}")
                return None

            creds = self._credentials_from_dict(credentials_dict)

            if not creds.refresh_token:
                print("❌ No refresh_token available, cannot refresh")
                return None

            # Force refresh so the caller always gets a fresh token + known expiry
            creds.refresh(Request())

            return self.credentials_to_dict(creds)

        except Exception as e:
            print(f"❌ Error refreshing credentials: {e}")
            return None
