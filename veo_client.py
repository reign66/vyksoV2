import os
import time
from typing import Optional, List, Literal

from google import genai
from google.genai import types


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

        # Build config
        config = {
            "aspectRatio": aspect_ratio,
            "durationSeconds": str(duration_seconds),
        }
        
        # Resolution only for 720p/1080p
        if resolution:
            config["resolution"] = resolution
            
        if negative_prompt:
            config["negativePrompt"] = negative_prompt
            
        # Person generation based on whether we have an image
        if image:
            config["personGeneration"] = "allow_adult"
        else:
            config["personGeneration"] = "allow_all"

        # Build kwargs for generate_videos
        kwargs = {
            "model": model_name,
            "prompt": prompt,
            "config": config,
        }
        
        if image:
            kwargs["image"] = image
            
        if last_frame:
            kwargs["lastFrame"] = last_frame
            
        if reference_images and len(reference_images) > 0:
            # Veo 3.1 supports up to 3 reference images
            kwargs["referenceImages"] = reference_images[:3]

        operation = self.client.models.generate_videos(**kwargs)

        while not operation.done:
            time.sleep(10)
            operation = self.client.operations.get(operation)

        generated_video = operation.response.generated_videos[0]
        self.client.files.download(file=generated_video.video)
        generated_video.video.save(download_path)
        return download_path
