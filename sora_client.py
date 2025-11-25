import os
import time
from typing import Optional, Union
import httpx
from pathlib import Path

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
        input_reference: Optional[Union[str, Path, bytes]] = None,  # Image file path, URL, or bytes
        download_path: str = "output.mp4",
    ) -> str:
        """Start a Sora job, poll until complete, then download MP4 to download_path.

        - use_pro: True => model "sora-2-pro", else "sora-2"
        - size: optional (e.g., 1280x720); if None, Sora default is used
        - seconds: optional duration; if None, Sora default is used (4, 8, or 12)
        - input_reference: optional image file path, URL, or bytes for image-to-video
        Returns the local file path to the downloaded MP4.
        
        Note: Model names for API are "sora-2" and "sora-2-pro".
        """
        if self.use_sdk:
            return self._generate_with_sdk(prompt, use_pro, size, seconds, input_reference, download_path)
        else:
            return self._generate_with_httpx(prompt, use_pro, size, seconds, input_reference, download_path)
    
    def _generate_with_sdk(
        self,
        prompt: str,
        use_pro: bool,
        size: Optional[str],
        seconds: Optional[int],
        input_reference: Optional[Union[str, Path, bytes]],
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
        
        # Handle input_reference (image for image-to-video)
        if input_reference:
            if isinstance(input_reference, (str, Path)):
                # File path or URL
                if str(input_reference).startswith(('http://', 'https://')):
                    # Download from URL first
                    import tempfile
                    with httpx.Client(timeout=30.0) as client:
                        resp = client.get(str(input_reference))
                        resp.raise_for_status()
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                            tmp.write(resp.content)
                            input_reference = tmp.name
                create_params["input_reference"] = open(input_reference, "rb")
            elif isinstance(input_reference, bytes):
                # Bytes data - write to temp file
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                    tmp.write(input_reference)
                    create_params["input_reference"] = open(tmp.name, "rb")

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
        input_reference: Optional[Union[str, Path, bytes]],
        download_path: str,
    ) -> str:
        """Generate video using direct HTTP calls (fallback method)."""
        model = "sora-2-pro" if use_pro else "sora-2"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        # Handle input_reference - if present, use multipart/form-data
        if input_reference:
            # Download image if URL
            image_data = None
            image_filename = "input_reference.jpg"
            
            if isinstance(input_reference, (str, Path)):
                if str(input_reference).startswith(('http://', 'https://')):
                    # Download from URL
                    with httpx.Client(timeout=30.0) as client:
                        resp = client.get(str(input_reference))
                        resp.raise_for_status()
                        image_data = resp.content
                        # Try to determine content type from response
                        content_type = resp.headers.get("content-type", "image/jpeg")
                        if "png" in content_type:
                            image_filename = "input_reference.png"
                        elif "webp" in content_type:
                            image_filename = "input_reference.webp"
                else:
                    # Local file path
                    with open(input_reference, "rb") as f:
                        image_data = f.read()
                    # Determine file extension
                    path_str = str(input_reference)
                    if path_str.endswith('.png'):
                        image_filename = "input_reference.png"
                    elif path_str.endswith('.webp'):
                        image_filename = "input_reference.webp"
            elif isinstance(input_reference, bytes):
                image_data = input_reference

            # Use multipart/form-data for file upload
            files = {
                "input_reference": (image_filename, image_data, "image/jpeg")
            }
            data = {
                "model": model,
                "prompt": prompt,
            }
            if size:
                data["size"] = size
            if seconds:
                # API expects string: '4', '8', or '12'
                if seconds <= 4:
                    seconds_str = "4"
                elif seconds <= 8:
                    seconds_str = "8"
                else:
                    seconds_str = "12"
                data["seconds"] = seconds_str

            # Start video generation job with multipart/form-data
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self.base_url}/videos",
                    headers=headers,
                    files=files,
                    data=data,
                )
        else:
            # No image - use JSON
            payload = {
                "model": model,
                "prompt": prompt,
            }
            if size:
                payload["size"] = size
            if seconds:
                # API expects string: '4', '8', or '12'
                if seconds <= 4:
                    seconds_str = "4"
                elif seconds <= 8:
                    seconds_str = "8"
                else:
                    seconds_str = "12"
                payload["seconds"] = seconds_str

            headers["Content-Type"] = "application/json"

            # Start video generation job
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    f"{self.base_url}/videos",
                    headers=headers,
                    json=payload,
                )
        
        # Better error handling: show API error message (applies to both cases)
        if response.status_code >= 400:
            error_detail = "Unknown error"
            try:
                error_data = response.json()
                error_detail = error_data.get("error", {}).get("message", str(error_data))
            except:
                error_detail = response.text or f"HTTP {response.status_code}"
            print(f"❌ API Error: {error_detail}")
            print(f"📋 Model: {model}, Prompt: {prompt[:100]}...")
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
