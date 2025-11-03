import os
import time
from typing import Optional

from openai import OpenAI


class SoraClient:
    """Client for OpenAI Sora 2 Videos API.

    Uses environment variable OPENAI_API_KEY for auth.
    """

    def __init__(self, api_key: Optional[str] = None):
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.client = OpenAI(api_key=api_key)

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

        # Start job
        video = self.client.videos.create(
            model=model,
            prompt=prompt,
            size=size,
            seconds=str(seconds) if seconds else None,
        )

        # Poll
        while video.status in ("in_progress", "queued"):
            time.sleep(5)
            video = self.client.videos.retrieve(video.id)

        if video.status == "failed":
            # Try to surface error message if present
            message = getattr(getattr(video, "error", None), "message", "Video generation failed")
            raise RuntimeError(message)

        # Download content
        content = self.client.videos.download_content(video.id, variant="video")
        content.write_to_file(download_path)
        return download_path
