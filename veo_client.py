import os
import time
from typing import Optional

from google import genai


class VeoAIClient:
    """Client pour Veo 3.1 via l'API Gemini (Google GenAI)."""

    def __init__(self, api_key: Optional[str] = None):
        api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self.client = genai.Client(api_key=api_key)

    def generate_video_and_wait(
        self,
        prompt: str,
        *,
        use_fast_model: bool = True,
        aspect_ratio: str = "16:9",
        negative_prompt: Optional[str] = None,
        image: Optional[object] = None,
        download_path: str = "output.mp4",
    ) -> str:
        """Lance la génération Veo 3 et attend la fin, retourne le chemin du MP4.

        - use_fast_model: True => veo-3.0-fast-generate-001, False => veo-3.0-generate-001
        - aspect_ratio: "16:9" ou "9:16"
        - image: optionnel, objet image pour image-to-video
        - download_path: chemin local du MP4
        """

        model_name = "veo-3.0-fast-generate-001" if use_fast_model else "veo-3.0-generate-001"

        config = None
        if negative_prompt or aspect_ratio:
            config = {}
            if negative_prompt:
                config["negativePrompt"] = negative_prompt
            if aspect_ratio:
                config["aspectRatio"] = aspect_ratio

        operation = self.client.models.generate_videos(
            model=model_name,
            prompt=prompt,
            image=image,
            config=config,
        )

        while not operation.done:
            time.sleep(10)
            operation = self.client.operations.get(operation)

        generated_video = operation.response.generated_videos[0]
        self.client.files.download(file=generated_video.video)
        generated_video.video.save(download_path)
        return download_path
