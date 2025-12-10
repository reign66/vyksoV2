import os
import time
import base64
from typing import Optional, List, Literal, Union
from io import BytesIO
from PIL import Image

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
            
        if last_frame:
            # Also convert last_frame if it's a PIL Image
            if hasattr(last_frame, 'save'):
                buffered = BytesIO()
                if hasattr(last_frame, 'mode') and last_frame.mode == 'RGBA':
                    last_frame = last_frame.convert('RGB')
                last_frame.save(buffered, format="JPEG", quality=95)
                last_frame_bytes = buffered.getvalue()
                kwargs["last_frame"] = types.Image(image_bytes=last_frame_bytes)
            else:
                kwargs["last_frame"] = last_frame
            
        if reference_images and len(reference_images) > 0:
            # Veo 3.1 supports up to 3 reference images - create VideoGenerationReferenceImage objects
            # CRITICAL: Images MUST be converted to types.Image with image_bytes
            ref_images = []
            for idx, ref_img in enumerate(reference_images[:3]):
                try:
                    # Convert to JPEG bytes
                    img_bytes = self._convert_to_image_bytes(ref_img)
                    print(f"  📸 Reference image {idx + 1}: converted to {len(img_bytes)} bytes")
                    
                    # Create types.Image from bytes
                    img_obj = types.Image(image_bytes=img_bytes)
                    
                    # Create VideoGenerationReferenceImage with proper structure
                    ref_images.append(types.VideoGenerationReferenceImage(
                        image=img_obj,
                        reference_type="asset"  # "asset" for content reference, "style" for style reference
                    ))
                except Exception as e:
                    print(f"  ⚠️ Failed to process reference image {idx + 1}: {e}")
                    continue
            
            if ref_images:
                kwargs["config"] = types.GenerateVideosConfig(
                    **config_kwargs,
                    reference_images=ref_images
                )
                print(f"  ✅ Added {len(ref_images)} reference images to Veo config")

        print(f"🚀 Starting video generation with Veo 3.1...")
        operation = self.client.models.generate_videos(**kwargs)

        print(f"⏳ Waiting for video generation to complete...")
        while not operation.done:
            time.sleep(10)
            operation = self.client.operations.get(operation)

        print(f"✅ Video generation complete, downloading...")
        generated_video = operation.response.generated_videos[0]
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
        Generate video using up to 3 keyframes (START, MIDDLE, END).
        
        This is the preferred method for generating sequences with visual continuity.
        Veo 3.1 will interpolate between the provided keyframes.
        
        Args:
            prompt: Text description of the video motion/action
            keyframes: List of 1-3 images (PIL Image or bytes) representing:
                - keyframes[0]: START frame (beginning of sequence)
                - keyframes[1]: MIDDLE frame (optional, midpoint)
                - keyframes[2]: END frame (optional, end of sequence)
            aspect_ratio: "16:9" (default) or "9:16"
            resolution: "720p" (default) or "1080p"
            duration_seconds: 4, 6, or 8 (must be 8 for multiple keyframes)
            negative_prompt: What to exclude from the video
            download_path: Output file path
            use_fast_model: True for faster generation (lower quality)
            
        Returns:
            Path to the generated video file
        """
        if not keyframes or len(keyframes) == 0:
            raise ValueError("At least 1 keyframe is required")
        
        if len(keyframes) > 3:
            print(f"⚠️ Only first 3 keyframes will be used (provided: {len(keyframes)})")
            keyframes = keyframes[:3]
        
        # For reference images, duration must be 8 seconds
        if len(keyframes) > 1 and duration_seconds != 8:
            print(f"⚠️ Multiple keyframes require 8s duration, adjusting from {duration_seconds}s")
            duration_seconds = 8
        
        model_name = self.MODEL_FAST if use_fast_model else self.MODEL_NORMAL
        print(f"🎥 Generating video with {len(keyframes)} keyframe(s) using {model_name}")
        
        # Convert all keyframes to proper format
        ref_images = []
        for idx, kf in enumerate(keyframes):
            try:
                img_bytes = self._convert_to_image_bytes(kf)
                img_obj = types.Image(image_bytes=img_bytes)
                ref_images.append(types.VideoGenerationReferenceImage(
                    image=img_obj,
                    reference_type="asset"
                ))
                print(f"  ✅ Keyframe {idx + 1} ({['START', 'MIDDLE', 'END'][idx]}): {len(img_bytes)} bytes")
            except Exception as e:
                print(f"  ❌ Failed to process keyframe {idx + 1}: {e}")
                raise
        
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
        
        config = types.GenerateVideosConfig(
            **config_kwargs,
            reference_images=ref_images
        )
        
        print(f"📋 Config: duration={duration_seconds}s, aspect_ratio={aspect_ratio}, keyframes={len(ref_images)}")
        print(f"🚀 Starting keyframe-based video generation...")
        
        operation = self.client.models.generate_videos(
            model=model_name,
            prompt=prompt,
            config=config,
        )
        
        print(f"⏳ Waiting for video generation to complete...")
        while not operation.done:
            time.sleep(10)
            operation = self.client.operations.get(operation)
        
        print(f"✅ Video generation complete, downloading...")
        generated_video = operation.response.generated_videos[0]
        self.client.files.download(file=generated_video.video)
        generated_video.video.save(download_path)
        print(f"💾 Video saved to: {download_path}")
        
        return download_path
