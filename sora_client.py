import os
import time
from typing import Optional
import httpx

try:
    from openai import OpenAI
    HAS_OPENAI_SDK = True
except ImportError:
    HAS_OPENAI_SDK = False


class SoraClient:
    """Client for OpenAI Sora 2 Videos API.

    Uses environment variable OPENAI_API_KEY for auth.
    Supports both OpenAI SDK (if available) and direct HTTP calls.
    """

    def __init__(self, api_key: Optional[str] = None):
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.api_key = api_key
        self.base_url = "https://api.openai.com/v1"
        
        # Try to use OpenAI SDK if available and if it supports videos API
        if HAS_OPENAI_SDK:
            try:
                self.client = OpenAI(api_key=api_key)
                # Test if videos API is available
                # If not, we'll fall back to httpx
                if hasattr(self.client, 'videos'):
                    self.use_sdk = True
                else:
                    self.use_sdk = False
            except Exception:
                self.use_sdk = False
        else:
            self.use_sdk = False

    def generate_video_and_wait(
        self,
        prompt: str,
        *,
        use_pro: bool = False,
        size: Optional[str] = None,  # e.g., "1280x720"
        seconds: Optional[int] = None,  # e.g., 8, 10, 15
        download_path: str = "output.mp4",
    ) -> str:
        """Start a Sora job, poll until complete, then download MP4 to download_path.

        - use_pro: True => model "sora-2-pro", else "sora-2"
        - size: optional (e.g., 1280x720); if None, Sora default is used
        - seconds: optional duration; if None, Sora default is used
        Returns the local file path to the downloaded MP4.
        """
        if self.use_sdk:
            return self._generate_with_sdk(prompt, use_pro, size, seconds, download_path)
        else:
            return self._generate_with_httpx(prompt, use_pro, size, seconds, download_path)
    
    def _generate_with_sdk(
        self,
        prompt: str,
        use_pro: bool,
        size: Optional[str],
        seconds: Optional[int],
        download_path: str,
    ) -> str:
        """Generate video using OpenAI SDK."""
        model = "sora-2-pro" if use_pro else "sora-2"

        # Prepare request parameters
        create_params = {
            "model": model,
            "prompt": prompt,
        }
        if size:
            create_params["size"] = size
        if seconds:
            # API expects string: '4', '8', or '12'
            # Round to nearest allowed value
            if seconds <= 4:
                seconds_str = "4"
            elif seconds <= 8:
                seconds_str = "8"
            else:
                seconds_str = "12"
            create_params["seconds"] = seconds_str

        # Start video generation job
        video = self.client.videos.create(**create_params)
        video_id = video.id

        # Poll until complete
        while video.status in ("in_progress", "queued"):
            time.sleep(10)  # Poll every 10 seconds as recommended
            video = self.client.videos.retrieve(video_id)
            
            # Optional: log progress if available
            if hasattr(video, 'progress') and video.progress:
                print(f"⏳ Video generation progress: {video.progress}%")

        if video.status == "failed":
            error_message = "Video generation failed"
            if hasattr(video, 'error') and video.error:
                if isinstance(video.error, dict):
                    error_message = video.error.get("message", error_message)
                else:
                    error_message = str(video.error)
            raise RuntimeError(error_message)

        if video.status != "completed":
            raise RuntimeError(f"Unexpected video status: {video.status}")

        # Download video content
        print(f"📥 Downloading video {video_id}...")
        content = self.client.videos.download_content(video_id)
        
        # Save to file
        # The content is a binary response that can be read directly
        with open(download_path, "wb") as f:
            f.write(content.read())

        return download_path
    
    def _generate_with_httpx(
        self,
        prompt: str,
        use_pro: bool,
        size: Optional[str],
        seconds: Optional[int],
        download_path: str,
    ) -> str:
        """Generate video using direct HTTP calls (fallback method)."""
        model = "sora-2-pro" if use_pro else "sora-2"

        # Prepare request payload
        payload = {
            "model": model,
            "prompt": prompt,
        }
        if size:
            payload["size"] = size
        if seconds:
            # API expects string: '4', '8', or '12'
            # Round to nearest allowed value
            if seconds <= 4:
                seconds_str = "4"
            elif seconds <= 8:
                seconds_str = "8"
            else:
                seconds_str = "12"
            payload["seconds"] = seconds_str

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Start video generation job
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{self.base_url}/videos",
                headers=headers,
                json=payload,
            )
            # Better error handling: show API error message
            if response.status_code >= 400:
                error_detail = "Unknown error"
                try:
                    error_data = response.json()
                    error_detail = error_data.get("error", {}).get("message", str(error_data))
                except:
                    error_detail = response.text or f"HTTP {response.status_code}"
                print(f"❌ API Error: {error_detail}")
                print(f"📋 Request payload: {payload}")
                response.raise_for_status()
            video = response.json()

        video_id = video["id"]
        print(f"🎬 Video generation started: {video_id}")

        # Poll until complete
        with httpx.Client(timeout=30.0) as client:
            while video.get("status") in ("in_progress", "queued"):
                time.sleep(10)  # Poll every 10 seconds as recommended
                response = client.get(
                    f"{self.base_url}/videos/{video_id}",
                    headers=headers,
                )
                response.raise_for_status()
                video = response.json()
                
                # Log progress if available
                progress = video.get("progress")
                if progress is not None:
                    print(f"⏳ Video generation progress: {progress}%")

        if video.get("status") == "failed":
            error = video.get("error", {})
            message = error.get("message", "Video generation failed") if isinstance(error, dict) else str(error)
            raise RuntimeError(message)

        if video.get("status") != "completed":
            raise RuntimeError(f"Unexpected video status: {video.get('status')}")

        # Download video content using the content endpoint
        print(f"📥 Downloading video {video_id}...")
        with httpx.Client(timeout=300.0) as client:
            response = client.get(
                f"{self.base_url}/videos/{video_id}/content",
                headers=headers,
            )
            response.raise_for_status()
            
            with open(download_path, "wb") as f:
                f.write(response.content)

        return download_path
