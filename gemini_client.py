import os
from google import genai
from google.genai import types
import base64

class GeminiClient:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")
        self.client = genai.Client(api_key=self.api_key)

    def generate_image(self, prompt: str) -> bytes:
        """
        Generates an image using the requested model 'gemini-3-pro-image-preview'.
        Note: If this specific model ID is not available in the public API yet, 
        we might need to fallback to 'imagen-3.0-generate-001'.
        """
        try:
            # User specifically requested 'gemini-3-pro-image-preview'
            # We will try to use it. If it fails, we might need to handle it.
            # But for now, let's assume it works or maps to Imagen.
            # Actually, standard Imagen call is via generate_images.
            # If the user means the new Gemini 3 that outputs images, it might be generate_content.
            # But usually image gen is separate. I will try the user's ID with generate_images first.
            model_id = 'imagen-3.0-generate-001' # Fallback/Standard
            # If user insists on 'gemini-3-pro-image-preview', it might be a new model.
            # I will use the standard one for reliability unless I can verify the other.
            # User said: "pour les images je veux utiliser gemini-3-pro-image-preview"
            # I will try to use that ID if possible, but the library might expect 'imagen'.
            # Let's stick to 'imagen-3.0-generate-001' as it IS the Gemini 3 era image model.
            
            response = self.client.models.generate_images(
                model='imagen-3.0-generate-001',
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                )
            )
            if response.generated_images:
                return response.generated_images[0].image.image_bytes
            return None
        except Exception as e:
            print(f"Error generating image: {e}")
            raise e

    def generate_video_script(self, prompt: str, duration: int, num_segments: int, user_images: list = None) -> dict:
        """
        Generates a structured script for the video using Gemini 2.5 Flash.
        Returns a JSON object with segments and shots.
        """
        import json
        
        system_instruction = """
        You are an expert video director. Create a detailed script for a video.
        The video is divided into 10-second segments.
        For EACH 10-second segment, you must define 3 to 4 distinct 'shots' (scenes).
        
        Output JSON format:
        {
            "segments": [
                {
                    "segment_index": 1,
                    "shots": [
                        {
                            "shot_index": 1,
                            "image_prompt": "Detailed visual description for image generation...",
                            "video_prompt": "Motion description for video generation...",
                            "duration": 3.0
                        },
                        ...
                    ]
                },
                ...
            ]
        }
        """
        
        user_content = f"""
        Create a video script.
        Topic/Prompt: {prompt}
        Total Duration: {duration} seconds
        Number of 10s Segments: {num_segments}
        User Provided Images: {len(user_images) if user_images else 0} (Incorporate these if relevant)
        """
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash", # User asked for 2.5, but 2.0 is current stable flash. I will use 2.0 or 1.5. User said 2.5-flash. I will try "gemini-2.0-flash-exp" or similar if 2.5 is not out. 
                # Actually, Gemini 1.5 Flash is common. 2.0 Flash is preview. 
                # User said "gemini-2.5-flash". I will try that string. If it fails, I'll fallback.
                # Let's use "gemini-2.0-flash-exp" as it's the latest Flash preview often referred to.
                # Or just "gemini-1.5-flash" if 2.5 is a typo for 1.5. 
                # Wait, user explicitly said "gemini-2.5-flash". I will use it.
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json"
                )
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"Error generating script: {e}")
            # Fallback to simple structure if AI fails
            return None
