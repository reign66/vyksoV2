import os
import time
from io import BytesIO
from typing import Optional, Union
import httpx
from pathlib import Path
from PIL import Image

# F-07: the Sora API only accepts these durations (seconds)
SORA_VALID_SECONDS = (4, 8, 12)

# Sizes accepted by the Sora API (note: "1920x1080" is NOT valid)
# sora-2 supports only the 720p sizes; sora-2-pro also supports the 1080p-class sizes.
_SORA_SIZES = {
    ("9:16", "720p"): "720x1280",
    ("9:16", "pro_1080p"): "1024x1792",
    ("16:9", "720p"): "1280x720",
    ("16:9", "pro_1080p"): "1792x1024",
}


def _poll_timeout_seconds() -> float:
    """Timeout global de polling (env VIDEO_POLL_TIMEOUT_SECONDS, défaut 900s = 15 min)."""
    try:
        return float(os.getenv("VIDEO_POLL_TIMEOUT_SECONDS", "900"))
    except (TypeError, ValueError):
        return 900.0


def clamp_sora_seconds(seconds: Optional[int]) -> Optional[str]:
    """Clamp a duration to the values accepted by the Sora API ({4, 8, 12}).

    Returns the API string value ('4', '8' or '12'), or None if seconds is falsy.
    Logs a warning when clamping occurs (F-07).
    """
    if not seconds:
        return None
    if seconds <= 4:
        clamped = 4
    elif seconds <= 8:
        clamped = 8
    else:
        clamped = 12
    if clamped != seconds:
        print(f"⚠️ Sora duration {seconds}s is not in {SORA_VALID_SECONDS}, clamped to {clamped}s")
    return str(clamped)


def closest_sora_size(aspect_ratio: str, quality: str, model: str) -> str:
    """Return the exact Sora size string for an aspect ratio / quality / model.

    - 9:16 → "720x1280" (720p) or "1024x1792" (pro_1080p, sora-2-pro only)
    - 16:9 → "1280x720" (720p) or "1792x1024" (pro_1080p, sora-2-pro only)
    - Never returns "1920x1080" (invalid for the API).
    - If pro_1080p is requested on plain sora-2 (720p only), falls back to 720p.
    """
    ratio = "9:16" if str(aspect_ratio).strip() == "9:16" else "16:9"

    quality_norm = str(quality or "").strip().lower()
    wants_pro_1080 = quality_norm in ("pro_1080p", "1080p", "pro1080p", "pro")

    is_pro_model = "pro" in str(model or "").lower()
    if wants_pro_1080 and not is_pro_model:
        print(f"⚠️ pro_1080p requested on model '{model}' (720p only) — falling back to 720p size")
        wants_pro_1080 = False

    return _SORA_SIZES[(ratio, "pro_1080p" if wants_pro_1080 else "720p")]


class SoraClient:
    """Client for OpenAI Sora 2 Videos API.

    Uses environment variable OPENAI_API_KEY for auth.
    Talks to the API directly via httpx (the installed openai SDK has no videos API).
    """

    def __init__(self, api_key: Optional[str] = None):
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.api_key = api_key
        self.base_url = "https://api.openai.com/v1"

    @staticmethod
    def resize_image_to(image_bytes: bytes, size: str) -> bytes:
        """Resize/crop an image to exactly the WxH of a Sora size string (F-03).

        Cover-fit then center-crop: the image is scaled so it fully covers the
        target dimensions, then center-cropped to match exactly. The Sora API
        requires the input_reference image to match the video dimensions.

        Args:
            image_bytes: Source image bytes (any PIL-readable format)
            size: Sora size string, e.g. "1280x720" or "720x1280"

        Returns:
            JPEG bytes (or PNG bytes if the source has transparency)
        """
        target_w, target_h = (int(v) for v in size.lower().split("x"))

        img = Image.open(BytesIO(image_bytes))
        img.load()

        has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
        img = img.convert("RGBA" if has_alpha else "RGB")

        src_w, src_h = img.size
        # Cover-fit: scale so both dimensions cover the target
        scale = max(target_w / src_w, target_h / src_h)
        new_w = max(target_w, int(round(src_w * scale)))
        new_h = max(target_h, int(round(src_h * scale)))
        img = img.resize((new_w, new_h), Image.LANCZOS)

        # Center-crop to exact target size
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        img = img.crop((left, top, left + target_w, top + target_h))

        buffered = BytesIO()
        if has_alpha:
            img.save(buffered, format="PNG")
        else:
            img.save(buffered, format="JPEG", quality=95)
        return buffered.getvalue()

    def generate_video_and_wait(
        self,
        prompt: str,
        *,
        use_pro: bool = False,
        size: Optional[str] = None,  # e.g., "1280x720"
        seconds: Optional[int] = None,  # clamped to 4, 8 or 12
        input_reference: Optional[Union[str, Path, bytes]] = None,  # Image file path, URL, or bytes
        download_path: str = "output.mp4",
    ) -> str:
        """Start a Sora job, poll until complete, then download MP4 to download_path.

        - use_pro: True => model "sora-2-pro", else "sora-2"
        - size: optional (e.g., 1280x720); if None, Sora default is used
        - seconds: optional duration; clamped to SORA_VALID_SECONDS (4, 8, 12)
        - input_reference: optional image file path, URL, or bytes for image-to-video.
          If its dimensions don't match `size`, it is automatically resized (cover-fit
          center-crop) to match — the API requires an exact match.
        Returns the local file path to the downloaded MP4.
        """
        model = "sora-2-pro" if use_pro else "sora-2"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        seconds_str = clamp_sora_seconds(seconds)

        # Handle input_reference - if present, use multipart/form-data
        if input_reference:
            image_data = None
            image_filename = "input_reference.jpg"
            image_content_type = "image/jpeg"

            if isinstance(input_reference, (str, Path)):
                if str(input_reference).startswith(('http://', 'https://')):
                    # Download from URL
                    with httpx.Client(timeout=30.0) as client:
                        resp = client.get(str(input_reference), follow_redirects=True)
                        resp.raise_for_status()
                        image_data = resp.content
                        # Try to determine content type from response
                        content_type = resp.headers.get("content-type", "image/jpeg")
                        if "png" in content_type:
                            image_filename = "input_reference.png"
                            image_content_type = "image/png"
                        elif "webp" in content_type:
                            image_filename = "input_reference.webp"
                            image_content_type = "image/webp"
                else:
                    # Local file path — read bytes with a context manager (no leaked handle)
                    with open(input_reference, "rb") as f:
                        image_data = f.read()
                    # Determine file extension
                    path_str = str(input_reference)
                    if path_str.endswith('.png'):
                        image_filename = "input_reference.png"
                        image_content_type = "image/png"
                    elif path_str.endswith('.webp'):
                        image_filename = "input_reference.webp"
                        image_content_type = "image/webp"
            elif isinstance(input_reference, bytes):
                image_data = input_reference

            # Defense in depth (F-03): the API requires the reference image to match
            # the video dimensions exactly — resize if it doesn't.
            if image_data and size:
                try:
                    with Image.open(BytesIO(image_data)) as probe:
                        img_size = probe.size
                    target = tuple(int(v) for v in size.lower().split("x"))
                    if img_size != target:
                        print(f"🖼️ input_reference is {img_size[0]}x{img_size[1]}, resizing to {size}...")
                        image_data = self.resize_image_to(image_data, size)
                        image_filename = "input_reference.png" if image_data[:8] == b"\x89PNG\r\n\x1a\n" else "input_reference.jpg"
                        image_content_type = "image/png" if image_filename.endswith(".png") else "image/jpeg"
                except Exception as resize_err:
                    print(f"⚠️ Could not verify/resize input_reference: {resize_err}")

            # Use multipart/form-data for file upload
            files = {
                "input_reference": (image_filename, image_data, image_content_type)
            }
            data = {
                "model": model,
                "prompt": prompt,
            }
            if size:
                data["size"] = size
            if seconds_str:
                data["seconds"] = seconds_str

            # Start video generation job with multipart/form-data
            with httpx.Client(timeout=60.0) as client:
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
            if seconds_str:
                payload["seconds"] = seconds_str

            json_headers = dict(headers)
            json_headers["Content-Type"] = "application/json"

            # Start video generation job
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    f"{self.base_url}/videos",
                    headers=json_headers,
                    json=payload,
                )

        # Better error handling: show API error message
        if response.status_code >= 400:
            error_detail = "Unknown error"
            try:
                error_data = response.json()
                error_detail = error_data.get("error", {}).get("message", str(error_data))
            except Exception:
                error_detail = response.text or f"HTTP {response.status_code}"
            print(f"❌ API Error: {error_detail}")
            print(f"📋 Model: {model}, Prompt: {prompt[:100]}...")
            response.raise_for_status()
        video = response.json()

        video_id = video["id"]
        print(f"🎬 Video generation started: {video_id}")

        # Poll until complete, with a hard deadline (F-14)
        timeout = _poll_timeout_seconds()
        deadline = time.monotonic() + timeout
        with httpx.Client(timeout=30.0) as client:
            while video.get("status") in ("in_progress", "queued"):
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Sora video generation timed out after {timeout:.0f}s "
                        f"(VIDEO_POLL_TIMEOUT_SECONDS), job {video_id}"
                    )
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
