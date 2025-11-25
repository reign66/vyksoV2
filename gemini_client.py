import os
import requests
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
        Uses gemini-2.5-flash-lite for fast text generation.
        
        Args:
            base_prompt: The original user prompt
            segment_context: Context about where this shot fits in the video (optional)
            user_image_description: Description of user-provided image if any (optional)
        
        Returns:
            Enriched prompt optimized for high-quality generation with TikTok Shorts aesthetic
        """
        # TikTok Shorts aesthetic suffix to always append
        tiktok_suffix = ", vertical 9:16 aspect ratio, TikTok Shorts aesthetic, high contrast vibrant colors, trending social media style, 4K quality"
        
        try:
            system_instruction = """
            You are an expert cinematographer and visual director specializing in TikTok and YouTube Shorts content.
            Your task is to enrich video/image generation prompts to produce stunning, viral-worthy content.
            
            Rules:
            1. Keep the original intent and subject matter intact
            2. Add specific cinematographic details (camera angles, movements, lighting)
            3. Include visual style descriptors (color grading, mood, atmosphere)
            4. Add technical quality markers (resolution, sharpness, professional grade)
            5. Make it suitable for AI video generation models
            6. If a user image is mentioned, incorporate it naturally into the scene
            7. Keep the prompt under 400 characters (TikTok aesthetic suffix will be added separately)
            8. Output ONLY the enriched prompt, nothing else
            9. Focus on dynamic, engaging visuals that grab attention in the first frame
            """
            
            user_content = f"""
            Original prompt: {base_prompt}
            {f'Segment context: {segment_context}' if segment_context else ''}
            {f'User provided image to incorporate: {user_image_description}' if user_image_description else ''}
            
            Enrich this prompt for viral TikTok/YouTube Shorts video generation.
            """
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                )
            )
            
            enriched = response.text.strip()
            # Add TikTok aesthetic suffix
            final_prompt = f"{enriched}{tiktok_suffix}"
            print(f"📝 Enriched prompt: {final_prompt[:100]}...")
            return final_prompt
            
        except Exception as e:
            print(f"Error enriching prompt: {e}, using original with TikTok suffix")
            return f"{base_prompt}{tiktok_suffix}"

    def describe_image_from_url(self, image_url: str) -> str:
        """
        Analyzes a user-provided image and returns a description for prompt enrichment.
        Uses gemini-2.5-flash-lite for fast text generation.
        """
        try:
            # Download the image
            response = httpx.get(image_url, timeout=30)
            image_bytes = response.content
            
            # Analyze with Gemini - use vision model
            image_part = types.Part.from_bytes(
                data=image_bytes,
                mime_type="image/png"
            )
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=[
                    image_part,
                    "Describe this image in detail for TikTok/Shorts video generation. Focus on: subjects, setting, colors, mood, style, key visual elements. Keep it under 200 characters."
                ]
            )
            
            return response.text.strip()
        except Exception as e:
            print(f"Error describing image: {e}")
            return None

    def generate_video_script(self, prompt: str, duration: int, num_segments: int, user_images: list = None, segment_duration: int = 8) -> dict:
        """
        Generates a structured script for the video using Gemini 2.5 Flash Lite.
        Returns a JSON object with segments and shots.
        Uses gemini-2.5-flash-lite for fast text generation.
        
        Args:
            prompt: The user's prompt for the video
            duration: Total video duration in seconds
            num_segments: Number of segments to generate
            user_images: Optional list of user-provided image URLs
            segment_duration: Duration per segment (8s for Veo 3.1, 10s for Sora)
        
        Returns:
            JSON object with segments and shots, each with enriched prompts
        """
        import json
        
        # First, analyze user images if provided (parallel would be ideal but keeping it simple)
        image_descriptions = []
        if user_images:
            for img_url in user_images[:3]:  # Max 3 images
                desc = self.describe_image_from_url(img_url)
                if desc:
                    image_descriptions.append(desc)
        
        system_instruction = f"""
        You are an expert TikTok/YouTube Shorts video director. Create a detailed script for a viral short-form video.
        The video is divided into {segment_duration}-second segments for optimal AI video generation.
        For EACH segment, you must define exactly 1 shot (scene) - keep it simple for best quality.
        
        IMPORTANT: 
        - Focus on creating visually STUNNING, attention-grabbing content
        - Each shot should tell a mini-story that hooks viewers immediately
        - Use dynamic camera movements and dramatic lighting descriptions
        - If user images are provided, use them strategically for the most impactful shots
        
        Output JSON format:
        {{
            "segments": [
                {{
                    "segment_index": 1,
                    "shots": [
                        {{
                            "shot_index": 1,
                            "image_prompt": "Detailed visual description for image generation focusing on composition, lighting, colors...",
                            "video_prompt": "Motion description for video generation including camera movements, subject actions, transitions...",
                            "duration": {segment_duration},
                            "use_user_image_index": null
                        }}
                    ]
                }}
            ]
        }}
        
        Note: "use_user_image_index" should be 0, 1, or 2 if this shot should use a user-provided image, or null to generate a new image.
        """
        
        user_content = f"""
        Create a TikTok/YouTube Shorts video script.
        Topic/Prompt: {prompt}
        Total Duration: {duration} seconds
        Number of Segments: {num_segments}
        Segment Duration: {segment_duration} seconds each
        User Provided Images: {len(user_images) if user_images else 0}
        {f'Image descriptions: {image_descriptions}' if image_descriptions else ''}
        
        Create {num_segments} segments with 1 shot each. Focus on viral TikTok/Shorts aesthetics: bold colors, dynamic movements, attention-grabbing visuals.
        """
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json"
                )
            )
            
            script = json.loads(response.text)
            
            print(f"📜 Script generated with {len(script.get('segments', []))} segments")
            
            # Enrich all prompts in the script (parallel enrichment for speed)
            for segment in script.get("segments", []):
                segment_context = f"Segment {segment.get('segment_index', 1)} of {num_segments}"
                for shot in segment.get("shots", []):
                    # Get user image description if applicable
                    user_img_desc = None
                    user_img_idx = shot.get("use_user_image_index")
                    if user_img_idx is not None and user_img_idx < len(image_descriptions):
                        user_img_desc = image_descriptions[user_img_idx]
                    
                    # Enrich both image and video prompts with TikTok aesthetic
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

    def generate_thumbnail(self, title: str, description: str, original_prompt: str) -> tuple:
        """
        Generates a YouTube Shorts thumbnail image using Imagen 4.0.
        Optimized for vertical 9:16 format with reserved zones for text overlay.
        
        Args:
            title: The video title (ideally clickbait)
            description: The video description
            original_prompt: The original user prompt for the video
            
        Returns:
            Tuple of (image_bytes, thumbnail_path) or (None, None) if generation fails
        """
        import os
        
        try:
            # Create an optimized prompt for YouTube Shorts thumbnail generation
            thumbnail_prompt = self._generate_thumbnail_prompt(title, description, original_prompt)
            
            print(f"🖼️ Generating YouTube Shorts thumbnail with Imagen 4.0...")
            print(f"📝 Thumbnail prompt: {thumbnail_prompt[:300]}...")
            
            # Call Imagen 4.0 API via Google GenAI
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-generate-001:predict"
            
            headers = {
                "Content-Type": "application/json",
            }
            
            # Configuration optimisée pour YouTube Shorts (VERTICAL 9:16)
            payload = {
                "instances": [{"prompt": thumbnail_prompt}],
                "parameters": {
                    "sampleCount": 1,
                    "aspectRatio": "9:16",  # VERTICAL pour YouTube Shorts
                    "personGeneration": "allow_adult"
                }
            }
            
            response = requests.post(
                f"{endpoint}?key={self.api_key}",
                headers=headers,
                json=payload,
                timeout=60
            )
            
            image_bytes = None
            
            if response.status_code == 200:
                result = response.json()
                # Extract base64 image from predictions
                if "predictions" in result and len(result["predictions"]) > 0:
                    prediction = result["predictions"][0]
                    if "bytesBase64Encoded" in prediction:
                        image_bytes = base64.b64decode(prediction["bytesBase64Encoded"])
                        print("✅ Thumbnail generated successfully with Imagen 4.0")
            
            # Fallback to gemini-3-pro-image-preview if Imagen fails
            if not image_bytes:
                print(f"⚠️ Imagen 4.0 failed (status: {response.status_code}), trying gemini-3-pro-image-preview...")
                image_bytes = self._generate_thumbnail_fallback(thumbnail_prompt)
            
            # Save thumbnail to /tmp/thumbnails/
            thumbnail_path = None
            if image_bytes:
                thumbnail_path = self._save_thumbnail(image_bytes)
            
            return image_bytes, thumbnail_path
            
        except Exception as e:
            print(f"❌ Error generating thumbnail with Imagen: {e}")
            # Try fallback
            try:
                image_bytes = self._generate_thumbnail_fallback(thumbnail_prompt)
                if image_bytes:
                    thumbnail_path = self._save_thumbnail(image_bytes)
                    return image_bytes, thumbnail_path
            except Exception as fallback_error:
                print(f"❌ Fallback thumbnail generation also failed: {fallback_error}")
            return None, None
    
    def _extract_keywords(self, title: str, description: str, original_prompt: str) -> dict:
        """
        Extrait les mots-clés pertinents pour enrichir le prompt Imagen.
        Utilise Gemini 2.5 Flash Lite pour analyser intelligemment le contenu.
        """
        keywords = {
            'main_subject': '',
            'style': 'cinematic dramatic',
            'mood': 'energetic and engaging',
            'lighting': 'dramatic professional'
        }
        
        try:
            # Utiliser Gemini 2.5 Flash Lite pour extraire les mots-clés de manière intelligente
            system_instruction = """
            You are an expert at analyzing video content for thumbnail creation.
            Extract key visual elements from the title and prompt.
            
            Output ONLY a JSON object with these exact keys:
            - main_subject: Detailed visual description of the main subject (e.g., "orange cat wearing tiny suit playing grand piano")
            - style: Visual style descriptor (e.g., "cinematic dramatic", "vibrant colorful", "dark mysterious")
            - mood: Emotional mood (e.g., "surprising and entertaining", "inspiring and motivational")
            - lighting: Lighting description (e.g., "dramatic spotlight from above", "warm golden hour")
            
            Be specific and visually descriptive. Focus on what would look AMAZING in a thumbnail.
            """
            
            user_content = f"""
            Title: {title}
            Description: {description}
            Original Prompt: {original_prompt}
            
            Extract keywords for a viral YouTube Shorts thumbnail.
            """
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json"
                )
            )
            
            import json
            extracted = json.loads(response.text)
            
            if extracted.get('main_subject'):
                keywords['main_subject'] = extracted['main_subject']
            if extracted.get('style'):
                keywords['style'] = extracted['style']
            if extracted.get('mood'):
                keywords['mood'] = extracted['mood']
            if extracted.get('lighting'):
                keywords['lighting'] = extracted['lighting']
                
        except Exception as e:
            print(f"⚠️ Error extracting keywords with Gemini: {e}")
            # Fallback: analyse basique du texte
            combined_text = f"{title} {description} {original_prompt}".lower()
            
            # Détection de thèmes communs
            if any(word in combined_text for word in ['chat', 'cat', 'kitten', 'chaton']):
                keywords['main_subject'] = 'adorable cat with expressive face'
            elif any(word in combined_text for word in ['argent', 'money', 'euro', 'économ', 'save', 'budget']):
                keywords['main_subject'] = 'pile of money bills and coins, golden piggy bank'
            elif any(word in combined_text for word in ['cuisine', 'recette', 'food', 'cook', 'recipe']):
                keywords['main_subject'] = 'delicious gourmet food presentation, steam rising'
            elif any(word in combined_text for word in ['fitness', 'sport', 'workout', 'muscle']):
                keywords['main_subject'] = 'athletic person in dynamic pose, muscular definition'
            elif any(word in combined_text for word in ['tech', 'phone', 'gadget', 'ai', 'robot']):
                keywords['main_subject'] = 'futuristic technology device with glowing elements'
            else:
                keywords['main_subject'] = 'dramatic scene with strong visual impact'
        
        return keywords
    
    def _generate_thumbnail_prompt(self, title: str, description: str, original_prompt: str) -> str:
        """
        Génère un prompt optimisé pour Imagen qui crée un thumbnail YouTube Shorts.
        
        Structure du thumbnail :
        - Top 20-30% : Zone vide pour titre putaclic
        - Middle 40-50% : Contenu visuel principal
        - Bottom 20-30% : Zone vide pour CTA/emoji
        """
        # Extrait les éléments clés
        keywords = self._extract_keywords(title, description, original_prompt)
        
        # Construit le prompt Imagen optimisé pour YouTube Shorts
        imagen_prompt = f"""Vertical 9:16 aspect ratio thumbnail for YouTube Shorts.

Visual content (center 40-50%): {keywords['main_subject']} with {keywords['style']} aesthetic.

Layout requirements:
- Top 20-30% must be EMPTY SPACE (solid dark color or subtle gradient) for text overlay
- Center 40-50% contains the main visual subject with dramatic lighting and high contrast
- Bottom 20-30% must be EMPTY SPACE (matching dark gradient) for call-to-action text
- High saturation vibrant colors optimized for mobile viewing
- Trending TikTok/YouTube Shorts aesthetic
- Professional photography quality, 4K sharp details
- Clear focal point in center area
- {keywords['mood']} mood with {keywords['lighting']} lighting

Style: Cinematic, eye-catching, clickbait thumbnail style, designed for maximum engagement on social media."""

        return imagen_prompt
    
    def _save_thumbnail(self, image_bytes: bytes) -> str:
        """
        Sauvegarde le thumbnail dans /tmp/thumbnails/ et retourne le chemin.
        """
        import os
        import uuid
        
        # Créer le dossier si nécessaire
        thumbnails_dir = "/tmp/thumbnails"
        os.makedirs(thumbnails_dir, exist_ok=True)
        
        # Générer un nom unique
        filename = f"thumbnail_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join(thumbnails_dir, filename)
        
        # Sauvegarder l'image
        with open(filepath, "wb") as f:
            f.write(image_bytes)
        
        print(f"💾 Thumbnail saved to: {filepath}")
        return filepath
    
    def _generate_thumbnail_fallback(self, prompt: str) -> bytes:
        """
        Fallback thumbnail generation using gemini-3-pro-image-preview.
        """
        try:
            response = self.client.models.generate_content(
                model='gemini-3-pro-image-preview',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=['IMAGE']
                )
            )
            
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'inline_data') and part.inline_data:
                        print("✅ Thumbnail generated with fallback model")
                        return base64.b64decode(part.inline_data.data)
            return None
        except Exception as e:
            print(f"Error in fallback thumbnail generation: {e}")
            return None
