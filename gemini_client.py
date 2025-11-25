import os
from google import genai
from google.genai import types
import base64
import httpx

class GeminiClient:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")
        self.client = genai.Client(api_key=self.api_key)

    def generate_image(self, prompt: str) -> bytes:
        """
        Generates an image using Gemini 3 Pro Image Preview model.
        Uses generate_content with IMAGE modality for the new model.
        """
        try:
            # Use gemini-3-pro-image-preview as requested
            response = self.client.models.generate_content(
                model='gemini-3-pro-image-preview',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=['IMAGE']
                )
            )
            
            # Extract image bytes from the response
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'inline_data') and part.inline_data:
                        return base64.b64decode(part.inline_data.data)
            return None
        except Exception as e:
            print(f"Error generating image with gemini-3-pro-image-preview: {e}")
            raise e

    def enrich_prompt(self, base_prompt: str, segment_context: str = None, user_image_description: str = None) -> str:
        """
        Enriches a client prompt before image/video generation for higher quality output.
        This adds cinematographic details, visual style, and technical specifications.
        
        Args:
            base_prompt: The original user prompt
            segment_context: Context about where this shot fits in the video (optional)
            user_image_description: Description of user-provided image if any (optional)
        
        Returns:
            Enriched prompt optimized for high-quality generation
        """
        try:
            system_instruction = """
            You are an expert cinematographer and visual director. Your task is to enrich video/image generation prompts
            to produce stunning, professional-quality content.
            
            Rules:
            1. Keep the original intent and subject matter intact
            2. Add specific cinematographic details (camera angles, movements, lighting)
            3. Include visual style descriptors (color grading, mood, atmosphere)
            4. Add technical quality markers (resolution, sharpness, professional grade)
            5. Make it suitable for AI video generation models like Veo 3.1
            6. If a user image is mentioned, incorporate it naturally into the scene
            7. Keep the prompt under 500 characters for optimal generation
            8. Output ONLY the enriched prompt, nothing else
            """
            
            user_content = f"""
            Original prompt: {base_prompt}
            {f'Segment context: {segment_context}' if segment_context else ''}
            {f'User provided image to incorporate: {user_image_description}' if user_image_description else ''}
            
            Enrich this prompt for high-quality video generation.
            """
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                )
            )
            
            enriched = response.text.strip()
            print(f"📝 Enriched prompt: {enriched[:100]}...")
            return enriched
            
        except Exception as e:
            print(f"Error enriching prompt: {e}, using original")
            return base_prompt

    def describe_image_from_url(self, image_url: str) -> str:
        """
        Analyzes a user-provided image and returns a description for prompt enrichment.
        """
        try:
            # Download the image
            response = httpx.get(image_url, timeout=30)
            image_bytes = response.content
            
            # Analyze with Gemini
            image_part = types.Part.from_bytes(
                data=image_bytes,
                mime_type="image/png"
            )
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[
                    image_part,
                    "Describe this image in detail for video generation context. Focus on: subjects, setting, colors, mood, style. Keep it under 200 characters."
                ]
            )
            
            return response.text.strip()
        except Exception as e:
            print(f"Error describing image: {e}")
            return None

    def generate_video_script(self, prompt: str, duration: int, num_segments: int, user_images: list = None) -> dict:
        """
        Generates a structured script for the video using Gemini 2.0 Flash.
        Returns a JSON object with segments and shots.
        
        Veo 3.1 supports 4s, 6s, or 8s clips, so we'll generate 1-4 shots per 8s segment.
        Each shot will have its prompt enriched before generation.
        """
        import json
        
        # First, analyze user images if provided
        image_descriptions = []
        if user_images:
            for img_url in user_images[:3]:  # Max 3 images for Veo 3.1
                desc = self.describe_image_from_url(img_url)
                if desc:
                    image_descriptions.append(desc)
        
        system_instruction = """
        You are an expert video director. Create a detailed script for a video.
        The video is divided into 8-second segments (Veo 3.1 optimal duration).
        For EACH 8-second segment, you must define 1 to 4 distinct 'shots' (scenes).
        
        IMPORTANT: Veo 3.1 can only use up to 3 reference images total per video.
        If user images are provided, indicate which shots should use them.
        
        Output JSON format:
        {
            "segments": [
                {
                    "segment_index": 1,
                    "shots": [
                        {
                            "shot_index": 1,
                            "image_prompt": "Detailed visual description for image generation...",
                            "video_prompt": "Motion description for video generation including camera movements...",
                            "duration": 8,
                            "use_user_image_index": null
                        },
                        ...
                    ]
                },
                ...
            ]
        }
        
        Note: "use_user_image_index" should be 0, 1, or 2 if this shot should use a user-provided image, or null to generate a new image.
        """
        
        # Calculate segments based on 8s blocks
        num_8s_segments = (duration + 7) // 8
        
        user_content = f"""
        Create a video script.
        Topic/Prompt: {prompt}
        Total Duration: {duration} seconds
        Number of 8s Segments: {num_8s_segments}
        User Provided Images: {len(user_images) if user_images else 0}
        {f'Image descriptions: {image_descriptions}' if image_descriptions else ''}
        
        Create {num_8s_segments} segments with 1-4 shots each. Each shot should be 8 seconds for optimal Veo 3.1 quality.
        """
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json"
                )
            )
            
            script = json.loads(response.text)
            
            # Enrich all prompts in the script
            for segment in script.get("segments", []):
                segment_context = f"Segment {segment.get('segment_index', 1)} of {num_8s_segments}"
                for shot in segment.get("shots", []):
                    # Get user image description if applicable
                    user_img_desc = None
                    user_img_idx = shot.get("use_user_image_index")
                    if user_img_idx is not None and user_img_idx < len(image_descriptions):
                        user_img_desc = image_descriptions[user_img_idx]
                    
                    # Enrich both image and video prompts
                    if shot.get("image_prompt"):
                        shot["image_prompt"] = self.enrich_prompt(
                            shot["image_prompt"],
                            segment_context=segment_context,
                            user_image_description=user_img_desc
                        )
                    if shot.get("video_prompt"):
                        shot["video_prompt"] = self.enrich_prompt(
                            shot["video_prompt"],
                            segment_context=segment_context,
                            user_image_description=user_img_desc
                        )
            
            return script
            
        except Exception as e:
            print(f"Error generating script: {e}")
            return None
