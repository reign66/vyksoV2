import os
import requests
from google import genai
from google.genai import types
import base64
import httpx
from typing import Optional, List, Literal
from PIL import Image
from io import BytesIO

# User tier types for differentiated prompts
UserTier = Literal["creator", "professional"]

class GeminiClient:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")
        self.client = genai.Client(api_key=self.api_key)
        # Store active chat sessions for multi-turn image editing
        self._chat_sessions = {}

    def generate_image(
        self, 
        prompt: str, 
        reference_images: Optional[List[Image.Image]] = None,
        aspect_ratio: str = "9:16",
        resolution: str = "2K",
        use_google_search: bool = False
    ) -> bytes:
        """
        Generates an image using Gemini 3 Pro Image Preview model.
        
        Args:
            prompt: Text description of the image to generate
            reference_images: Optional list of PIL Images (up to 18) for reference
            aspect_ratio: Image aspect ratio ("1:1","2:3","3:2","3:4","4:3","4:5","5:4","9:16","16:9","21:9")
            resolution: Image resolution ("1K", "2K", "4K")
            use_google_search: Whether to use Google Search for grounding (real-time data)
        
        Returns:
            Image bytes or None if generation fails
        """
        try:
            # Build contents - can include multiple reference images (up to 18)
            contents = [prompt]
            
            if reference_images:
                # Gemini 3 Pro supports up to 14-18 reference images
                for img in reference_images[:18]:
                    if isinstance(img, Image.Image):
                        contents.append(img)
            
            # Build config with image settings
            config_kwargs = {
                "response_modalities": ['TEXT', 'IMAGE'],  # Must include both per docs
                "image_config": types.ImageConfig(
                    aspect_ratio=aspect_ratio,
                    image_size=resolution
                )
            }
            
            # Add Google Search tool if requested (for real-time data grounding)
            if use_google_search:
                config_kwargs["tools"] = [{"google_search": {}}]
            
            response = self.client.models.generate_content(
                model='gemini-3-pro-image-preview',
                contents=contents,
                config=types.GenerateContentConfig(**config_kwargs)
            )
            
            # Extract image bytes from the response (skip thought images)
            for part in response.parts:
                # Skip thought parts (intermediate images)
                if hasattr(part, 'thought') and part.thought:
                    continue
                # Check for image data
                if hasattr(part, 'inline_data') and part.inline_data:
                    if part.inline_data.mime_type and 'image' in part.inline_data.mime_type:
                        return base64.b64decode(part.inline_data.data)
                # Alternative: use as_image() helper
                try:
                    image = part.as_image()
                    if image:
                        # Convert PIL Image to bytes
                        buffer = BytesIO()
                        image.save(buffer, format='PNG')
                        return buffer.getvalue()
                except:
                    pass
            
            # Fallback: check candidates structure
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'thought') and part.thought:
                        continue
                    if hasattr(part, 'inline_data') and part.inline_data:
                        return base64.b64decode(part.inline_data.data)
            
            print("⚠️ No image found in Gemini response")
            return None
            
        except Exception as e:
            print(f"Error generating image with gemini-3-pro-image-preview: {e}")
            raise e

    def create_image_chat(self, session_id: str, use_google_search: bool = False):
        """
        Creates a multi-turn chat session for iterative image generation/editing.
        
        Args:
            session_id: Unique identifier for this chat session
            use_google_search: Whether to enable Google Search grounding
        
        Returns:
            The chat session object
        """
        config_kwargs = {
            "response_modalities": ['TEXT', 'IMAGE'],
        }
        
        if use_google_search:
            config_kwargs["tools"] = [{"google_search": {}}]
        
        chat = self.client.chats.create(
            model="gemini-3-pro-image-preview",
            config=types.GenerateContentConfig(**config_kwargs)
        )
        
        self._chat_sessions[session_id] = chat
        return chat

    def chat_generate_image(
        self,
        session_id: str,
        message: str,
        aspect_ratio: str = "9:16",
        resolution: str = "2K"
    ) -> bytes:
        """
        Sends a message in an existing chat session to generate/edit images.
        This allows iterative modifications like "Update this to Spanish" etc.
        
        Args:
            session_id: The chat session ID
            message: The instruction/prompt for this turn
            aspect_ratio: Desired aspect ratio for the output
            resolution: Desired resolution ("1K", "2K", "4K")
        
        Returns:
            Image bytes or None
        """
        chat = self._chat_sessions.get(session_id)
        if not chat:
            chat = self.create_image_chat(session_id)
        
        try:
            response = chat.send_message(
                message,
                config=types.GenerateContentConfig(
                    image_config=types.ImageConfig(
                        aspect_ratio=aspect_ratio,
                        image_size=resolution
                    ),
                )
            )
            
            # Extract image from response
            for part in response.parts:
                if hasattr(part, 'thought') and part.thought:
                    continue
                try:
                    image = part.as_image()
                    if image:
                        buffer = BytesIO()
                        image.save(buffer, format='PNG')
                        return buffer.getvalue()
                except:
                    pass
                if hasattr(part, 'inline_data') and part.inline_data:
                    return base64.b64decode(part.inline_data.data)
            
            return None
            
        except Exception as e:
            print(f"Error in chat image generation: {e}")
            raise e

    def close_chat(self, session_id: str):
        """Closes and removes a chat session."""
        if session_id in self._chat_sessions:
            del self._chat_sessions[session_id]

    def enrich_prompt(
        self, 
        base_prompt: str, 
        segment_context: str = None, 
        user_image_description: str = None,
        user_tier: UserTier = "creator"
    ) -> str:
        """
        Enriches a client prompt before image/video generation for higher quality output.
        This adds cinematographic details, visual style, and technical specifications.
        Uses gemini-2.0-flash-lite for fast text generation.
        
        Args:
            base_prompt: The original user prompt
            segment_context: Context about where this shot fits in the video (optional)
            user_image_description: Description of user-provided image if any (optional)
            user_tier: "creator" for TikTok/Shorts content, "professional" for ads
        
        Returns:
            Enriched prompt optimized for high-quality generation
        """
        if user_tier == "creator":
            return self._enrich_prompt_creator(base_prompt, segment_context, user_image_description)
        else:
            return self._enrich_prompt_professional(base_prompt, segment_context, user_image_description)

    def _enrich_prompt_creator(self, base_prompt: str, segment_context: str = None, user_image_description: str = None) -> str:
        """
        Enriches prompt for CREATOR tier - optimized for TikTok/YouTube Shorts.
        Focus on viral content, attention-grabbing visuals, trendy aesthetics.
        """
        # TikTok Shorts aesthetic suffix
        creator_suffix = ", vertical 9:16 aspect ratio, TikTok Shorts aesthetic, high contrast vibrant colors, trending social media style, viral potential, 4K quality, hook in first 3 seconds"
        
        try:
            system_instruction = """
            You are an expert TikTok/YouTube Shorts content creator and viral video specialist.
            Your task is to enrich video/image generation prompts to produce VIRAL, engaging short-form content.
            
            CREATOR STYLE RULES:
            1. Keep the original intent but make it MORE EXCITING and attention-grabbing
            2. Add dynamic camera movements (quick zooms, sweeping shots, dramatic reveals)
            3. Use bold, saturated colors that POP on mobile screens
            4. Include trendy visual effects (glitch effects, speed ramps, transitions)
            5. Create INSTANT HOOKS - the first frame must grab attention
            6. Use high energy, fast-paced visual storytelling
            7. Incorporate current social media trends and aesthetics
            8. If a user image is mentioned, make it the star of a viral moment
            9. Keep the prompt under 400 characters
            10. Output ONLY the enriched prompt, nothing else
            
            VIRAL ELEMENTS TO INCLUDE:
            - Dramatic lighting changes
            - Unexpected visual twists
            - Satisfying visual moments
            - Relatable/shareable content hooks
            - Mobile-optimized composition (centered subjects)
            """
            
            user_content = f"""
            Original prompt: {base_prompt}
            {f'Scene context: {segment_context}' if segment_context else ''}
            {f'User provided image to feature: {user_image_description}' if user_image_description else ''}
            
            Transform this into a VIRAL TikTok/YouTube Shorts video prompt. Make it irresistible to scroll past!
            """
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                )
            )
            
            enriched = response.text.strip()
            final_prompt = f"{enriched}{creator_suffix}"
            print(f"📝 [CREATOR] Enriched prompt: {final_prompt[:100]}...")
            return final_prompt
            
        except Exception as e:
            print(f"Error enriching creator prompt: {e}, using original with suffix")
            return f"{base_prompt}{creator_suffix}"

    def _enrich_prompt_professional(self, base_prompt: str, segment_context: str = None, user_image_description: str = None) -> str:
        """
        Enriches prompt for PROFESSIONAL tier - optimized for ads, commercials, brand content.
        Focus on polished, high-end production quality, brand-safe, conversion-focused.
        """
        # Professional ad aesthetic suffix
        professional_suffix = ", cinematic 9:16 vertical format, premium advertising quality, professional color grading, brand-safe content, high-end production value, 4K HDR quality, commercial grade"
        
        try:
            system_instruction = """
            You are an elite advertising director and commercial cinematographer.
            Your task is to enrich video/image generation prompts for PROFESSIONAL ADVERTISING content.
            
            PROFESSIONAL AD STYLE RULES:
            1. Maintain brand-safe, polished, premium aesthetics
            2. Use sophisticated camera work (smooth tracking shots, elegant reveals, product showcases)
            3. Apply refined, professional color grading (not oversaturated - elegant and clean)
            4. Create aspirational, lifestyle-driven narratives
            5. Focus on product/service benefits and emotional connection
            6. Use professional lighting setups (3-point lighting, soft fills, dramatic key lights)
            7. Include subtle but effective call-to-action moments
            8. If a user image is mentioned, integrate it as a premium product/brand showcase
            9. Keep the prompt under 400 characters
            10. Output ONLY the enriched prompt, nothing else
            
            ADVERTISING ELEMENTS TO INCLUDE:
            - Clean, uncluttered compositions
            - Professional model/product positioning
            - Aspirational lifestyle imagery
            - Trust-building visual elements
            - Conversion-focused storytelling arcs
            - Multi-sequence narrative potential (for longer ads)
            """
            
            user_content = f"""
            Original prompt: {base_prompt}
            {f'Sequence context: {segment_context}' if segment_context else ''}
            {f'Brand/product image to feature: {user_image_description}' if user_image_description else ''}
            
            Transform this into a PROFESSIONAL ADVERTISING video prompt. Premium quality, conversion-focused, brand-safe.
            """
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                )
            )
            
            enriched = response.text.strip()
            final_prompt = f"{enriched}{professional_suffix}"
            print(f"📝 [PROFESSIONAL] Enriched prompt: {final_prompt[:100]}...")
            return final_prompt
            
        except Exception as e:
            print(f"Error enriching professional prompt: {e}, using original with suffix")
            return f"{base_prompt}{professional_suffix}"

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

    def generate_video_script(
        self, 
        prompt: str, 
        duration: int, 
        num_segments: int, 
        user_images: list = None, 
        segment_duration: int = 8,
        user_tier: UserTier = "creator",
        images_per_segment: int = 1
    ) -> dict:
        """
        Generates a structured script for the video using Gemini 2.0 Flash Lite.
        Returns a JSON object with segments and shots.
        
        Args:
            prompt: The user's prompt for the video
            duration: Total video duration in seconds
            num_segments: Number of segments to generate
            user_images: Optional list of user-provided image URLs (up to 18)
            segment_duration: Duration per segment (8s for Veo 3.1, 10s for Sora)
            user_tier: "creator" for TikTok/Shorts, "professional" for ads
            images_per_segment: Number of images to generate per segment (1-3 for creator, more for professional)
        
        Returns:
            JSON object with segments and shots, each with enriched prompts
        """
        import json
        
        # Analyze user images if provided (now supports up to 18 images)
        image_descriptions = []
        if user_images:
            for img_url in user_images[:18]:  # Support up to 18 images
                desc = self.describe_image_from_url(img_url)
                if desc:
                    image_descriptions.append(desc)
        
        # Choose system instruction based on user tier
        if user_tier == "creator":
            system_instruction = self._get_creator_script_instruction(segment_duration, len(user_images) if user_images else 0)
        else:
            system_instruction = self._get_professional_script_instruction(segment_duration, len(user_images) if user_images else 0)
        
        user_content = f"""
        Create a video script.
        Topic/Prompt: {prompt}
        Total Duration: {duration} seconds
        Number of Segments: {num_segments}
        Segment Duration: {segment_duration} seconds each
        User Provided Images: {len(user_images) if user_images else 0}
        Images Per Segment: {images_per_segment}
        {f'Image descriptions: {image_descriptions}' if image_descriptions else ''}
        
        Create {num_segments} segments. {"Make it viral-worthy!" if user_tier == "creator" else "Make it premium advertising quality."}
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
            
            print(f"📜 Script generated with {len(script.get('segments', []))} segments for {user_tier.upper()} tier")
            
            # Enrich all prompts in the script with tier-specific enrichment
            for segment in script.get("segments", []):
                segment_context = f"Segment {segment.get('segment_index', 1)} of {num_segments}"
                for shot in segment.get("shots", []):
                    # Get user image description if applicable
                    user_img_desc = None
                    user_img_idx = shot.get("use_user_image_index")
                    if user_img_idx is not None and user_img_idx < len(image_descriptions):
                        user_img_desc = image_descriptions[user_img_idx]
                    
                    # Enrich both image and video prompts with tier-specific style
                    if shot.get("image_prompt"):
                        shot["image_prompt"] = self.enrich_prompt(
                            shot["image_prompt"],
                            segment_context=segment_context,
                            user_image_description=user_img_desc,
                            user_tier=user_tier
                        )
                    if shot.get("video_prompt"):
                        shot["video_prompt"] = self.enrich_prompt(
                            shot["video_prompt"],
                            segment_context=segment_context,
                            user_image_description=user_img_desc,
                            user_tier=user_tier
                        )
            
            return script
            
        except Exception as e:
            print(f"Error generating script: {e}")
            return None

    def _get_creator_script_instruction(self, segment_duration: int, num_user_images: int) -> str:
        """Returns system instruction for CREATOR tier video scripts (TikTok/Shorts)."""
        return f"""
        You are an expert TikTok/YouTube Shorts video director specializing in VIRAL content.
        Create a script optimized for short-form social media that will get maximum engagement.
        
        VIDEO STRUCTURE:
        - Each segment is {segment_duration} seconds
        - For CREATOR tier: Keep it SIMPLE - 1 main shot per segment for scene changes
        - Generate 1-3 images per segment to create visual variety within the scene
        - User has provided {num_user_images} reference images that can be used
        
        CREATOR STYLE REQUIREMENTS:
        - VIRAL HOOKS: First 3 seconds must be impossibly attention-grabbing
        - FAST PACING: Quick cuts, dynamic transitions, never boring
        - BOLD VISUALS: Saturated colors, high contrast, mobile-optimized
        - TRENDY: Use current TikTok trends, challenges, aesthetics
        - EMOTIONAL: Create surprise, awe, humor, or curiosity
        - VERTICAL: Everything composed for 9:16 mobile viewing
        
        Output JSON format:
        {{
            "segments": [
                {{
                    "segment_index": 1,
                    "shots": [
                        {{
                            "shot_index": 1,
                            "image_prompt": "Detailed visual for the main scene...",
                            "video_prompt": "Dynamic motion and action description...",
                            "duration": {segment_duration},
                            "use_user_image_index": null,
                            "scene_images": ["variation 1 prompt", "variation 2 prompt"]
                        }}
                    ]
                }}
            ]
        }}
        
        Note: "use_user_image_index" can be 0-{num_user_images - 1 if num_user_images > 0 else 0} to use a user image, or null to generate.
        "scene_images" contains 1-3 additional image prompts for scene variety (scene changes within the segment).
        """

    def _get_professional_script_instruction(self, segment_duration: int, num_user_images: int) -> str:
        """Returns system instruction for PROFESSIONAL tier video scripts (ads)."""
        return f"""
        You are an elite advertising director creating a PROFESSIONAL commercial video.
        Create a script optimized for conversion, brand building, and premium production quality.
        
        VIDEO STRUCTURE:
        - Each segment is {segment_duration} seconds
        - For PROFESSIONAL tier: Multiple sequences with narrative arc
        - Multiple shots per segment for complex storytelling
        - User has provided {num_user_images} brand/product images that should be featured
        
        PROFESSIONAL AD REQUIREMENTS:
        - NARRATIVE ARC: Problem → Solution → Benefit → CTA flow
        - PREMIUM QUALITY: Cinematic lighting, elegant composition, refined colors
        - BRAND SAFE: Professional, trustworthy, aspirational imagery
        - PRODUCT FOCUS: Clear product/service showcase moments
        - CONVERSION: Build desire and urgency, clear value proposition
        - MULTI-SEQUENCE: Create coherent story across segments
        
        Output JSON format:
        {{
            "segments": [
                {{
                    "segment_index": 1,
                    "narrative_beat": "introduction/problem/solution/benefit/cta",
                    "shots": [
                        {{
                            "shot_index": 1,
                            "image_prompt": "Premium visual composition description...",
                            "video_prompt": "Sophisticated camera movement and action...",
                            "duration": {segment_duration},
                            "use_user_image_index": null,
                            "scene_images": ["angle 1", "angle 2", "detail shot"]
                        }}
                    ]
                }}
            ]
        }}
        
        Note: "use_user_image_index" can be 0-{num_user_images - 1 if num_user_images > 0 else 0} to feature a brand image, or null to generate.
        "scene_images" contains multiple image prompts for comprehensive product/brand coverage.
        "narrative_beat" describes where this segment fits in the ad's story arc.
        """

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
        Uses proper API format with TEXT + IMAGE modalities and image config.
        """
        try:
            response = self.client.models.generate_content(
                model='gemini-3-pro-image-preview',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=['TEXT', 'IMAGE'],
                    image_config=types.ImageConfig(
                        aspect_ratio="9:16",
                        image_size="2K"
                    )
                )
            )
            
            # Extract image from response (skip thought images)
            for part in response.parts:
                if hasattr(part, 'thought') and part.thought:
                    continue
                try:
                    image = part.as_image()
                    if image:
                        buffer = BytesIO()
                        image.save(buffer, format='PNG')
                        print("✅ Thumbnail generated with fallback model")
                        return buffer.getvalue()
                except:
                    pass
                if hasattr(part, 'inline_data') and part.inline_data:
                    print("✅ Thumbnail generated with fallback model")
                    return base64.b64decode(part.inline_data.data)
            
            # Fallback check candidates structure
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'thought') and part.thought:
                        continue
                    if hasattr(part, 'inline_data') and part.inline_data:
                        print("✅ Thumbnail generated with fallback model")
                        return base64.b64decode(part.inline_data.data)
            return None
        except Exception as e:
            print(f"Error in fallback thumbnail generation: {e}")
            return None
