import os
import json
import uuid
import stripe
import httpx
from fastapi.responses import StreamingResponse
from typing import Optional, List, Dict, Literal
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, field_validator
from sora_client import SoraClient
from veo_client import VeoAIClient
from supabase_client import get_client
from utils.supabase_uploader import SupabaseVideoUploader
from utils.video_concat import VideoEditor
from utils.content_generator import ContentGenerator, ScheduleCalculator
from gemini_client import GeminiClient
from youtube_client import YouTubeClient
from io import BytesIO
from starlette.requests import Request as StarletteRequest
from starlette.responses import StreamingResponse as StarletteStreamingResponse
from urllib.parse import urlparse

# Import new Stripe configuration and routes
from config.stripe_config import get_stripe_config, get_plan_type
from routes.checkout import router as checkout_router
from routes.webhook import router as webhook_router
from services.supabase_service import (
    update_user_subscription,
    add_credits_to_user,
    get_user_by_stripe_subscription,
)

app = FastAPI(
    title="Vykso API",
    description="API de génération vidéo automatique via Sora 2",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://vykso.com",
        "https://vykso.lovable.app",
        "https://www.vykso.com",
        os.getenv("FRONTEND_URL", ""),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Stripe routes
# IMPORTANT: Webhook route must be included to receive raw body for signature verification
app.include_router(checkout_router)
app.include_router(webhook_router)

# Clients - Lazy initialization to prevent startup crashes
# These will be initialized on first use, allowing the server to start
# even if some API keys are not configured

_sora = None
_veo = None
_supabase = None
_uploader = None
_video_editor = None
_gemini_client = None
_youtube_client = None
_content_generator = None
_schedule_calculator = None

def get_sora():
    global _sora
    if _sora is None:
        _sora = SoraClient()
    return _sora

def get_veo():
    global _veo
    if _veo is None:
        _veo = VeoAIClient()
    return _veo

def get_supabase():
    global _supabase
    if _supabase is None:
        _supabase = get_client()
    return _supabase

def get_uploader():
    global _uploader
    if _uploader is None:
        _uploader = SupabaseVideoUploader()
    return _uploader

def get_video_editor():
    global _video_editor
    if _video_editor is None:
        _video_editor = VideoEditor()
    return _video_editor

def get_gemini():
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = GeminiClient()
    return _gemini_client

def get_youtube():
    global _youtube_client
    if _youtube_client is None:
        _youtube_client = YouTubeClient()
    return _youtube_client

def get_content_generator():
    global _content_generator
    if _content_generator is None:
        _content_generator = ContentGenerator(gemini_client=get_gemini())
    return _content_generator

def get_schedule_calculator():
    global _schedule_calculator
    if _schedule_calculator is None:
        _schedule_calculator = ScheduleCalculator()
    return _schedule_calculator

# Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# ========= VIDEO STREAMING/PROXY HELPERS =========
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
VIDEOS_BUCKET = os.getenv("VIDEOS_BUCKET", "vykso-videos")
SUPABASE_ANON_OR_SERVICE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

async def _get_authenticated_user_id(request: Request) -> str:
    """Validate Supabase JWT from Authorization header and return user id (sub).

    This calls Supabase Auth `/auth/v1/user` which verifies the Bearer JWT.
    Requires SUPABASE_URL and an API key (anon or service) in env.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    jwt_token = auth_header[len("Bearer "):].strip()

    if not SUPABASE_URL or not SUPABASE_ANON_OR_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase auth not configured")

    auth_user_url = f"{SUPABASE_URL}/auth/v1/user"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            auth_user_url,
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "apikey": SUPABASE_ANON_OR_SERVICE_KEY,
            },
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    try:
        data = resp.json()
        user_id = data.get("id") or data.get("sub")
    except Exception:
        user_id = None
    if not user_id:
        raise HTTPException(status_code=401, detail="Unable to resolve user from token")
    return user_id

def _extract_object_path_from_public_url(public_url: str, bucket: str) -> Optional[str]:
    """Extract the storage object path (filename) from a Supabase public URL.
    Supports URLs like .../storage/v1/object/public/{bucket}/{path}.
    """
    try:
        parts = public_url.split("/storage/v1/object/")
        if len(parts) < 2:
            return None
        tail = parts[1]
        # remove leading 'public/' if present
        if tail.startswith("public/"):
            tail = tail[len("public/"):]
        # tail is now like '{bucket}/{path}'
        if not tail.startswith(f"{bucket}/"):
            return None
        return tail[len(bucket) + 1 :]
    except Exception:
        return None

async def _proxy_supabase_object_stream(object_path: str, range_header: Optional[str]):
    """Stream a Supabase Storage object with Range support using the service key.
    This avoids exposing external URLs and works with private buckets.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase configuration missing")

    # Build direct storage endpoint (non-public) so auth works for private buckets
    object_url = f"{SUPABASE_URL}/storage/v1/object/{VIDEOS_BUCKET}/{object_path}"

    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Accept": "application/octet-stream",
    }
    if range_header:
        headers["Range"] = range_header

    async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
        upstream = await client.get(object_url, headers=headers)
        # 200 or 206 expected; propagate errors
        if upstream.status_code >= 400:
            raise HTTPException(status_code=upstream.status_code, detail="Unable to fetch video content")

        # Prepare headers to forward
        forward_headers = {}
        for h in [
            "Content-Type",
            "Content-Length",
            "Content-Range",
            "Accept-Ranges",
            "ETag",
            "Last-Modified",
            "Cache-Control",
        ]:
            v = upstream.headers.get(h)
            if v:
                forward_headers[h] = v

        status = upstream.status_code  # 200 or 206 for ranges

        async def body_iter():
            async for chunk in upstream.aiter_bytes(chunk_size=1024 * 256):
                yield chunk

        return StarletteStreamingResponse(body_iter(), status_code=status, headers=forward_headers, media_type="video/mp4")

# ============= MODELS =============

# AI Model name normalization - accepts various formats from frontend
AI_MODEL_ALIASES = {
    # Veo 3.1 normal
    "veo-3.1-generate-preview": "veo-3.1-generate-preview",
    "veo-3.1": "veo-3.1-generate-preview",
    "veo3.1": "veo-3.1-generate-preview",
    "veo 3.1": "veo-3.1-generate-preview",
    "veo": "veo-3.1-generate-preview",
    "veo-3": "veo-3.1-generate-preview",
    "veo3": "veo-3.1-generate-preview",
    # Veo 3.1 fast (all variations)
    "veo-3.1-fast-generate-preview": "veo-3.1-fast-generate-preview",
    "veo-3.1-fast": "veo-3.1-fast-generate-preview",
    "veo3.1-fast": "veo-3.1-fast-generate-preview",
    "veo3.1 fast": "veo-3.1-fast-generate-preview",
    "veo3.1fast": "veo-3.1-fast-generate-preview",
    "veo 3.1 fast": "veo-3.1-fast-generate-preview",
    "veo-fast": "veo-3.1-fast-generate-preview",
    "veo fast": "veo-3.1-fast-generate-preview",
    "veofast": "veo-3.1-fast-generate-preview",
    "veo-3-fast": "veo-3.1-fast-generate-preview",
    "veo3-fast": "veo-3.1-fast-generate-preview",
    "veo3fast": "veo-3.1-fast-generate-preview",
    # Sora 2
    "sora-2": "sora-2",
    "sora2": "sora-2",
    "sora 2": "sora-2",
    "sora": "sora-2",
    # Sora 2 Pro
    "sora-2-pro": "sora-2-pro",
    "sora2-pro": "sora-2-pro",
    "sora2pro": "sora-2-pro",
    "sora 2 pro": "sora-2-pro",
    "sora-pro": "sora-2-pro",
    "sora pro": "sora-2-pro",
    "sorapro": "sora-2-pro",
}

VALID_AI_MODELS = ["sora-2", "sora-2-pro", "veo-3.1-generate-preview", "veo-3.1-fast-generate-preview"]

def normalize_ai_model(value: str) -> str:
    """Normalize AI model name to the expected format."""
    if not value:
        return "veo-3.1-generate-preview"
    
    # Lowercase and strip for matching
    normalized = value.lower().strip()
    
    # Check aliases
    if normalized in AI_MODEL_ALIASES:
        return AI_MODEL_ALIASES[normalized]
    
    # Check if it's already a valid model
    if normalized in VALID_AI_MODELS:
        return normalized
    
    # Default fallback
    print(f"⚠️ Unknown ai_model '{value}', defaulting to veo-3.1-generate-preview")
    return "veo-3.1-generate-preview"


# ============= USER TIER SYSTEM =============
# IMPORTANT: Logic based on database "plan" field
#
# CREATOR plans (9:16 vertical, TikTok/Shorts optimized):
#   - starter, premium, pro, max (and their yearly variants)
#   - creator_basic, creator_pro, creator_max (legacy naming)
#   - free
#
# PROFESSIONAL plans (16:9 horizontal, ads/commercials optimized):
#   - premium_pro, pro_pro, max_pro (plans with "_pro" suffix)
#   - starter_pro (if exists)

# Professional plans use "_pro" suffix (NOT to be confused with the "pro" plan which is Creator)
PROFESSIONAL_PLANS = ["premium_pro", "pro_pro", "max_pro", "starter_pro"]

# All other plans are Creator tier
CREATOR_PLANS = [
    "free", "starter", "premium", "pro", "max",  # Base plans = Creator
    "starter_yearly", "premium_yearly", "pro_yearly", "max_yearly",  # Yearly variants
    "starter_annual", "premium_annual", "pro_annual", "max_annual",  # Annual variants
    "creator_basic", "creator_pro", "creator_max",  # Legacy naming
    "creator_basic_yearly", "creator_pro_yearly", "creator_max_yearly",  # Legacy yearly
]

def get_user_tier(plan: str) -> str:
    """
    Determines user tier based on their plan.
    
    Plans ending with "_pro" suffix = PROFESSIONAL (16:9 ads)
    All other plans = CREATOR (9:16 TikTok/Shorts)
    
    Returns:
        "professional" for ad-focused plans (16:9)
        "creator" for TikTok/Shorts focused plans (9:16)
    """
    if not plan:
        return "creator"
    
    plan_lower = plan.lower()
    
    # Check for professional suffix patterns
    if plan_lower in [p.lower() for p in PROFESSIONAL_PLANS]:
        return "professional"
    
    # Check for "_pro" suffix (professional ads plans)
    if plan_lower.endswith("_pro"):
        return "professional"
    
    # All other plans are Creator tier
    return "creator"

def get_fixed_duration_for_creator(ai_model: str) -> int:
    """
    Returns fixed duration for Creator tier users.
    Creator users cannot change duration - it's fixed based on model.
    
    - Sora models: 10 seconds
    - VEO models: 8 seconds
    """
    if ai_model in ("sora-2", "sora-2-pro"):
        return 10
    else:  # VEO models
        return 8

def get_aspect_ratio_for_tier(user_tier: str) -> str:
    """
    Returns the aspect ratio based on user tier.
    
    - Creator: 9:16 (vertical, TikTok/Shorts)
    - Professional: 16:9 (horizontal, ads/commercials)
    """
    if user_tier == "professional":
        return "16:9"
    return "9:16"

def is_creator_plan(plan: str) -> bool:
    """Check if a plan is a Creator tier plan."""
    return get_user_tier(plan) == "creator"

def is_professional_plan(plan: str) -> bool:
    """Check if a plan is a Professional tier plan."""
    return get_user_tier(plan) == "professional"


class VideoRequest(BaseModel):
    user_id: str  # Ignored server-side; derived from JWT
    niche: Optional[str] = None
    duration: int
    quality: str = "basic"
    custom_prompt: Optional[str] = None
    ai_model: str = "veo-3.1-generate-preview"
    
    @field_validator('ai_model', mode='before')
    @classmethod
    def normalize_model(cls, v):
        return normalize_ai_model(v)

class VideoResponse(BaseModel):
    job_id: str
    status: str
    estimated_time: str
    num_clips: int
    total_credits: int

class CheckoutRequest(BaseModel):
    plan: str
    user_id: str

class BuyCreditsRequest(BaseModel):
    user_id: str
    credits: int
    amount: int

class StoryboardShot(BaseModel):
    Scene: str
    duration: float

class VideoRequestAdvanced(BaseModel):
    model_config = {"protected_namespaces": ()}
    
    user_id: str  # Ignored server-side; derived from JWT
    niche: Optional[str] = None
    duration: int = 10
    quality: str = "basic"
    custom_prompt: Optional[str] = None
    image_urls: Optional[List[str]] = None
    shots: Optional[List[StoryboardShot]] = None
    model_type: Literal["text-to-video", "image-to-video", "storyboard"] = "text-to-video"
    ai_model: str = "veo-3.1-generate-preview"
    
    @field_validator('ai_model', mode='before')
    @classmethod
    def normalize_model(cls, v):
        return normalize_ai_model(v)


class YouTubeUploadRequest(BaseModel):
    """Request model for YouTube upload with flexible parameters"""
    privacy: Literal["public", "private", "unlisted"] = "public"
    schedule: bool = False
    title: Optional[str] = None  # Custom title, or auto-generated if not provided
    description: Optional[str] = None  # Custom description, or auto-generated if not provided
    tags: Optional[List[str]] = None  # Custom tags, or default if not provided
    thumbnail_url: Optional[str] = None  # URL of pre-generated thumbnail (optional)


class YouTubeUploadResponse(BaseModel):
    """Response model for YouTube upload"""
    success: bool
    youtube_id: Optional[str] = None
    youtube_url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    scheduled_for: Optional[str] = None  # ISO 8601 UTC timestamp
    scheduled_for_display: Optional[str] = None  # Human readable (Paris timezone)
    error: Optional[str] = None
    thumbnail_uploaded: bool = False

# ============= FUNCTIONS =============

def generate_prompt(niche: str = None, custom_prompt: str = None, clip_index: int = None, total_clips: int = None, user_tier: str = "creator") -> str:
    """Génère un prompt optimisé pour la génération vidéo
    
    Args:
        niche: Content niche/category
        custom_prompt: Custom user prompt
        clip_index: Index of current clip (for multi-clip videos)
        total_clips: Total number of clips
        user_tier: "creator" for 9:16 vertical or "professional" for 16:9 horizontal
    """
    
    if custom_prompt:
        base = custom_prompt
    else:
        templates = {
            "recettes": "Cinematic cooking video showing delicious recipe preparation, beautiful food styling, warm kitchen lighting, professional chef techniques, mouth-watering close-ups",
            "voyage": "Breathtaking travel footage showcasing stunning landscapes, cinematic drone shots, golden hour lighting, epic adventure vibes, cultural exploration, scenic beauty",
            "motivation": "Inspiring motivational content with dynamic visual metaphors, uplifting atmosphere, professional cinematography, energetic pacing, success imagery, empowering message",
            "tech": "Modern technology showcase with sleek product presentation, futuristic aesthetics, clean minimalist style, innovative tech display, professional lighting, cutting-edge visuals"
        }
        base = templates.get(niche.lower() if niche else "", f"High-quality viral video content, engaging visuals, professional production")
    
    if clip_index is not None and total_clips is not None and total_clips > 1:
        sequence_info = f", dynamic scene {clip_index} of {total_clips}, smooth cinematic transition, continuous flow"
    else:
        sequence_info = ""
    
    # Determine format suffix based on tier
    if user_tier == "professional":
        format_suffix = ", 16:9 horizontal widescreen format, professional commercial quality, cinematic"
    else:
        format_suffix = ", 9:16 vertical format, TikTok optimized, high quality, cinematic"
    
    return f"{base}{sequence_info}{format_suffix}"

def calculate_credits_cost(duration: int, quality: str, ai_model: str = "veo-3.1-generate-preview") -> int:
    """Calcule le coût en crédits selon la durée, la qualité et le modèle"""
    # Veo 3.1 (normal et fast) uses 8s segments, Sora uses 10s segments
    if ai_model in ("veo-3.1-generate-preview", "veo-3.1-fast-generate-preview"):
        num_clips = (duration + 7) // 8
    else:
        num_clips = (duration + 9) // 10
    
    if quality == "basic":
        return num_clips * 1
    elif quality == "pro_720p":
        return num_clips * 3
    elif quality == "pro_1080p":
        return num_clips * 5
    else:
        return num_clips

def _validate_duration_and_model(duration: int, ai_model: str):
    if duration < 6 or duration > 60:
        raise HTTPException(status_code=400, detail="Duration must be between 6 and 60 seconds")
    if ai_model in ("veo-3.1-generate-preview", "veo-3.1-fast-generate-preview"):
        # Veo 3.1 (normal et fast) supports flexible durations
        pass  # Accept any duration between 6-60
    else:
        # Sora uses 10s segments
        pass  # Accept any duration between 6-60


def get_tier_config(user_tier: str, ai_model: str) -> dict:
    """
    Get configuration parameters based on user tier.
    
    Returns dict with:
    - keyframes_per_sequence: 2 for starter, 3 for pro/max
    - transitions: whether to add crossfade transitions
    - transition_duration: duration of crossfade in seconds
    - resolution: video resolution
    - max_duration: maximum video duration in seconds
    """
    # Base configs by tier
    if user_tier == "creator":
        # Creator tier - TikTok/Shorts optimized
        return {
            "keyframes_per_sequence": 2,  # Simpler: just start + end
            "transitions": False,
            "transition_duration": 0.0,
            "resolution": "720p",
            "max_duration": 10,  # Single 8-10s video
        }
    else:
        # Professional tier - ads/commercials
        return {
            "keyframes_per_sequence": 3,  # Full: start + middle + end
            "transitions": True,
            "transition_duration": 0.3,
            "resolution": "1080p",
            "max_duration": 64,  # Up to 8 sequences
        }


def _create_fallback_script(prompt: str, num_sequences: int, aspect_ratio: str) -> dict:
    """
    Create a basic fallback script when LLM script generation fails.
    
    This generates simple keyframe prompts based on the user's prompt.
    """
    sequences = []
    
    orientation = "horizontal widescreen" if aspect_ratio == "16:9" else "vertical portrait"
    
    for seq_idx in range(num_sequences):
        seq_num = seq_idx + 1
        
        # Create basic keyframe prompts
        base_desc = f"Cinematic {aspect_ratio} frame ({orientation}). {prompt}"
        
        sequence = {
            "sequence_index": seq_num,
            "description": f"Sequence {seq_num}: {prompt}",
            "keyframe_start": f"{base_desc}. START of sequence {seq_num}. Opening shot with establishing composition. Professional cinematography.",
            "keyframe_middle": f"{base_desc}. MIDDLE of sequence {seq_num}. Dynamic mid-sequence visual. Camera in motion. Action peak.",
            "keyframe_end": f"{base_desc}. END of sequence {seq_num}. Closing frame preparing for {'next sequence' if seq_idx < num_sequences - 1 else 'finale'}. Smooth transition point.",
            "veo_prompt": f"Smooth cinematic motion. {prompt}. Professional cinematography, natural movement, film quality.",
            "transition_to_next": "Smooth visual transition" if seq_idx < num_sequences - 1 else None
        }
        
        sequences.append(sequence)
    
    return {
        "title": prompt[:50] + "..." if len(prompt) > 50 else prompt,
        "overall_mood": "Cinematic and professional",
        "sequences": sequences
    }


def _validate_image_urls(image_urls: Optional[List[str]], max_images: int = 18):
    """
    Validates image URLs for video generation.
    
    Args:
        image_urls: List of image URLs to validate
        max_images: Maximum allowed images (default 18 for Gemini 3 Pro)
    """
    if not image_urls:
        return
    
    if len(image_urls) > max_images:
        raise HTTPException(
            status_code=400, 
            detail=f"Too many images. Maximum allowed: {max_images}, provided: {len(image_urls)}"
        )
    
    try:
        supabase_host = urlparse(SUPABASE_URL).netloc
    except Exception:
        supabase_host = None
    
    for url in image_urls:
        parsed = urlparse(url)
        if not parsed.scheme.startswith("http"):
            raise HTTPException(status_code=400, detail="Invalid image URL scheme")
        if supabase_host and parsed.netloc != supabase_host:
            raise HTTPException(status_code=400, detail="Image URLs must be hosted on Supabase Storage")
        if "/storage/v1/object/public/video-images/" not in url:
            raise HTTPException(status_code=400, detail="Image URL not in allowed bucket 'video-images'")

async def process_video_generation(
    job_id: str, 
    niche: str, 
    duration: int, 
    quality: str, 
    user_id: str, 
    custom_prompt: str = None,
    image_urls: List[str] = None,
    shots: List[dict] = None,
    model_type: str = "text-to-video",
    ai_model: str = "veo-3.1-generate-preview",
    user_tier: str = "professional"
):
    """
    NEW ARCHITECTURE: Sequential keyframe-based video generation.
    
    Generates videos with visual continuity using 3 keyframes per sequence:
    - START keyframe: Beginning of sequence (reused from previous video's last frame for seq > 1)
    - MIDDLE keyframe: Midpoint of sequence
    - END keyframe: End of sequence (must connect to next sequence)
    
    Args:
        job_id: Unique job identifier
        niche: Content niche/category
        duration: Video duration in seconds
        quality: Video quality setting
        user_id: User identifier
        custom_prompt: Optional custom prompt
        image_urls: List of reference image URLs (up to 18)
        shots: List of storyboard shots
        model_type: Type of generation (text-to-video, image-to-video, storyboard)
        ai_model: AI model to use
        user_tier: "creator" for TikTok/Shorts or "professional" for ads
    """
    import asyncio
    from PIL import Image
    import httpx
    
    try:
        print(f"🎬 Starting KEYFRAME-BASED generation for job {job_id}")
        print(f"🤖 AI Model: {ai_model}")
        print(f"📊 Model type: {model_type}")
        print(f"👤 User tier: {user_tier.upper()}")
        
        get_supabase().table("video_jobs").update({
            "status": "generating"
        }).eq("id", job_id).execute()
        
        # ===== CONFIGURATION BY TIER =====
        tier_config = get_tier_config(user_tier, ai_model)
        aspect_ratio = get_aspect_ratio_for_tier(user_tier)
        num_keyframes = tier_config.get("keyframes_per_sequence", 3)
        add_transitions = tier_config.get("transitions", False)
        transition_duration = tier_config.get("transition_duration", 0.3)
        resolution = tier_config.get("resolution", "720p")
        
        print(f"📐 Config: {aspect_ratio}, {resolution}, {num_keyframes} keyframes/seq, transitions={add_transitions}")
        
        # ===== DÉTECTION DU MODÈLE AI =====
        if ai_model in ("veo-3.1-generate-preview", "veo-3.1-fast-generate-preview"):
            # ===== VEO 3.1 WITH KEYFRAME ARCHITECTURE =====
            use_fast_model = (ai_model == "veo-3.1-fast-generate-preview")
            model_variant = "FAST" if use_fast_model else "NORMAL"
            print(f"🎥 Using Veo 3.1 ({model_variant}) with KEYFRAME ARCHITECTURE")
            
            # 1. Calculate number of sequences
            num_sequences = max(1, (duration + 7) // 8)
            print(f"📊 Video: {duration}s → {num_sequences} sequences of 8s each")
            
            # 2. Download user images if provided
            user_pil_images = []
            if image_urls:
                for img_url in image_urls[:18]:
                    try:
                        print(f"📥 Downloading user image: {img_url[:50]}...")
                        resp = httpx.get(img_url, timeout=30)
                        user_pil_images.append(Image.open(BytesIO(resp.content)))
                    except Exception as e:
                        print(f"⚠️ Failed to download image: {e}")
            
            # 3. Generate cinematic script with keyframe structure
            print(f"📜 Generating CINEMATIC SCRIPT with {num_keyframes} keyframes per sequence...")
            script = get_gemini().generate_cinematic_script(
                user_prompt=custom_prompt or generate_prompt(niche, user_tier=user_tier),
                duration=duration,
                user_images=image_urls,
                user_tier=user_tier,
                num_keyframes_per_sequence=num_keyframes
            )
            
            if not script or "sequences" not in script:
                print("⚠️ Script generation failed, using fallback method")
                script = _create_fallback_script(custom_prompt or generate_prompt(niche), num_sequences, aspect_ratio)
            
            sequences = script.get("sequences", [])
            print(f"✅ Script ready: {len(sequences)} sequences")
            
            # 4. SEQUENTIAL VIDEO GENERATION WITH CONTINUITY
            # This is the key change - we process sequences ONE BY ONE
            # so we can use the last frame of video N as the first keyframe of video N+1
            
            all_video_bytes = []
            previous_last_frame = None  # Will store the last frame of previous video
            
            loop = asyncio.get_running_loop()
            
            for seq_idx, sequence in enumerate(sequences):
                seq_num = seq_idx + 1
                print(f"\n{'='*50}")
                print(f"🎬 SEQUENCE {seq_num}/{len(sequences)}")
                print(f"{'='*50}")
                
                # Log progress (no database update - progress column may not exist)
                progress = int((seq_idx / len(sequences)) * 100)
                print(f"📊 Progress: {progress}%")
                
                # Get keyframe prompts from script
                kf_start_prompt = sequence.get("keyframe_start", "")
                kf_middle_prompt = sequence.get("keyframe_middle", "")
                kf_end_prompt = sequence.get("keyframe_end", "")
                veo_prompt = sequence.get("veo_prompt", "")
                
                # Generate keyframes
                keyframes = []
                
                # KEYFRAME 1 (START): Use previous video's last frame OR generate new
                if previous_last_frame is not None:
                    print(f"  🔗 Using previous video's last frame as START keyframe (continuity)")
                    keyframes.append(previous_last_frame)
                else:
                    # First sequence - generate START keyframe
                    print(f"  🖼️ Generating START keyframe...")
                    
                    # Use user image as reference if available
                    ref_images = user_pil_images[:3] if user_pil_images else None
                    
                    kf_start_bytes = await loop.run_in_executor(
                        None,
                        lambda: get_gemini().generate_keyframe_image(
                            keyframe_prompt=kf_start_prompt,
                            reference_images=ref_images,
                            aspect_ratio=aspect_ratio,
                            position="START"
                        )
                    )
                    
                    if kf_start_bytes:
                        keyframes.append(kf_start_bytes)
                        # Upload for debug/preview
                        try:
                            await loop.run_in_executor(
                                None,
                                get_uploader().upload_bytes,
                                kf_start_bytes,
                                f"{job_id}_seq{seq_num}_kf_start.jpg"
                            )
                        except Exception:
                            pass
                
                # KEYFRAME 2 (MIDDLE): Always generate
                if num_keyframes >= 2:
                    print(f"  🖼️ Generating MIDDLE keyframe...")
                    
                    kf_middle_bytes = await loop.run_in_executor(
                        None,
                        lambda: get_gemini().generate_keyframe_image(
                            keyframe_prompt=kf_middle_prompt,
                            reference_images=user_pil_images[:3] if user_pil_images else None,
                            aspect_ratio=aspect_ratio,
                            position="MIDDLE"
                        )
                    )
                    
                    if kf_middle_bytes:
                        keyframes.append(kf_middle_bytes)
                        try:
                            await loop.run_in_executor(
                                None,
                                get_uploader().upload_bytes,
                                kf_middle_bytes,
                                f"{job_id}_seq{seq_num}_kf_middle.jpg"
                            )
                        except Exception:
                            pass
                
                # KEYFRAME 3 (END): Always generate
                if num_keyframes >= 3:
                    print(f"  🖼️ Generating END keyframe...")
                    
                    kf_end_bytes = await loop.run_in_executor(
                        None,
                        lambda: get_gemini().generate_keyframe_image(
                            keyframe_prompt=kf_end_prompt,
                            reference_images=user_pil_images[:3] if user_pil_images else None,
                            aspect_ratio=aspect_ratio,
                            position="END"
                        )
                    )
                    
                    if kf_end_bytes:
                        keyframes.append(kf_end_bytes)
                        try:
                            await loop.run_in_executor(
                                None,
                                get_uploader().upload_bytes,
                                kf_end_bytes,
                                f"{job_id}_seq{seq_num}_kf_end.jpg"
                            )
                        except Exception:
                            pass
                
                # Validate keyframes
                if len(keyframes) == 0:
                    print(f"  ⚠️ No keyframes generated, falling back to text-to-video")
                    keyframes = None
                else:
                    print(f"  ✅ {len(keyframes)} keyframes ready for Veo")
                
                # GENERATE VIDEO WITH VEO 3.1
                print(f"  🎥 Generating video with Veo 3.1 ({len(keyframes) if keyframes else 0} keyframes)...")
                
                video_path = f"/tmp/{job_id}_seq{seq_num}.mp4"
                
                if keyframes and len(keyframes) > 0:
                    # Use the new keyframe-based generation method
                    await loop.run_in_executor(
                        None,
                        lambda: get_veo().generate_video_with_keyframes(
                            prompt=veo_prompt,
                            keyframes=keyframes,
                            aspect_ratio=aspect_ratio,
                            resolution=resolution,
                            duration_seconds=8,
                            download_path=video_path,
                            use_fast_model=use_fast_model,
                        )
                    )
                else:
                    # Fallback to standard generation without keyframes
                    await loop.run_in_executor(
                        None,
                        lambda: get_veo().generate_video_and_wait(
                            prompt=veo_prompt,
                            aspect_ratio=aspect_ratio,
                            resolution=resolution,
                            duration_seconds=8,
                            download_path=video_path,
                            use_fast_model=use_fast_model,
                        )
                    )
                
                # Read video bytes
                with open(video_path, "rb") as f:
                    video_bytes = f.read()
                
                all_video_bytes.append(video_bytes)
                print(f"  ✅ Sequence {seq_num} video generated: {len(video_bytes)} bytes")
                
                # EXTRACT LAST FRAME FOR NEXT SEQUENCE
                if seq_idx < len(sequences) - 1:  # Not the last sequence
                    print(f"  🔄 Extracting last frame for continuity...")
                    try:
                        previous_last_frame = await loop.run_in_executor(
                            None,
                            lambda: get_video_editor().extract_last_frame(video_bytes)
                        )
                        print(f"  ✅ Last frame extracted: {len(previous_last_frame)} bytes")
                    except Exception as e:
                        print(f"  ⚠️ Failed to extract last frame: {e}")
                        previous_last_frame = None
                
                # Upload sequence video
                try:
                    await loop.run_in_executor(
                        None,
                        get_uploader().upload_bytes,
                        video_bytes,
                        f"{job_id}_seq{seq_num}.mp4"
                    )
                except Exception:
                    pass
            
            # 5. CONCATENATE ALL VIDEOS
            print(f"\n{'='*50}")
            print(f"🎞️ MERGING {len(all_video_bytes)} sequences...")
            print(f"{'='*50}")
            
            if len(all_video_bytes) == 1:
                final_video_bytes = all_video_bytes[0]
            else:
                final_video_bytes = await loop.run_in_executor(
                    None,
                    lambda: get_video_editor().concatenate_video_bytes(
                        all_video_bytes,
                        f"{job_id}_final.mp4",
                        add_transitions=add_transitions,
                        transition_duration=transition_duration
                    )
                )
            
            # 6. UPLOAD FINAL VIDEO
            print(f"📤 Uploading final video ({len(final_video_bytes)} bytes)...")
            final_url = await loop.run_in_executor(
                None,
                get_uploader().upload_bytes,
                final_video_bytes,
                f"{job_id}.mp4"
            )
            
            # 7. UPDATE JOB STATUS
            get_supabase().table("video_jobs").update({
                "status": "completed",
                "video_url": final_url,
                "completed_at": "now()",
            }).eq("id", job_id).execute()
            
            print(f"✅ Job {job_id} COMPLETED! URL: {final_url}")
        
        else:
            # ===== MODE SORA 2 (OpenAI Videos API) - Parallel Advanced Scripting =====
            use_pro_model = (ai_model == "sora-2-pro")
            model_variant = "PRO" if use_pro_model else "STANDARD"
            print(f"🎥 Using Sora 2 API ({model_variant} mode) with Parallel Advanced Scripting")
            print(f"🎨 User tier: {user_tier} - {'TikTok/Shorts optimized' if user_tier == 'creator' else 'Professional ads optimized'}")

            def quality_to_sora_params(q: str):
                # Map simple: basic => default, pro_720p => size 1280x720, pro_1080p => size 1920x1080
                if q == "pro_1080p":
                    return "1920x1080"
                if q == "pro_720p":
                    return "1280x720"
                return None

            size = quality_to_sora_params(quality)

            # 1. Calculate Segments (10s blocks for Sora)
            num_segments = (duration + 9) // 10
            
            # For Creator tier: simpler structure (1-3 images for scene changes)
            # For Professional tier: complex sequences with multiple shots
            images_per_segment = 1 if user_tier == "creator" else 3
            
            # 2. Generate Script using Gemini with tier-specific prompt enrichment
            print(f"📜 Generating {user_tier.upper()} script for {duration}s video ({num_segments} segments)...")
            script = get_gemini().generate_video_script(
                prompt=custom_prompt or generate_prompt(niche),
                duration=duration,
                num_segments=num_segments,
                user_images=image_urls,
                segment_duration=10,  # Sora uses 10s segments
                user_tier=user_tier,
                images_per_segment=images_per_segment
            )
            
            # 3. Download user images if provided (now supports up to 18 images)
            user_pil_images = []
            if image_urls:
                import httpx
                from PIL import Image
                for img_url in image_urls[:18]:  # Support up to 18 images
                    try:
                        print(f"📥 Downloading user image: {img_url[:50]}...")
                        resp = httpx.get(img_url, timeout=30)
                        user_pil_images.append(Image.open(BytesIO(resp.content)))
                    except Exception as e:
                        print(f"⚠️ Failed to download image: {e}")
            
            import asyncio
            from concurrent.futures import ThreadPoolExecutor
            
            # Determine aspect ratio based on tier for Sora
            tier_aspect_ratio = get_aspect_ratio_for_tier(user_tier)
            print(f"📐 Aspect ratio for {user_tier.upper()} tier (Sora): {tier_aspect_ratio}")
            
            async def process_sora_shot(segment_index, shot_data, user_images_list, tier=user_tier, aspect_ratio=tier_aspect_ratio):
                """Helper to process a single shot: Image Gen -> Video Gen with Sora 2"""
                shot_idx = shot_data.get("shot_index", 0)
                img_prompt = shot_data.get("image_prompt")
                vid_prompt = shot_data.get("video_prompt")
                use_user_image_idx = shot_data.get("use_user_image_index")
                shot_duration = shot_data.get("duration", 10)
                scene_images = shot_data.get("scene_images", [])  # Additional scene variation prompts
                
                print(f"🎬 Processing Seg {segment_index} Shot {shot_idx} ({tier.upper()} tier, {aspect_ratio})...")
                
                loop = asyncio.get_running_loop()
                
                input_reference = None
                
                # Check if we should use a user-provided image
                if use_user_image_idx is not None and use_user_image_idx < len(user_images_list):
                    print(f"  🖼️ Using user-provided image {use_user_image_idx} for this shot")
                    # Save user image to temp file for Sora
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                        user_images_list[use_user_image_idx].save(tmp.name)
                        input_reference = tmp.name
                else:
                    # A. Generate Image with Gemini using enriched prompt and reference images
                    print(f"  📸 Seg {segment_index} Shot {shot_idx}: Generating Image...")
                    
                    # Select reference images based on tier
                    ref_images_for_generation = None
                    if tier == "creator" and len(user_images_list) > 0:
                        # Creator: use first 3 user images as style reference
                        ref_images_for_generation = user_images_list[:3]
                    elif tier == "professional" and len(user_images_list) > 0:
                        # Professional: distribute images across segments for brand consistency
                        start_idx = (segment_index - 1) * 3 % len(user_images_list)
                        ref_images_for_generation = user_images_list[start_idx:start_idx + 3]
                    
                    # Generate with reference images if available
                    def generate_with_refs():
                        return get_gemini().generate_image(
                            prompt=img_prompt,
                            reference_images=ref_images_for_generation,
                            aspect_ratio=aspect_ratio,  # Use tier-specific aspect ratio
                            resolution="4K"  # 4K quality for both tiers
                        )
                    
                    try:
                        image_bytes = await loop.run_in_executor(None, generate_with_refs)
                        
                        if image_bytes:
                            # Validate and save generated image for Sora input
                            import tempfile
                            from PIL import Image as PILImage
                            try:
                                # Validate the image first
                                test_img = PILImage.open(BytesIO(image_bytes))
                                test_img.load()  # Force load to verify
                                
                                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                                    tmp.write(image_bytes)
                                    input_reference = tmp.name
                                print(f"  ✅ Image generated successfully for Seg {segment_index} Shot {shot_idx}")
                                
                                # Upload generated image for reference
                                try:
                                    await loop.run_in_executor(None, get_uploader().upload_bytes, image_bytes, f"{job_id}_seg{segment_index}_shot{shot_idx}.png")
                                except Exception as e:
                                    print(f"  ⚠️ Failed to upload generated image: {e}")
                            except Exception as pil_err:
                                print(f"  ⚠️ Image data invalid, proceeding with text-to-video: {pil_err}")
                                input_reference = None
                        else:
                            print(f"  ⚠️ Image generation returned None, proceeding with text-to-video")
                    except Exception as img_gen_err:
                        print(f"  ⚠️ Image generation failed, proceeding with text-to-video: {img_gen_err}")
                        input_reference = None

                # B. Generate Video with Sora 2
                print(f"  🎥 Seg {segment_index} Shot {shot_idx}: Generating Video with Sora 2...")
                
                # Sora accepts 4, 8, or 12 second videos
                sora_duration = 8  # Default to 8s
                if shot_duration <= 4:
                    sora_duration = 4
                elif shot_duration <= 8:
                    sora_duration = 8
                else:
                    sora_duration = 12
                
                local_path = await loop.run_in_executor(
                    None, 
                    lambda: get_sora().generate_video_and_wait(
                        prompt=vid_prompt,
                        use_pro=use_pro_model,
                        size=size,
                        seconds=sora_duration,
                        input_reference=input_reference,
                        download_path=f"/tmp/{job_id}_seg{segment_index}_shot{shot_idx}.mp4",
                    )
                )
                
                # Upload clip
                with open(local_path, "rb") as f:
                    data = f.read()
                url = await loop.run_in_executor(None, get_uploader().upload_bytes, data, f"{job_id}_seg{segment_index}_shot{shot_idx}.mp4")
                return (segment_index, shot_idx, url)

            all_clip_urls = []
            
            if script and "segments" in script:
                tasks = []
                total_segments = len(script["segments"])
                total_shots = 0
                
                # Create tasks for ALL shots across ALL segments
                for segment in script["segments"]:
                    seg_idx = segment.get("segment_index", 0)
                    shots = segment.get("shots", [])
                    total_shots += len(shots)
                    
                    for shot in shots:
                        tasks.append(process_sora_shot(seg_idx, shot, user_pil_images))
                
                # Log detailed generation plan
                expected_duration = total_segments * 10  # Sora uses 10s segments
                print(f"📊 GENERATION PLAN (Sora):")
                print(f"   - Requested duration: {duration}s")
                print(f"   - Segments to generate: {total_segments}")
                print(f"   - Total shots: {total_shots}")
                print(f"   - Expected output duration: {expected_duration}s")
                print(f"🚀 Launching {len(tasks)} parallel generation tasks with enriched prompts...")
                # Run all tasks in parallel
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results
                valid_results = []
                for res in results:
                    if isinstance(res, Exception):
                        print(f"❌ Task failed: {res}")
                    else:
                        valid_results.append(res)
                
                # Sort by segment then shot to ensure correct order
                valid_results.sort(key=lambda x: (x[0], x[1]))
                all_clip_urls = [r[2] for r in valid_results]
                
            else:
                # Fallback to simple generation if script generation fails
                print("⚠️ Script generation failed, falling back to simple generation (Sora).")
                
                # Determine aspect ratio based on tier
                tier_aspect_ratio = get_aspect_ratio_for_tier(user_tier)
                print(f"📐 Fallback using aspect ratio: {tier_aspect_ratio} for {user_tier.upper()} tier (Sora)")
                
                # Generate a single video with the enriched prompt
                enriched_prompt = get_gemini().enrich_prompt(
                    custom_prompt or generate_prompt(niche),
                    segment_context="Single video generation",
                    user_image_description=None,
                    user_tier=user_tier  # Pass user tier for proper prompt enrichment
                )
                
                # Use first user image if available
                input_ref = None
                if user_pil_images:
                    import tempfile
                    print(f"  🖼️ Using first user-provided image in Sora fallback mode")
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                        user_pil_images[0].save(tmp.name)
                        input_ref = tmp.name
                
                # For longer videos (>10s), generate multiple clips even in fallback mode
                target_clips = max(1, (duration + 9) // 10)
                print(f"  📹 Generating {target_clips} clip(s) for {duration}s video in Sora fallback mode")
                
                fallback_clip_urls = []
                for clip_idx in range(target_clips):
                    clip_prompt = enriched_prompt
                    if target_clips > 1:
                        clip_prompt = f"{enriched_prompt}, scene {clip_idx + 1} of {target_clips}, continuous narrative flow"
                    
                    # Use user image only for first clip
                    clip_input_ref = input_ref if clip_idx == 0 else None
                    
                    local_path = get_sora().generate_video_and_wait(
                        prompt=clip_prompt,
                        use_pro=use_pro_model,
                        size=size,
                        seconds=10,
                        input_reference=clip_input_ref,
                        download_path=f"/tmp/{job_id}_fallback_{clip_idx}.mp4",
                    )
                    
                    with open(local_path, "rb") as f:
                        data = f.read()
                    url = get_uploader().upload_bytes(data, f"{job_id}_fallback_{clip_idx}.mp4")
                    fallback_clip_urls.append(url)
                    print(f"  ✅ Sora fallback clip {clip_idx + 1}/{target_clips} generated")
                
                all_clip_urls = fallback_clip_urls

            if len(all_clip_urls) == 1:
                final_url = all_clip_urls[0]
            elif len(all_clip_urls) > 1:
                print(f"🎞️ Concatenating {len(all_clip_urls)} Sora clips...")
                concatenated_data = get_video_editor().concatenate_videos(all_clip_urls, f"{job_id}.mp4")
                final_url = get_uploader().upload_bytes(concatenated_data, f"{job_id}.mp4")
            else:
                raise Exception("No clips generated")

            get_supabase().table("video_jobs").update({
                "status": "completed",
                "video_url": final_url,
                "completed_at": "now()",
            }).eq("id", job_id).execute()

            print(f"✅ Job {job_id} completed! (credits already deducted)")
        
    except Exception as e:
        print(f"❌ Error generating video {job_id}: {e}")
        import traceback
        traceback.print_exc()
        
        # REFUND CREDITS
        try:
            print(f"💰 Refunding credits for job {job_id} due to failure...")
            # We need to calculate amount to refund. 
            # We can re-calculate or store cost in metadata. 
            # For now, re-calculate based on job data if possible, but we don't have it handy easily without query.
            # Let's assume we can pass it or query it.
            # Ideally we should have stored 'cost' in video_jobs.
            # For now, let's just query the job to get duration/quality if needed, or pass it to this function.
            # We passed duration/quality to this function!
            cost = calculate_credits_cost(duration, quality, ai_model)
            get_supabase().rpc("refund_credits", {
                "p_user_id": user_id,
                "p_amount": cost
            }).execute()
            print(f"✅ Refunded {cost} credits.")
        except Exception as refund_error:
            print(f"❌ Error refunding credits: {refund_error}")

        get_supabase().table("video_jobs").update({
            "status": "failed",
            "error": str(e)
        }).eq("id", job_id).execute()

# ============= ENDPOINTS =============

@app.get("/")
def root():
    return {
        "service": "Vykso Backend API",
        "version": "1.0.0",
        "status": "running",
        "environment": os.getenv("ENVIRONMENT", "development")
    }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/videos/generate", response_model=VideoResponse)
async def generate_video(req: VideoRequest, background_tasks: BackgroundTasks, request: Request):
    """
    Endpoint principal : génère une vidéo de durée variable
    
    Handles two user tiers:
    - CREATOR tier: Fixed duration (8s VEO, 10s Sora), TikTok/Shorts optimized
    - PROFESSIONAL tier: Variable duration, ad-optimized
    """
    # Auth: derive user_id from JWT
    token_user_id = await _get_authenticated_user_id(request)
    # Security: ignore body user_id and use token subject
    req.user_id = token_user_id
    
    try:
        user = get_supabase().table("profiles").select("*").eq("id", req.user_id).execute()
        
        if not user.data:
            print(f"👤 Creating new user: {req.user_id}")
            get_supabase().table("profiles").insert({
                "id": req.user_id,
                "email": f"{req.user_id}@vykso.com",
                "credits": 10,
                "plan": "free"
            }).execute()
            user = get_supabase().table("profiles").select("*").eq("id", req.user_id).execute()
        
        user_data = user.data[0]
        user_plan = user_data.get("plan", "free")
        user_tier = get_user_tier(user_plan)
        print(f"👤 User: {req.user_id}, Credits: {user_data['credits']}, Plan: {user_plan}, Tier: {user_tier}")
        
    except Exception as e:
        print(f"❌ Error checking user: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    # For CREATOR tier: Force fixed duration (no choice)
    if is_creator_plan(user_plan):
        fixed_duration = get_fixed_duration_for_creator(req.ai_model)
        req.duration = fixed_duration
        print(f"👤 Creator tier detected - forcing duration to {fixed_duration}s")

    # Validate model/duration
    _validate_duration_and_model(req.duration, req.ai_model)
    
    if not req.niche and not req.custom_prompt:
        raise HTTPException(status_code=400, detail="Either niche or custom_prompt is required")
    
    # Calculate clips based on model (8s for Veo 3.1/fast, 10s for Sora)
    if req.ai_model in ("veo-3.1-generate-preview", "veo-3.1-fast-generate-preview"):
        num_clips = (req.duration + 7) // 8
    else:
        num_clips = (req.duration + 9) // 10
    required_credits = calculate_credits_cost(req.duration, req.quality, req.ai_model)
    
    # Deduct credits atomically BEFORE scheduling work (backend source of truth)
    try:
        decrement = get_supabase().rpc("decrement_credits", {
            "p_user_id": req.user_id,
            "p_amount": required_credits,
        }).execute()
        if not decrement.data:
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient credits. Need {required_credits} credits."
            )
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error decrementing credits: {e}")
        raise HTTPException(status_code=500, detail="Unable to deduct credits")
    
    try:
        job = get_supabase().table("video_jobs").insert({
            "user_id": req.user_id,
            "status": "pending",
            "niche": req.niche or "custom",
            "duration": req.duration,
            "quality": req.quality,
            "prompt": req.custom_prompt or generate_prompt(req.niche),
            "metadata": json.dumps({
                "num_clips": num_clips,
                "target_duration": req.duration,
                "custom_prompt": req.custom_prompt,
                "ai_model": req.ai_model,
                "user_tier": user_tier
            })
        }).execute()
        
        job_id = job.data[0]["id"]
        print(f"📋 Job created: {job_id}")
        
    except Exception as e:
        print(f"❌ Error creating job: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    background_tasks.add_task(
        process_video_generation, 
        job_id, 
        req.niche, 
        req.duration, 
        req.quality, 
        req.user_id,
        req.custom_prompt,
        None,
        None,
        "text-to-video",
        req.ai_model,
        user_tier  # Pass user tier for differentiated prompts
    )
    
    estimated_time = num_clips * 40
    return VideoResponse(
        job_id=job_id,
        status="pending",
        estimated_time=f"{estimated_time}-{estimated_time + 60}s",
        num_clips=num_clips,
        total_credits=required_credits
    )

@app.post("/api/videos/generate-advanced")
async def generate_video_advanced(req: VideoRequestAdvanced, background_tasks: BackgroundTasks, request: Request):
    """
    Endpoint avancé : supporte storyboard, image-to-video, etc.
    
    Handles two user tiers:
    - CREATOR tier: Fixed duration (8s VEO, 10s Sora), TikTok/Shorts optimized, 1-3 images
    - PROFESSIONAL tier: Variable duration, ad-optimized, multiple sequences
    """
    # Auth: derive user_id from JWT
    token_user_id = await _get_authenticated_user_id(request)
    req.user_id = token_user_id

    # Vérifier user pour déterminer le tier
    try:
        user = get_supabase().table("profiles").select("*").eq("id", req.user_id).execute()
        
        if not user.data:
            get_supabase().table("profiles").insert({
                "id": req.user_id,
                "email": f"{req.user_id}@vykso.com",
                "credits": 10,
                "plan": "free"
            }).execute()
            user = get_supabase().table("profiles").select("*").eq("id", req.user_id).execute()
        
        user_data = user.data[0]
        user_plan = user_data.get("plan", "free")
        user_tier = get_user_tier(user_plan)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    # For CREATOR tier: Force fixed duration (no choice)
    if is_creator_plan(user_plan):
        fixed_duration = get_fixed_duration_for_creator(req.ai_model)
        req.duration = fixed_duration
        print(f"👤 Creator tier detected - forcing duration to {fixed_duration}s")

    # Calculer la durée totale pour storyboard
    if req.model_type == "storyboard" and req.shots:
        total_duration = sum(shot.duration for shot in req.shots)
        req.duration = int(total_duration)
    
    # Validate model/duration
    _validate_duration_and_model(req.duration, req.ai_model)
    
    if req.model_type != "storyboard":
        if not req.niche and not req.custom_prompt:
            raise HTTPException(status_code=400, detail="Either niche or custom_prompt is required")
    
    # Additional server-side validations - now supports up to 18 images
    _validate_image_urls(req.image_urls, max_images=18)

    # Calculer le coût
    required_credits = calculate_credits_cost(req.duration, req.quality, req.ai_model)
    
    try:
        # Deduct credits BEFORE scheduling generation
        decrement = get_supabase().rpc("decrement_credits", {
            "p_user_id": req.user_id,
            "p_amount": required_credits,
        }).execute()
        if not decrement.data:
            raise HTTPException(status_code=402, detail="Insufficient credits")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    # Créer job
    try:
        job = get_supabase().table("video_jobs").insert({
            "user_id": req.user_id,
            "status": "pending",
            "niche": req.niche or ("storyboard" if req.model_type == "storyboard" else "custom"),
            "duration": req.duration,
            "quality": req.quality,
            "prompt": req.custom_prompt or generate_prompt(req.niche),
            "metadata": json.dumps({
                "model_type": req.model_type,
                "has_images": bool(req.image_urls),
                "num_images": len(req.image_urls) if req.image_urls else 0,
                "num_shots": len(req.shots) if req.shots else 0,
                "ai_model": req.ai_model,
                "user_tier": user_tier
            })
        }).execute()
        
        job_id = job.data[0]["id"]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    # Lancer génération with user_tier
    shots_dict = [shot.dict() for shot in req.shots] if req.shots else None
    
    background_tasks.add_task(
        process_video_generation, 
        job_id, 
        req.niche, 
        req.duration, 
        req.quality, 
        req.user_id,
        req.custom_prompt,
        req.image_urls,
        shots_dict,
        req.model_type,
        req.ai_model,
        user_tier  # Pass user tier for differentiated prompts
    )
    
    estimated_time = (len(req.shots) if req.shots else 1) * 40
    return VideoResponse(
        job_id=job_id,
        status="pending",
        estimated_time=f"{estimated_time}-{estimated_time + 60}s",
        num_clips=len(req.shots) if req.shots else 1,
        total_credits=required_credits
    )

@app.get("/api/videos/{job_id}/status")
async def get_video_status(job_id: str, request: Request):
    """Check le statut d'une vidéo"""
    try:
        # Require auth and ensure ownership
        token_user_id = await _get_authenticated_user_id(request)
        job = get_supabase().table("video_jobs").select("*").eq("id", job_id).single().execute()
        
        if not job.data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        job_data = job.data

        if job_data.get("user_id") != token_user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        
        if job_data.get("metadata"):
            try:
                job_data["metadata"] = json.loads(job_data["metadata"])
            except:
                pass
        
        return job_data
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error getting job status: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/api/users/{user_id}/videos")
async def get_user_videos(user_id: str, request: Request, limit: int = 20, offset: int = 0):
    """Liste les vidéos d'un utilisateur"""
    try:
        # Require auth and ensure user matches token
        token_user_id = await _get_authenticated_user_id(request)
        if token_user_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        videos = get_supabase().table("video_jobs").select("*").eq("user_id", user_id).order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        
        return {
            "total": len(videos.data),
            "videos": videos.data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/users/{user_id}/info")
async def get_user_info(user_id: str, request: Request):
    """Récupère les infos complètes d'un utilisateur"""
    try:
        # Require auth and ensure user matches token
        token_user_id = await _get_authenticated_user_id(request)
        if token_user_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        user = get_supabase().table("profiles").select("*").eq("id", user_id).single().execute()
        
        if not user.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        return user.data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/users/{user_id}/tier")
async def get_user_tier_info(user_id: str, request: Request):
    """
    Get user tier information for frontend to adapt UI.
    
    TIER LOGIC:
    - Plans: starter, premium, pro, max (and yearly variants) → CREATOR tier (9:16 vertical)
    - Plans: premium_pro, pro_pro, max_pro (with _pro suffix) → PROFESSIONAL tier (16:9 horizontal)
    
    Returns:
        - plan: Current plan name
        - tier: "creator" or "professional"
        - is_creator: Boolean for quick check
        - aspect_ratio: "9:16" for creator, "16:9" for professional
        - fixed_duration: Fixed duration if creator tier (null for professional)
        - max_images: Maximum images allowed (18 for all)
        - features: Dictionary of tier-specific features
    """
    try:
        # Require auth and ensure user matches token
        token_user_id = await _get_authenticated_user_id(request)
        if token_user_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        
        user = get_supabase().table("profiles").select("plan, credits").eq("id", user_id).single().execute()
        
        if not user.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        plan = user.data.get("plan", "free")
        credits = user.data.get("credits", 0)
        tier = get_user_tier(plan)
        is_creator = is_creator_plan(plan)
        aspect_ratio = get_aspect_ratio_for_tier(tier)
        
        # Build tier-specific features
        if is_creator:
            features = {
                "duration_selection": False,  # Creator tier cannot select duration
                "fixed_duration_veo": 8,
                "fixed_duration_sora": 10,
                "aspect_ratio": "9:16",  # Vertical for TikTok/Shorts
                "orientation": "vertical",
                "prompt_style": "viral_tiktok_shorts",
                "sequences": False,  # No complex sequences
                "max_images_per_segment": 3,
                "description": "Optimisé pour TikTok et YouTube Shorts (9:16 vertical)"
            }
        else:
            features = {
                "duration_selection": True,  # Professional can select duration
                "min_duration": 6,
                "max_duration": 60,
                "aspect_ratio": "16:9",  # Horizontal widescreen for ads
                "orientation": "horizontal",
                "prompt_style": "professional_advertising",
                "sequences": True,  # Complex multi-sequence videos
                "max_images_per_segment": 6,
                "description": "Optimisé pour publicités professionnelles (16:9 horizontal)"
            }
        
        return {
            "plan": plan,
            "tier": tier,
            "is_creator": is_creator,
            "aspect_ratio": aspect_ratio,
            "credits": credits,
            "max_images": 18,  # Both tiers support up to 18 reference images
            "features": features
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/users/sync")
async def sync_user_from_auth(user_data: dict, request: Request):
    """Synchronise les données utilisateur depuis Supabase Auth (appelé après login OAuth)"""
    try:
        # Require auth and ensure identity consistency when possible
        token_user_id = await _get_authenticated_user_id(request)
        user_id = user_data.get("id")
        email = user_data.get("email")
        first_name = user_data.get("user_metadata", {}).get("first_name") or user_data.get("user_metadata", {}).get("full_name", "").split()[0] if user_data.get("user_metadata", {}).get("full_name") else None
        last_name = user_data.get("user_metadata", {}).get("last_name") or " ".join(user_data.get("user_metadata", {}).get("full_name", "").split()[1:]) if user_data.get("user_metadata", {}).get("full_name") and len(user_data.get("user_metadata", {}).get("full_name", "").split()) > 1 else None
        
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID is required")

        if token_user_id and user_id and token_user_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        
        # Check if user exists
        existing = get_supabase().table("profiles").select("*").eq("id", user_id).execute()
        
        update_data = {
            "email": email or f"{user_id}@vykso.com",
        }
        
        if first_name:
            update_data["first_name"] = first_name
        if last_name:
            update_data["last_name"] = last_name
        
        if existing.data:
            # Update existing user
            result = get_supabase().table("profiles").update(update_data).eq("id", user_id).execute()
        else:
            # Create new user
            update_data.update({
                "id": user_id,
                "credits": 10,
                "plan": "free"
            })
            result = get_supabase().table("profiles").insert(update_data).execute()
        
        return {"success": True, "user": result.data[0] if result.data else None}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error syncing user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/videos/{job_id}/upload-youtube", response_model=YouTubeUploadResponse)
async def upload_video_to_youtube(job_id: str, request: Request, body: YouTubeUploadRequest = None):
    """
    Upload a generated video to YouTube with flexible options.
    
    Parameters:
    - privacy: 'public', 'private', or 'unlisted' (default: 'public')
    - schedule: If true, schedules for optimal time (video will be private until then)
    - title: Custom title (auto-generated clickbait if not provided)
    - description: Custom description (auto-generated if not provided)
    - tags: Custom tags list (defaults to ['Shorts', 'AI', 'Vykso'])
    - thumbnail_url: URL of pre-generated thumbnail (auto-generated with Imagen if not provided)
    
    Returns YouTube video URL, ID, and scheduled time if applicable.
    """
    import requests as req_lib
    
    token_user_id = await _get_authenticated_user_id(request)
    
    # Default body if not provided
    if body is None:
        body = YouTubeUploadRequest()
    
    try:
        # 1. Get User YouTube Tokens from profiles table
        user = get_supabase().table("profiles").select("youtube_tokens").eq("id", token_user_id).single().execute()
        if not user.data or not user.data.get("youtube_tokens"):
            raise HTTPException(
                status_code=400, 
                detail="YouTube account not connected. Please connect your YouTube account first."
            )
        
        tokens = user.data["youtube_tokens"]
        
        # Validate tokens have all required fields
        required_fields = ['token', 'refresh_token', 'token_uri', 'client_id', 'client_secret']
        missing_fields = [f for f in required_fields if not tokens.get(f)]
        
        if missing_fields:
            print(f"❌ YouTube tokens missing fields: {missing_fields}")
            raise HTTPException(
                status_code=400,
                detail=f"Your YouTube connection is incomplete (missing: {', '.join(missing_fields)}). Please disconnect and reconnect your YouTube account."
            )
        
        # Refresh tokens if needed
        refreshed_tokens = get_youtube().refresh_credentials(tokens)
        if refreshed_tokens is None:
            raise HTTPException(
                status_code=400,
                detail="Failed to refresh YouTube credentials. Please disconnect and reconnect your YouTube account."
            )
        if refreshed_tokens != tokens:
            # Update tokens in database
            get_supabase().table("profiles").update({
                "youtube_tokens": refreshed_tokens
            }).eq("id", token_user_id).execute()
            tokens = refreshed_tokens
        
        # 2. Get Video Job Data
        job = get_supabase().table("video_jobs").select("*").eq("id", job_id).single().execute()
        if not job.data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Verify ownership
        if job.data.get("user_id") != token_user_id:
            raise HTTPException(status_code=403, detail="Forbidden")
        
        video_url = job.data.get("video_url")
        if not video_url:
            raise HTTPException(status_code=400, detail="Video not ready")
        
        original_prompt = job.data.get("prompt", "AI Generated Video")
        
        # 3. Generate or use provided content
        # Title
        if body.title:
            final_title = body.title
        else:
            print("🎯 Generating clickbait title...")
            final_title = get_content_generator().generate_clickbait_title(original_prompt)
        
        # Description
        if body.description:
            final_description = body.description
        else:
            print("📝 Generating description...")
            final_description = get_content_generator().generate_description(original_prompt)
        
        # Ensure #Shorts is present
        final_title, final_description = get_content_generator().check_shorts_tag_present(
            final_title, final_description
        )
        
        # Tags
        final_tags = get_content_generator().get_default_tags(body.tags)
        
        # 4. Calculate schedule time if requested
        schedule_time_iso = None
        schedule_time_display = None
        final_privacy = body.privacy
        
        if body.schedule:
            print("📅 Calculating optimal publish time...")
            optimal_time = get_schedule_calculator().calculate_optimal_publish_time()
            schedule_time_iso = get_schedule_calculator().format_for_youtube_api(optimal_time)
            schedule_time_display = get_schedule_calculator().format_for_display(optimal_time)
            # When scheduling, privacy MUST be 'private'
            final_privacy = 'private'
            print(f"⏰ Scheduled for: {schedule_time_display}")
        
        # 5. Download video to temp file
        print(f"📥 Downloading video for upload...")
        path = _extract_object_path_from_public_url(video_url, VIDEOS_BUCKET)
        if not path:
            # Try direct download if it's a full URL
            r = req_lib.get(video_url, timeout=60)
            video_data = r.content
        else:
            video_data = get_supabase().storage.from_(VIDEOS_BUCKET).download(path)
        
        temp_video_path = f"/tmp/{job_id}_upload.mp4"
        with open(temp_video_path, "wb") as f:
            f.write(video_data)
        
        # 6. Generate or download thumbnail
        thumbnail_bytes = None
        thumbnail_path = None
        
        if body.thumbnail_url:
            # Download thumbnail from provided URL
            print(f"📥 Downloading provided thumbnail...")
            try:
                r = req_lib.get(body.thumbnail_url, timeout=30)
                if r.status_code == 200:
                    thumbnail_bytes = r.content
            except Exception as e:
                print(f"⚠️ Failed to download thumbnail: {e}")
        
        if not thumbnail_bytes:
            # Generate thumbnail with Imagen (optimized for YouTube Shorts 9:16)
            print("🖼️ Generating YouTube Shorts thumbnail with AI...")
            try:
                thumbnail_bytes, thumbnail_path = get_gemini().generate_thumbnail(
                    title=final_title,
                    description=final_description,
                    original_prompt=original_prompt
                )
                
                # Save thumbnail path to video_jobs metadata
                if thumbnail_path:
                    try:
                        current_metadata = job.data.get("metadata")
                        if isinstance(current_metadata, str):
                            current_metadata = json.loads(current_metadata)
                        elif current_metadata is None:
                            current_metadata = {}
                        
                        current_metadata["thumbnail_path"] = thumbnail_path
                        
                        get_supabase().table("video_jobs").update({
                            "metadata": json.dumps(current_metadata)
                        }).eq("id", job_id).execute()
                        print(f"💾 Thumbnail path saved to metadata: {thumbnail_path}")
                    except Exception as e:
                        print(f"⚠️ Failed to save thumbnail path to metadata: {e}")
                        
            except Exception as e:
                print(f"⚠️ Thumbnail generation failed: {e}")
                # Continue without thumbnail - YouTube will auto-generate one
        
        # 7. Upload to YouTube with thumbnail
        print(f"🚀 Uploading to YouTube...")
        result = get_youtube().upload_video_with_thumbnail(
            file_path=temp_video_path,
            title=final_title,
            description=final_description,
            credentials_dict=tokens,
            privacy=final_privacy,
            tags=final_tags,
            schedule_time=schedule_time_iso,
            thumbnail_bytes=thumbnail_bytes
        )
        
        # 8. Cleanup temp file
        try:
            os.remove(temp_video_path)
        except:
            pass
        
        # 9. Return response
        if result.success:
            return YouTubeUploadResponse(
                success=True,
                youtube_id=result.youtube_id,
                youtube_url=result.youtube_url,
                title=final_title,
                description=final_description,
                scheduled_for=schedule_time_iso,
                scheduled_for_display=schedule_time_display,
                thumbnail_uploaded=result.thumbnail_uploaded
            )
        else:
            return YouTubeUploadResponse(
                success=False,
                error=result.error
            )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ YouTube upload error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ============= YOUTUBE AUTH ENDPOINTS =============

@app.get("/api/auth/youtube/url")
async def get_youtube_auth_url(request: Request):
    token_user_id = await _get_authenticated_user_id(request)
    url = get_youtube().get_auth_url(user_id=token_user_id)
    return {"url": url}

@app.get("/api/auth/youtube/callback")
async def youtube_auth_callback(code: str, state: str):
    """
    Callback from Google. 'state' is the user_id we passed.
    """
    try:
        user_id = state
        credentials = get_youtube().get_credentials_from_code(code)
        
        # Convert credentials to dict - ensure ALL required fields are saved
        creds_dict = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': list(credentials.scopes) if credentials.scopes else []
        }
        
        # Validate that we got a refresh_token (required for long-term access)
        if not creds_dict.get('refresh_token'):
            print("⚠️ Warning: No refresh_token received from Google. User may need to revoke app access and reconnect.")
        
        # Log credential fields for debugging (not values, just keys)
        print(f"📝 Storing YouTube credentials with fields: {list(creds_dict.keys())}")
        print(f"📝 Refresh token present: {bool(creds_dict.get('refresh_token'))}")
        print(f"📝 Token URI: {creds_dict.get('token_uri')}")
        
        # Store in DB
        get_supabase().table("profiles").update({
            "youtube_tokens": creds_dict
        }).eq("id", user_id).execute()
        
        return {"status": "success", "message": "YouTube connected successfully"}
        
    except Exception as e:
        print(f"❌ YouTube callback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/auth/youtube/disconnect")
async def disconnect_youtube(request: Request):
    """
    Disconnect YouTube account by clearing stored tokens.
    User will need to reconnect to upload videos again.
    """
    try:
        token_user_id = await _get_authenticated_user_id(request)
        
        # Clear YouTube tokens
        get_supabase().table("profiles").update({
            "youtube_tokens": None
        }).eq("id", token_user_id).execute()
        
        print(f"🔌 YouTube disconnected for user {token_user_id}")
        return {"status": "success", "message": "YouTube account disconnected successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ YouTube disconnect error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/auth/youtube/status")
async def get_youtube_status(request: Request):
    """
    Check if the user has a valid YouTube connection.
    """
    try:
        token_user_id = await _get_authenticated_user_id(request)
        
        user = get_supabase().table("profiles").select("youtube_tokens").eq("id", token_user_id).single().execute()
        
        if not user.data or not user.data.get("youtube_tokens"):
            return {"connected": False, "valid": False, "message": "YouTube not connected"}
        
        tokens = user.data["youtube_tokens"]
        
        # Check for required fields
        required_fields = ['token', 'refresh_token', 'token_uri', 'client_id', 'client_secret']
        missing_fields = [f for f in required_fields if not tokens.get(f)]
        
        if missing_fields:
            return {
                "connected": True,
                "valid": False,
                "message": f"Connection incomplete. Missing: {', '.join(missing_fields)}. Please reconnect."
            }
        
        return {"connected": True, "valid": True, "message": "YouTube connected and ready"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ YouTube status check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============= STRIPE ENDPOINTS =============

@app.post("/api/stripe/create-checkout")
async def create_checkout_session(req: CheckoutRequest, request: Request):
    """
    Créer une session Stripe Checkout pour abonnement
    
    Supports both PROFESSIONAL and CREATOR tier plans with monthly AND yearly billing:
    
    PROFESSIONAL plans:
    - starter: 199€/month or 179€/month yearly (600 credits)
    - pro: 589€/month or 530€/month yearly (1200 credits)
    - max: 1199€/month or 1079€/month yearly (1800 credits)
    
    CREATOR plans:
    - creator_basic: 34.99€/month or 31.49€/month yearly (100 credits)
    - creator_pro: 65.99€/month or 59.39€/month yearly (200 credits)
    - creator_max: 89.99€/month or 80.99€/month yearly (300 credits)
    
    Plan names can include interval suffix: 'creator_basic_yearly', 'pro_annual', etc.
    """
    # Auth: derive user_id from JWT and ignore body value
    token_user_id = await _get_authenticated_user_id(request)
    req.user_id = token_user_id
    
    config = get_stripe_config()
    
    # Parse plan name and interval
    plan_name = req.plan
    interval = "monthly"
    
    # Check for interval suffix
    if plan_name.endswith("_yearly") or plan_name.endswith("_annual"):
        interval = "yearly" if plan_name.endswith("_yearly") else "annual"
        plan_name = plan_name.replace("_yearly", "").replace("_annual", "")
    
    # Map plan name to price ID
    price_id = None
    
    # Creator plans (use _YEARLY suffix)
    if plan_name == "creator_basic":
        price_id = config.PRICE_BASIC_YEARLY if interval in ["yearly", "annual"] else config.PRICE_BASIC_MONTHLY
    elif plan_name == "creator_pro":
        price_id = config.PRICE_PRO_YEARLY if interval in ["yearly", "annual"] else config.PRICE_PRO_MONTHLY
    elif plan_name == "creator_max":
        price_id = config.PRICE_MAX_YEARLY if interval in ["yearly", "annual"] else config.PRICE_MAX_MONTHLY
    # Professional plans (use _ANNUAL suffix)
    elif plan_name == "starter":
        price_id = config.PRICE_STARTER_ANNUAL if interval in ["yearly", "annual"] else config.PRICE_STARTER
    elif plan_name == "pro":
        price_id = config.PRICE_PRO_ANNUAL if interval in ["yearly", "annual"] else config.PRICE_PRO
    elif plan_name == "max":
        price_id = config.PRICE_MAX_ANNUAL if interval in ["yearly", "annual"] else config.PRICE_MAX
    
    if not price_id:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid plan: {req.plan}. Valid plans: creator_basic, creator_pro, creator_max, starter, pro, max (with optional _yearly/_annual suffix)"
        )
    
    # Get plan info from config
    plan_info = get_plan_type(price_id)
    if not plan_info:
        raise HTTPException(status_code=500, detail=f"Price ID {price_id} not configured in Stripe")
    
    # Determine tier type for metadata
    tier_type = plan_info['planFamily']
    internal_plan_name = config.get_plan_name_from_price_id(price_id)
    
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            allow_promotion_codes=True,
            success_url=f"{os.getenv('FRONTEND_URL', 'https://vykso.lovable.app')}/payment-success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{os.getenv('FRONTEND_URL', 'https://vykso.lovable.app')}/pricing",
            client_reference_id=req.user_id,
            metadata={
                'user_id': req.user_id,
                'userId': req.user_id,
                'plan': internal_plan_name,
                'tier': plan_info['tier'],
                'planFamily': tier_type,
                'interval': plan_info['interval'],
                'credits': str(plan_info['credits']),
                'type': 'subscription'
            },
            subscription_data={
                'metadata': {
                    'user_id': req.user_id,
                    'userId': req.user_id,
                    'plan': internal_plan_name,
                    'tier': plan_info['tier'],
                    'planFamily': tier_type,
                    'credits': str(plan_info['credits']),
                }
            }
        )
        
        print(f"✅ Checkout session created for {plan_info['name']}")
        print(f"   Plan: {internal_plan_name} ({tier_type})")
        print(f"   Interval: {plan_info['interval']}")
        print(f"   Credits: {plan_info['credits']}")
        
        return {"checkout_url": session.url}
    
    except Exception as e:
        print(f"❌ Stripe error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stripe/buy-credits")
async def buy_credits(req: BuyCreditsRequest, request: Request):
    """Acheter des crédits ponctuels (pas d'abonnement)"""
    # Auth required
    token_user_id = await _get_authenticated_user_id(request)
    # Security: ignore body user_id, use token subject
    req.user_id = token_user_id

    # Basic server-side validation for credits/amount
    if req.credits <= 0 or req.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid credits or amount")
    # Optional: map fixed packs for safety
    packs = {
        60: 9,    # example: 60 credits -> 9 EUR
        120: 15,
        300: 29,
    }
    # If pack exists, enforce price; otherwise allow custom amount (comment to restrict strictly)
    if req.credits in packs and packs[req.credits] != req.amount:
        raise HTTPException(status_code=400, detail="Invalid amount for selected credits pack")

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'product_data': {
                        'name': f'{req.credits} Vykso Credits',
                        'description': f'{req.credits // 6} videos of 60s'
                    },
                    'unit_amount': req.amount * 100
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f"{os.getenv('FRONTEND_URL', 'https://vykso.lovable.app')}/payment-success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{os.getenv('FRONTEND_URL', 'https://vykso.lovable.app')}/credits",
            client_reference_id=req.user_id,
            metadata={
                'user_id': req.user_id,
                'credits': str(req.credits),
                'type': 'credit_purchase'
            }
        )
        
        return {"checkout_url": session.url}
    
    except Exception as e:
        print(f"❌ Stripe error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/webhooks/stripe-legacy")
async def stripe_webhook_legacy(request: Request):
    """
    Legacy Webhook Stripe endpoint (kept for backward compatibility).
    
    The main webhook handler is now in routes/webhook.py
    This endpoint handles the same events but with the old logic.
    """
    
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.getenv("STRIPE_WEBHOOK_SECRET")
        )
    except ValueError as e:
        print(f"❌ Invalid payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        print(f"❌ Invalid signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    config = get_stripe_config()
    print(f"📨 Received Stripe webhook (legacy): {event['type']}")
    
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        metadata = session.get('metadata', {})
        user_id = metadata.get('user_id') or metadata.get('userId')
        
        if metadata.get('type') == 'credit_purchase':
            credits_to_add = int(metadata.get('credits', 0))
            
            print(f"💳 Credit purchase: {credits_to_add} credits for user {user_id}")
            
            try:
                add_credits_to_user(user_id, credits_to_add)
                print(f"✅ Added {credits_to_add} credits to user {user_id}")
            except Exception as e:
                print(f"❌ Error adding credits: {e}")
        
        elif metadata.get('type') == 'subscription':
            subscription_id = session.get('subscription')
            customer_id = session.get('customer')
            
            # Get plan info from metadata or fetch from Stripe
            plan = metadata.get('plan')
            tier_type = metadata.get('planFamily') or metadata.get('tier_type', 'professional')
            credits = int(metadata.get('credits', 0))
            
            # If credits not in metadata, get from config
            if credits == 0:
                credits = config.get_credits_for_plan(plan)
            
            # Fallback to old mapping if still 0
            if credits == 0:
                professional_credits_map = {
                    "starter": 600, "starter_annual": 600,
                    "pro": 1200, "pro_annual": 1200,
                    "max": 1800, "max_annual": 1800
                }
                creator_credits_map = {
                    "creator_basic": 100, "creator_basic_yearly": 100,
                    "creator_pro": 200, "creator_pro_yearly": 200,
                    "creator_max": 300, "creator_max_yearly": 300
                }
                credits_map = {**professional_credits_map, **creator_credits_map}
                credits = credits_map.get(plan, 100 if tier_type == "creator" else 600)
            
            print(f"✅ Subscription {plan} ({tier_type} tier) for user {user_id}")
            
            try:
                update_user_subscription(user_id, {
                    'plan': plan,
                    'credits': credits,
                    'stripe_customer_id': customer_id,
                    'stripe_subscription_id': subscription_id,
                    'status': 'active',
                    'plan_family': tier_type,
                })
                
                print(f"✅ User {user_id} upgraded to {plan} ({tier_type} tier) with {credits} credits")
            except Exception as e:
                print(f"❌ Error updating user: {e}")
    
    elif event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        subscription_id = invoice.get('subscription')
        billing_reason = invoice.get('billing_reason')
        
        if subscription_id and billing_reason == 'subscription_cycle':
            try:
                user = get_user_by_stripe_subscription(subscription_id)
                
                if user:
                    plan = user.get('plan', 'free')
                    
                    # Get credits from config
                    credits = config.get_credits_for_plan(plan)
                    
                    # Fallback to old mapping
                    if credits == 0:
                        professional_credits_map = {
                            "starter": 600, "starter_annual": 600,
                            "pro": 1200, "pro_annual": 1200,
                            "max": 1800, "max_annual": 1800
                        }
                        creator_credits_map = {
                            "creator_basic": 100, "creator_basic_yearly": 100,
                            "creator_pro": 200, "creator_pro_yearly": 200,
                            "creator_max": 300, "creator_max_yearly": 300
                        }
                        credits_map = {**professional_credits_map, **creator_credits_map}
                        tier_type = "creator" if plan.startswith("creator_") else "professional"
                        credits = credits_map.get(plan, 100 if tier_type == "creator" else 600)
                    
                    update_user_subscription(user['id'], {'credits': credits})
                    
                    print(f"✅ Monthly credits recharged for user {user['id']}: {credits} credits")
            except Exception as e:
                print(f"❌ Error recharging credits: {e}")
    
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        metadata = subscription.get('metadata', {})
        user_id = metadata.get('user_id') or metadata.get('userId')
        
        if not user_id:
            user = get_user_by_stripe_subscription(subscription['id'])
            if user:
                user_id = user.get('id')
        
        if user_id:
            print(f"🚫 Subscription canceled for user {user_id}")
            update_user_subscription(user_id, {
                'status': 'canceled',
                'credits': 0,
                'plan': 'free',
            })
    
    return {"status": "success"}

@app.get("/api/videos/{job_id}/download")
async def download_video(job_id: str, request: Request):
    """Télécharge une vidéo directement depuis la plateforme (proxy + streaming, supporte gros fichiers)."""
    try:
        # Require auth and ensure ownership
        token_user_id = await _get_authenticated_user_id(request)
        job = get_supabase().table("video_jobs").select("video_url, niche, created_at, user_id").eq("id", job_id).single().execute()
        if not job.data:
            raise HTTPException(status_code=404, detail="Video not found")

        if job.data.get("user_id") != token_user_id:
            raise HTTPException(status_code=403, detail="Forbidden")

        video_url = job.data.get("video_url")
        if not video_url:
            raise HTTPException(status_code=404, detail="Video URL not available")

        object_path = _extract_object_path_from_public_url(video_url, VIDEOS_BUCKET)
        if not object_path:
            # Fallback: try to use the filename from URL
            object_path = video_url.rstrip("/").split("/")[-1]

        # Build filename
        niche = job.data.get("niche", "video")
        created_at = job.data.get("created_at", "")[:10]
        filename = f"vykso_{niche}_{created_at}_{job_id[:8]}.mp4"

        # Proxy with range support
        range_header = request.headers.get("range") or request.headers.get("Range")
        stream_resp = await _proxy_supabase_object_stream(object_path, range_header)
        # Force attachment disposition for downloads
        stream_resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return stream_resp

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Download error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/videos/{job_id}/stream")
async def stream_video(job_id: str, request: Request):
    """Stream vidéo pour lecture dans le player (Range + proxy, pas d'URL externe)."""
    try:
        # Require auth and ensure ownership
        token_user_id = await _get_authenticated_user_id(request)
        job = get_supabase().table("video_jobs").select("video_url, user_id").eq("id", job_id).single().execute()
        if not job.data:
            raise HTTPException(status_code=404, detail="Video not found")

        if job.data.get("user_id") != token_user_id:
            raise HTTPException(status_code=403, detail="Forbidden")

        video_url = job.data.get("video_url")
        if not video_url:
            raise HTTPException(status_code=404, detail="Video URL not available")

        object_path = _extract_object_path_from_public_url(video_url, VIDEOS_BUCKET)
        if not object_path:
            object_path = video_url.rstrip("/").split("/")[-1]

        range_header = request.headers.get("range") or request.headers.get("Range")
        return await _proxy_supabase_object_stream(object_path, range_header)

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Stream error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload-image")
async def upload_image_to_supabase(request: Request, file: UploadFile = File(...)):
    """Upload une image vers Supabase Storage"""
    try:
        # Require auth
        await _get_authenticated_user_id(request)
        # Vérifier le type de fichier
        allowed_types = ["image/jpeg", "image/png", "image/webp"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid file type. Allowed: {', '.join(allowed_types)}"
            )
        
        # Lire le contenu
        contents = await file.read()
        
        # Vérifier la taille (max 10MB)
        max_size = 10 * 1024 * 1024  # 10MB
        if len(contents) > max_size:
            raise HTTPException(
                status_code=400, 
                detail=f"File too large. Max size: {max_size / 1024 / 1024}MB"
            )
        
        # Générer un nom unique
        import uuid
        file_ext = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        filename = f"{uuid.uuid4()}.{file_ext}"
        
        print(f"📤 Uploading image to Supabase: {filename}")
        
        # Upload vers Supabase Storage
        from supabase import create_client
        supabase_client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_KEY")
        )
        
        supabase_client.storage.from_("video-images").upload(
            filename,
            contents,
            {
                "content-type": file.content_type,
                "cache-control": "public, max-age=31536000"
            }
        )
        
        # Générer l'URL publique
        public_url = supabase_client.storage.from_("video-images").get_public_url(filename)
        
        print(f"✅ Image uploaded: {public_url}")
        
        return {
            "url": public_url,
            "filename": filename
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
