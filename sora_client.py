import os
import time
from typing import Optional
import httpx


class SoraClient:
    """Client for OpenAI Sora 2 Videos API.

    Uses environment variable OPENAI_API_KEY for auth.
    """

    def __init__(self, api_key: Optional[str] = None):
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.api_key = api_key
        self.base_url = "https://api.openai.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

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
        model = "sora-2-pro" if use_pro else "sora-2"

        # Prepare request payload
        payload = {
            "model": model,
            "prompt": prompt,
        }
        if size:
            payload["size"] = size
        if seconds:
            payload["seconds"] = str(seconds)

        # Start job
        with httpx.Client() as client:
            response = client.post(
                f"{self.base_url}/videos",
                headers=self.headers,
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            video = response.json()

        video_id = video["id"]

        # Poll until complete
        with httpx.Client() as client:
            while video.get("status") in ("in_progress", "queued"):
                time.sleep(5)
                response = client.get(
                    f"{self.base_url}/videos/{video_id}",
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                video = response.json()

        if video.get("status") == "failed":
            error = video.get("error", {})
            message = error.get("message", "Video generation failed")
            raise RuntimeError(message)

        # Download content
        download_url = video.get("download_url") or video.get("url")
        if not download_url:
            raise RuntimeError("No download URL found in video response")

        with httpx.Client() as client:
            response = client.get(download_url, timeout=300.0)
            response.raise_for_status()
            with open(download_path, "wb") as f:
                f.write(response.content)

        return download_path
