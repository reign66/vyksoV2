import os
import time
import base64
from typing import Optional, List, Literal, Union
from io import BytesIO
from PIL import Image

from google import genai
from google.genai import types


def _poll_timeout_seconds() -> float:
    """Timeout global de polling (env VIDEO_POLL_TIMEOUT_SECONDS, défaut 900s = 15 min)."""
    try:
        return float(os.getenv("VIDEO_POLL_TIMEOUT_SECONDS", "900"))
    except (TypeError, ValueError):
        return 900.0


class VeoAIClient:
    """Client pour Veo 3.1 via l'API Gemini (Google GenAI)."""

    # Modèles Veo 3.1 disponibles
    MODEL_NORMAL = "veo-3.1-generate-preview"
    MODEL_FAST = "veo-3.1-fast-generate-preview"

    def __init__(self, api_key: Optional[str] = None):
        api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self.client = genai.Client(api_key=api_key)

    def _convert_to_image_bytes(self, img: Union[Image.Image, bytes, str]) -> bytes:
        """
        Convert various image formats to JPEG bytes suitable for Veo API.
        
        Args:
            img: PIL Image, bytes, or base64 string
            
        Returns:
            JPEG image bytes
        """
        if isinstance(img, bytes):
            # Validate and potentially reconvert to JPEG
            try:
                pil_img = Image.open(BytesIO(img))
                pil_img.load()
                # Convert to RGB if needed (handles RGBA)
                if pil_img.mode in ('RGBA', 'P'):
                    pil_img = pil_img.convert('RGB')
                buffered = BytesIO()
                pil_img.save(buffered, format="JPEG", quality=95)
                return buffered.getvalue()
            except Exception:
                return img  # Return as-is if already valid
                
        elif isinstance(img, str):
            # Assume base64 encoded
            img_bytes = base64.b64decode(img)
            return self._convert_to_image_bytes(img_bytes)
            
        elif hasattr(img, 'save'):  # PIL Image
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            buffered = BytesIO()
            img.save(buffered, format="JPEG", quality=95)
            return buffered.getvalue()
            
        else:
            raise ValueError(f"Unsupported image type: {type(img)}")

    def _start_generation(self, gen_kwargs: dict, config_kwargs: dict):
        """Start generate_videos, retrying once with person_generation='allow_adult'
        if the API rejects 'allow_all' (400 in some regions — F-12)."""
        try:
            return self.client.models.generate_videos(**gen_kwargs)
        except Exception as e:
            msg = str(e).lower()
            if config_kwargs.get("person_generation") == "allow_all" and (
                "person_generation" in msg or "persongeneration" in msg
                or "allow_all" in msg or "allowall" in msg
            ):
                print("⚠️ person_generation='allow_all' rejected by API, retrying with 'allow_adult'...")
                config_kwargs["person_generation"] = "allow_adult"
                gen_kwargs["config"] = types.GenerateVideosConfig(**config_kwargs)
                return self.client.models.generate_videos(**gen_kwargs)
            raise

    def _wait_and_validate(self, operation):
        """Poll the operation with a hard deadline (F-14), then validate the
        result (F-05). Returns the first generated video."""
        timeout = _poll_timeout_seconds()
        deadline = time.monotonic() + timeout
        while not operation.done:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Veo video generation timed out after {timeout:.0f}s "
                    f"(VIDEO_POLL_TIMEOUT_SECONDS)"
                )
            time.sleep(10)
            operation = self.client.operations.get(operation)

        # F-05: validate the completed operation
        op_error = getattr(operation, "error", None)
        if op_error:
            raise RuntimeError(f"Veo video generation failed: {op_error}")

        response = getattr(operation, "response", None)
        generated_videos = getattr(response, "generated_videos", None) if response else None
        if not generated_videos:
            rai_reasons = getattr(response, "rai_media_filtered_reasons", None) if response else None
            detail = f" RAI filter reasons: {rai_reasons}" if rai_reasons else ""
            raise RuntimeError(
                "Veo returned no generated video — the request was likely blocked by "
                "RAI/safety filtering (prompt or image rejected)." + detail
            )
        return generated_videos[0]

    def generate_video_and_wait(
        self,
        prompt: str,
        *,
        aspect_ratio: str = "9:16",
        resolution: str = "720p",
        duration_seconds: int = 8,
        negative_prompt: Optional[str] = None,
        image: Optional[object] = None,
        last_frame: Optional[object] = None,
        reference_images: Optional[List[object]] = None,
        download_path: str = "output.mp4",
        use_fast_model: bool = False,
    ) -> str:
        """Lance la génération Veo 3.1 et attend la fin, retourne le chemin du MP4.

        Veo 3.1 Parameters:
        - prompt: Text description of the video (supports audio cues)
        - aspect_ratio: "16:9" (default for 720p/1080p) or "9:16"
        - resolution: "720p" (default) or "1080p" (only supports 8s duration)
        - duration_seconds: 4, 6, or 8 (must be 8 for extension/interpolation/referenceImages)
        - negative_prompt: Text describing what to exclude from the video
        - image: Initial image to animate (Image object)
        - last_frame: Final image for video interpolation (must be used with image)
        - reference_images: Up to 3 images for style/content reference (Veo 3.1 only, requires 8s duration, 16:9 only)
        - download_path: Local path for the MP4
        - use_fast_model: If True, uses veo-3.1-fast-generate-preview (faster but may have lower quality)
                          If False (default), uses veo-3.1-generate-preview (normal quality)
        """

        # Sélection du modèle : fast ou normal
        model_name = self.MODEL_FAST if use_fast_model else self.MODEL_NORMAL
        print(f"🎥 Using Veo 3.1 model: {model_name}")

        # Validate and normalize duration for Veo 3.1 (must be 4, 6, or 8 seconds)
        # Veo 3.1 only supports these specific durations
        valid_durations = [4, 6, 8]
        if duration_seconds not in valid_durations:
            # Round to nearest valid duration
            if duration_seconds < 5:
                duration_seconds = 4
            elif duration_seconds < 7:
                duration_seconds = 6
            else:
                duration_seconds = 8
        
        print(f"⏱️ Video duration: {duration_seconds}s")
        
        # Build config using types.GenerateVideosConfig (required by Veo 3.1 API)
        # IMPORTANT: Use camelCase for API parameters (durationSeconds, not duration_seconds)
        config_kwargs = {
            "aspect_ratio": aspect_ratio,
            "number_of_videos": 1,
            "duration_seconds": duration_seconds,  # SDK converts snake_case to camelCase
        }
        
        # Add resolution if specified (720p or 1080p)
        # Note: 1080p only supports 8s duration
        if resolution:
            if resolution == "1080p" and duration_seconds != 8:
                print(f"⚠️ 1080p resolution only supports 8s duration, adjusting...")
                config_kwargs["duration_seconds"] = 8
            config_kwargs["resolution"] = resolution
        
        # Person generation based on whether we have an image
        if image:
            config_kwargs["person_generation"] = "allow_adult"
        else:
            config_kwargs["person_generation"] = "allow_all"
            
        if negative_prompt:
            config_kwargs["negative_prompt"] = negative_prompt

        # F-04: last_frame is a field of GenerateVideosConfig, NOT a kwarg of
        # generate_videos() — it must be set in the config object.
        if last_frame:
            if hasattr(last_frame, 'save'):  # PIL Image
                buffered = BytesIO()
                if hasattr(last_frame, 'mode') and last_frame.mode == 'RGBA':
                    last_frame = last_frame.convert('RGB')
                last_frame.save(buffered, format="JPEG", quality=95)
                last_frame_bytes = buffered.getvalue()
                config_kwargs["last_frame"] = types.Image(image_bytes=last_frame_bytes)
            else:
                config_kwargs["last_frame"] = last_frame

        # Create GenerateVideosConfig object
        config = types.GenerateVideosConfig(**config_kwargs)
        print(f"📋 Veo 3.1 config: duration={duration_seconds}s, aspect_ratio={aspect_ratio}, resolution={resolution}")

        # Build kwargs for generate_videos
        kwargs = {
            "model": model_name,
            "prompt": prompt,
            "config": config,
        }

        if image:
            # Convert PIL Image to bytes if needed for Veo 3.1 API
            if hasattr(image, 'save'):  # PIL Image object
                buffered = BytesIO()
                # Convert to RGB if needed (handles RGBA images)
                if hasattr(image, 'mode') and image.mode == 'RGBA':
                    image = image.convert('RGB')
                image.save(buffered, format="JPEG", quality=95)
                image_bytes = buffered.getvalue()
                # Create Image object from bytes for the SDK
                kwargs["image"] = types.Image(image_bytes=image_bytes)
                print(f"  📸 Converted PIL Image to bytes ({len(image_bytes)} bytes)")
            else:
                kwargs["image"] = image

        # Note: reference_images is NOT supported by current Veo models
        # The API returns: "`referenceImages` isn't supported by this model"
        # If reference_images are provided, we ignore them and log a warning
        if reference_images and len(reference_images) > 0:
            print(f"  ⚠️ reference_images parameter is not supported by Veo models - ignoring {len(reference_images)} images")
            print(f"  ℹ️ Use 'image' parameter for image-to-video or 'last_frame' for video interpolation instead")

        print(f"🚀 Starting video generation with Veo 3.1...")
        operation = self._start_generation(kwargs, config_kwargs)

        print(f"⏳ Waiting for video generation to complete...")
        generated_video = self._wait_and_validate(operation)

        print(f"✅ Video generation complete, downloading...")
        self.client.files.download(file=generated_video.video)
        generated_video.video.save(download_path)
        print(f"💾 Video saved to: {download_path}")
        return download_path

    def generate_video_with_keyframes(
        self,
        prompt: str,
        keyframes: List[Union[Image.Image, bytes]],
        *,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        duration_seconds: int = 8,
        negative_prompt: Optional[str] = None,
        download_path: str = "output.mp4",
        use_fast_model: bool = False,
    ) -> str:
        """
        Generate video using keyframes (START and optionally END for interpolation).
        
        This method uses Veo 3.1's image-to-video and video interpolation features:
        - If 1 keyframe: image-to-video (animates from the provided image)
        - If 2+ keyframes: video interpolation (start to end frame)
        
        Note: The Veo API does NOT support reference_images parameter.
        Instead, it uses 'image' for start frame and 'last_frame' for end frame.
        
        Args:
            prompt: Text description of the video motion/action
            keyframes: List of 1-3 images (PIL Image or bytes):
                - keyframes[0]: START frame (used as 'image' parameter)
                - keyframes[-1]: END frame (used as 'last_frame' if 2+ keyframes)
                - Middle keyframes are not directly supported by Veo API
            aspect_ratio: "16:9" (default) or "9:16"
            resolution: "720p" (default) or "1080p"
            duration_seconds: 4, 6, or 8 (must be 8 for interpolation)
            negative_prompt: What to exclude from the video
            download_path: Output file path
            use_fast_model: True for faster generation (lower quality)
            
        Returns:
            Path to the generated video file
        """
        if not keyframes or len(keyframes) == 0:
            raise ValueError("At least 1 keyframe is required")
        
        # For video interpolation (start + end frames), duration must be 8 seconds
        if len(keyframes) > 1 and duration_seconds != 8:
            print(f"⚠️ Video interpolation requires 8s duration, adjusting from {duration_seconds}s")
            duration_seconds = 8
        
        model_name = self.MODEL_FAST if use_fast_model else self.MODEL_NORMAL
        print(f"🎥 Generating video with {len(keyframes)} keyframe(s) using {model_name}")
        
        # Convert keyframes to proper format
        # Veo API uses 'image' for start frame and 'last_frame' for end frame (NOT reference_images)
        start_frame_bytes = self._convert_to_image_bytes(keyframes[0])
        print(f"  ✅ START keyframe: {len(start_frame_bytes)} bytes")
        
        end_frame_bytes = None
        if len(keyframes) >= 2:
            # Use the last keyframe as the end frame for interpolation
            end_frame_bytes = self._convert_to_image_bytes(keyframes[-1])
            print(f"  ✅ END keyframe: {len(end_frame_bytes)} bytes")
            if len(keyframes) > 2:
                print(f"  ⚠️ Middle keyframes ({len(keyframes) - 2}) are not directly supported by Veo API, using only START and END")
        
        # Build config
        config_kwargs = {
            "aspect_ratio": aspect_ratio,
            "number_of_videos": 1,
            "duration_seconds": duration_seconds,
            "person_generation": "allow_adult",
        }
        
        if resolution:
            if resolution == "1080p" and duration_seconds != 8:
                duration_seconds = 8
                config_kwargs["duration_seconds"] = 8
            config_kwargs["resolution"] = resolution
            
        if negative_prompt:
            config_kwargs["negative_prompt"] = negative_prompt

        # F-04: last_frame belongs in GenerateVideosConfig, NOT as a kwarg of
        # generate_videos() — add end frame for video interpolation if 2+ keyframes
        if end_frame_bytes:
            config_kwargs["last_frame"] = types.Image(image_bytes=end_frame_bytes)
            print(f"📋 Config: duration={duration_seconds}s, aspect_ratio={aspect_ratio}, mode=interpolation (start→end)")
        else:
            print(f"📋 Config: duration={duration_seconds}s, aspect_ratio={aspect_ratio}, mode=image-to-video")

        config = types.GenerateVideosConfig(**config_kwargs)

        # Build kwargs for generate_videos
        kwargs = {
            "model": model_name,
            "prompt": prompt,
            "config": config,
            "image": types.Image(image_bytes=start_frame_bytes),  # Start frame
        }

        print(f"🚀 Starting video generation...")

        operation = self._start_generation(kwargs, config_kwargs)

        print(f"⏳ Waiting for video generation to complete...")
        generated_video = self._wait_and_validate(operation)

        print(f"✅ Video generation complete, downloading...")
        self.client.files.download(file=generated_video.video)
        generated_video.video.save(download_path)
        print(f"💾 Video saved to: {download_path}")
        
        return download_path
