import os
import json
import uuid
import asyncio
import tempfile
import httpx
import logging
from datetime import datetime, timezone, timedelta
from fastapi.responses import StreamingResponse, RedirectResponse
from typing import Optional, List, Dict, Literal
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sora_client import SoraClient, closest_sora_size
from veo_client import VeoAIClient
from wan_client import WanVideoClient, wan_available
from supabase_client import get_client
from utils.auth import get_authenticated_user_id
from utils.notify import notify_event
from utils.supabase_uploader import SupabaseVideoUploader
from utils.video_concat import VideoEditor
from utils.content_generator import ContentGenerator, ScheduleCalculator
from gemini_client import GeminiClient
from youtube_client import YouTubeClient, make_oauth_state, verify_oauth_state
from io import BytesIO
from starlette.requests import Request as StarletteRequest
from starlette.responses import StreamingResponse as StarletteStreamingResponse
from urllib.parse import urlparse

# ========= LOGGING FILTER FOR 401 ERRORS =========
# Filter out 401 Unauthorized from uvicorn access logs to reduce noise
# These are expected when frontend polls with expired tokens
class Filter401Responses(logging.Filter):
    """Filter to suppress 401 Unauthorized responses from access logs."""
    def filter(self, record: logging.LogRecord) -> bool:
        # Check if the log message contains 401 status code
        message = record.getMessage()
        if "401" in message and ("/status" in message or "Unauthorized" in message):
            return False  # Don't log this message
        return True  # Log everything else

# Apply filter to uvicorn access logger
uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.addFilter(Filter401Responses())

# Stripe routes (canonical payment endpoints live in routes/)
from routes.checkout import router as checkout_router
from routes.webhook import router as webhook_router

app = FastAPI(
    title="Vykso API",
    description="API de génération vidéo automatique via Sora 2",
    version="1.0.0"
)

# ========= RATE LIMITING (slowapi) =========
# Global default: 60 req/min per IP; stricter limits on generation/upload endpoints.
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS — explicit origins (no empty strings), methods and headers restricted
_cors_origins = [
    "http://localhost:3000",
    "https://vykso.com",
    "https://www.vykso.com",
    os.getenv("FRONTEND_URL", "https://vykso.com"),
]
_cors_origins = list(dict.fromkeys(o for o in _cors_origins if o))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Include Stripe routes
# IMPORTANT: Webhook route must be included to receive raw body for signature verification
app.include_router(checkout_router)
app.include_router(webhook_router)

# Le webhook Stripe est protégé par signature, pas par IP : il doit rester hors
# du rate-limit global (un batch de renouvellements Stripe dépasserait 60/min).
from routes.webhook import stripe_webhook as _stripe_webhook_endpoint
limiter.exempt(_stripe_webhook_endpoint)

# Clients - Lazy initialization to prevent startup crashes
# These will be initialized on first use, allowing the server to start
# even if some API keys are not configured

_sora = None
_veo = None
_wan = None
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

def get_wan():
    global _wan
    if _wan is None:
        _wan = WanVideoClient()
    return _wan

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

# ========= VIDEO STREAMING/PROXY HELPERS =========
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
VIDEOS_BUCKET = os.getenv("VIDEOS_BUCKET", "vykso-videos")

# Auth helper now lives in utils/auth.py (shared with routes/) — re-exported
# under the historical name used by all call sites in this file.
_get_authenticated_user_id = get_authenticated_user_id

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
    # Wan 2.2 (self-hosted, experimental)
    "wan-2.2": "wan-2.2",
    "wan2.2": "wan-2.2",
    "wan 2.2": "wan-2.2",
    "wan": "wan-2.2",
    "wan2gp": "wan-2.2",
    "local": "wan-2.2",
}

VALID_AI_MODELS = ["sora-2", "sora-2-pro", "veo-3.1-generate-preview", "veo-3.1-fast-generate-preview", "wan-2.2"]

VEO_MODELS = ("veo-3.1-generate-preview", "veo-3.1-fast-generate-preview")
SORA_MODELS = ("sora-2", "sora-2-pro")

def normalize_ai_model(value: str) -> str:
    """Normalize AI model name to the expected format.

    Unknown model → HTTPException 400 (no silent default).
    'wan-2.2' is only valid when WAN_ENDPOINT is configured.
    """
    if not value:
        raise HTTPException(status_code=400, detail="Modèle IA manquant (ai_model)")

    normalized = str(value).lower().strip()

    canonical = AI_MODEL_ALIASES.get(normalized)
    if canonical is None and normalized in VALID_AI_MODELS:
        canonical = normalized

    if canonical is None:
        raise HTTPException(
            status_code=400,
            detail=f"Modèle IA inconnu: '{value}'. Modèles valides: {', '.join(VALID_AI_MODELS)}"
        )

    if canonical == "wan-2.2" and not wan_available():
        raise HTTPException(status_code=400, detail="Modèle Wan non configuré (WAN_ENDPOINT)")

    return canonical


# ============= USER TIER SYSTEM =============
# Source of truth: profiles.plan_family ('creator' | 'professional').
# Fallback: plan name prefix 'professional_' (new taxonomy:
# free, creator_basic, creator_pro, creator_max,
# professional_starter, professional_pro, professional_max).

def get_user_tier(profile) -> str:
    """
    Determines user tier from the profile row.

    Priority:
    1. profiles.plan_family ('professional' → professional, 'creator' → creator)
    2. Fallback: plan name prefix 'professional_'

    Accepts either a profile dict or a plan string (legacy call form).

    Returns:
        "professional" for ad-focused plans (16:9)
        "creator" for TikTok/Shorts focused plans (9:16)
    """
    plan = ""
    if isinstance(profile, dict):
        family = (profile.get("plan_family") or "").strip().lower()
        if family == "professional":
            return "professional"
        if family == "creator":
            return "creator"
        plan = profile.get("plan") or ""
    elif profile:
        plan = str(profile)

    if plan.strip().lower().startswith("professional_"):
        return "professional"
    return "creator"

def get_fixed_duration_for_creator(ai_model: str) -> int:
    """
    Returns fixed duration for Creator tier users.
    Creator users cannot change duration - it's fixed based on model.

    All models (Veo, Sora, Wan) now use 8-second segments
    (F-07: 10s is not a valid Sora duration — valid values are 4/8/12).
    """
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


class VideoRequest(BaseModel):
    user_id: str  # Ignored server-side; derived from JWT
    niche: Optional[str] = None
    duration: int = Field(ge=4, le=64)
    quality: Literal["basic", "pro_720p", "pro_1080p"] = "basic"
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

class StoryboardShot(BaseModel):
    Scene: str
    duration: float

class VideoRequestAdvanced(BaseModel):
    model_config = {"protected_namespaces": ()}

    user_id: str  # Ignored server-side; derived from JWT
    niche: Optional[str] = None
    duration: int = Field(default=8, ge=4, le=64)
    quality: Literal["basic", "pro_720p", "pro_1080p"] = "basic"
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

# All providers (Veo, Sora, Wan) generate and bill 8-second segments,
# so billed == generated (F-07).
SEGMENT_SECONDS = 8

# Maximum total video duration (professional tier) — 64s everywhere (8 segments)
MAX_VIDEO_DURATION = 64
MIN_VIDEO_DURATION = 4

def per_segment_credits(quality: str, ai_model: str = "veo-3.1-generate-preview") -> int:
    """Coût en crédits d'UN segment généré (8s) selon la qualité et le modèle."""
    if ai_model == "wan-2.2":
        return 1  # Wan (expérimental, auto-hébergé) est facturé au tarif 'basic'
    return {"basic": 1, "pro_720p": 3, "pro_1080p": 5}.get(quality, 1)

def num_segments_for_duration(duration: int) -> int:
    """Nombre de segments de 8s nécessaires pour couvrir la durée demandée."""
    return max(1, (int(duration) + SEGMENT_SECONDS - 1) // SEGMENT_SECONDS)

def calculate_credits_cost(duration: int, quality: str, ai_model: str = "veo-3.1-generate-preview") -> int:
    """Calcule le coût en crédits : segments générés × coût par segment.

    Tous les modèles utilisent des segments de 8s (veo=8, sora=8, wan=8),
    donc le nombre de segments facturés == le nombre de segments générés.
    """
    return num_segments_for_duration(duration) * per_segment_credits(quality, ai_model)

def _validate_duration_and_model(duration: int, ai_model: str):
    if duration < MIN_VIDEO_DURATION or duration > MAX_VIDEO_DURATION:
        raise HTTPException(
            status_code=400,
            detail=f"La durée doit être comprise entre {MIN_VIDEO_DURATION} et {MAX_VIDEO_DURATION} secondes"
        )


def get_tier_config(user_tier: str, ai_model: str) -> dict:
    """
    Get configuration parameters based on user tier.

    Returns dict with:
    - keyframes_per_sequence: 2 (START + END only — F-06: MIDDLE keyframes
      were generated then discarded, they are skipped entirely now)
    - transitions: whether to add crossfade transitions
    - transition_duration: duration of crossfade in seconds
    - resolution: video resolution
    - max_duration: maximum video duration in seconds (64s for professional)
    """
    # Base configs by tier
    if user_tier == "creator":
        # Creator tier - TikTok/Shorts optimized
        return {
            "keyframes_per_sequence": 2,  # START + END only
            "transitions": False,
            "transition_duration": 0.0,
            "resolution": "720p",
            "max_duration": SEGMENT_SECONDS,  # Single fixed 8s video
        }
    else:
        # Professional tier - ads/commercials
        return {
            "keyframes_per_sequence": 2,  # START + END only (F-06)
            "transitions": True,
            "transition_duration": 0.3,
            "resolution": "1080p",
            "max_duration": MAX_VIDEO_DURATION,  # Up to 8 sequences (64s)
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

# ============= JOB / CREDITS HELPERS =============

_video_semaphore: Optional[asyncio.Semaphore] = None

def get_video_semaphore() -> asyncio.Semaphore:
    """Global semaphore limiting concurrent shot/segment generations (per process)."""
    global _video_semaphore
    if _video_semaphore is None:
        _video_semaphore = asyncio.Semaphore(int(os.getenv("VIDEO_MAX_CONCURRENT_SHOTS", "3")))
    return _video_semaphore


def _parse_job_metadata(raw) -> dict:
    """Parse video_jobs.metadata, tolerant des deux formats (dict nouveau / string JSON legacy)."""
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


def _refund_credits(user_id: str, amount: int) -> bool:
    """Rembourse des crédits via la RPC atomique. Ne lève jamais — retourne True/False."""
    if not user_id or amount <= 0:
        return False
    try:
        get_supabase().rpc("refund_credits", {
            "p_user_id": user_id,
            "p_amount": amount,
        }).execute()
        print(f"💰 Refunded {amount} credits to user {user_id}")
        return True
    except Exception as e:
        print(f"❌ Error refunding credits to {user_id}: {e}")
        return False


def _fail_job_and_refund(job_id: str, error_message: str, notify_label: str = "Job vidéo échoué"):
    """Marque un job en échec et rembourse le credits_cost STOCKÉ (pas recalculé).

    Garde anti-double-remboursement :
    - ne rembourse que si metadata.refunded n'est pas déjà true ;
    - déduit les crédits déjà remboursés au prorata (metadata.refunded_credits) ;
    - écrit metadata.refunded=true dans le MÊME update qui passe le job en failed.
    """
    row = None
    try:
        res = get_supabase().table("video_jobs").select(
            "user_id, credits_cost, metadata"
        ).eq("id", job_id).maybe_single().execute()
        row = res.data if res else None
    except Exception as e:
        print(f"❌ Failure handler: unable to load job {job_id}: {e}")

    metadata = _parse_job_metadata(row.get("metadata")) if row else {}
    user_id = row.get("user_id") if row else None
    refunded_now = 0

    if row and not metadata.get("refunded"):
        stored_cost = int(row.get("credits_cost") or 0)
        already_refunded = int(metadata.get("refunded_credits") or 0)
        amount = max(0, stored_cost - already_refunded)
        if amount > 0 and _refund_credits(user_id, amount):
            refunded_now = amount
            metadata["refunded_credits"] = already_refunded + amount

    update_payload = {
        "status": "failed",
        "error": error_message,
    }
    if row is not None:
        # N'écraser la metadata que si on a pu la charger (sinon on perdrait
        # les infos existantes et on bloquerait un futur remboursement légitime)
        metadata["refunded"] = True
        update_payload["metadata"] = metadata
    try:
        get_supabase().table("video_jobs").update(update_payload).eq("id", job_id).execute()
    except Exception as e:
        print(f"❌ Unable to mark job {job_id} as failed: {e}")

    # Best-effort notification (notify_event ne lève jamais)
    notify_event(notify_label, {
        "job_id": job_id,
        "user_id": user_id or "inconnu",
        "erreur": (error_message or "")[:300],
        "crédits remboursés": refunded_now,
    })


def _pil_to_png_bytes(pil_image) -> bytes:
    """Sérialise une image PIL en bytes PNG (conversion de mode si nécessaire)."""
    img = pil_image
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _merge_segment_prompts(segment: dict, fallback_prompt: str) -> dict:
    """F-39 : fusionne les shots d'un segment de script en UNE seule génération.

    Les video_prompts des shots sont joints par ' Then ' ; l'image du premier
    shot sert de référence. Garantit 1 appel vidéo max par segment.
    """
    seg_shots = segment.get("shots") or []
    video_prompts = [s.get("video_prompt") for s in seg_shots if s.get("video_prompt")]
    merged_prompt = " Then ".join(video_prompts) if video_prompts else fallback_prompt
    first_shot = seg_shots[0] if seg_shots else {}
    return {
        "segment_index": segment.get("segment_index") or 0,
        "video_prompt": merged_prompt,
        "image_prompt": first_shot.get("image_prompt"),
        "use_user_image_index": first_shot.get("use_user_image_index"),
    }


def _update_job_progress(job_id: str, progress: int):
    """Met à jour video_jobs.progress (best-effort)."""
    try:
        get_supabase().table("video_jobs").update({
            "progress": max(0, min(100, int(progress)))
        }).eq("id", job_id).execute()
    except Exception as e:
        print(f"⚠️ Unable to update progress for job {job_id}: {e}")


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
    Génération vidéo par segments de 8s avec continuité visuelle.

    Trois providers :
    - Veo 3.1 (normal/fast) : keyframes START+END (F-06), séquentiel avec continuité
    - Sora 2 / Sora 2 Pro : 1 génération par segment (F-39), parallèle (sémaphore)
    - Wan 2.2 (auto-hébergé, expérimental) : séquentiel, continuité par dernière frame

    Crédits : le coût est stocké dans video_jobs.credits_cost à la création.
    - segments manquants/échoués → remboursement prorata (metadata.partial)
    - zéro clip → exception → remboursement intégral via _fail_job_and_refund
    Tous les fichiers temporaires vivent dans un TemporaryDirectory par job (F-18).
    """
    from PIL import Image

    loop = asyncio.get_running_loop()
    semaphore = get_video_semaphore()
    per_seg_cost = per_segment_credits(quality, ai_model)
    billed_segments = num_segments_for_duration(duration)
    base_prompt = custom_prompt or generate_prompt(niche, user_tier=user_tier)

    try:
        # F-18 : répertoire temporaire par job, nettoyé succès OU échec
        with tempfile.TemporaryDirectory(prefix=f"vykso_{job_id}_") as job_tmpdir:
            print(f"🎬 Starting generation for job {job_id}")
            print(f"🤖 AI Model: {ai_model} | type: {model_type} | tier: {user_tier.upper()}")

            get_supabase().table("video_jobs").update({
                "status": "generating"
            }).eq("id", job_id).execute()

            # ===== CONFIGURATION BY TIER =====
            tier_config = get_tier_config(user_tier, ai_model)
            aspect_ratio = get_aspect_ratio_for_tier(user_tier)
            add_transitions = tier_config.get("transitions", False)
            transition_duration = tier_config.get("transition_duration", 0.3)
            resolution = tier_config.get("resolution", "720p")
            print(f"📐 Config: {aspect_ratio}, {resolution}, transitions={add_transitions}, "
                  f"{billed_segments} segment(s) of {SEGMENT_SECONDS}s")

            # ===== DOWNLOAD USER IMAGES (async, F-17) =====
            user_pil_images = []
            if image_urls:
                async with httpx.AsyncClient(timeout=30) as http_client:
                    for img_url in image_urls[:18]:
                        try:
                            print(f"📥 Downloading user image: {img_url[:50]}...")
                            resp = await http_client.get(img_url)
                            resp.raise_for_status()
                            img = Image.open(BytesIO(resp.content))
                            img.load()
                            user_pil_images.append(img)
                        except Exception as e:
                            print(f"⚠️ Failed to download image: {e}")

            final_url = None
            ok_segments = 0

            # =========================================================
            # BRANCHE 1 : VEO 3.1 (keyframes START + END, séquentiel)
            # =========================================================
            if ai_model in VEO_MODELS:
                use_fast_model = (ai_model == "veo-3.1-fast-generate-preview")
                print(f"🎥 Veo 3.1 ({'FAST' if use_fast_model else 'NORMAL'}) — keyframe architecture (START+END)")

                # Script cinématique (le générateur peut retourner MOINS de séquences — prorata géré plus bas)
                script = await loop.run_in_executor(None, lambda: get_gemini().generate_cinematic_script(
                    user_prompt=base_prompt,
                    duration=duration,
                    user_images=image_urls,
                    user_tier=user_tier,
                    num_keyframes_per_sequence=2,  # F-06 : START + END uniquement
                ))
                if not script or "sequences" not in script:
                    print("⚠️ Script generation failed, using fallback method")
                    script = _create_fallback_script(base_prompt, billed_segments, aspect_ratio)

                sequences = (script.get("sequences") or [])[:billed_segments]
                print(f"✅ Script ready: {len(sequences)} sequence(s)")

                all_video_bytes = []
                previous_last_frame = None  # dernière frame de la vidéo précédente (continuité)

                for seq_idx, sequence in enumerate(sequences):
                    seq_num = seq_idx + 1
                    print(f"\n🎬 SEQUENCE {seq_num}/{len(sequences)}")
                    _update_job_progress(job_id, int((seq_idx / max(1, len(sequences))) * 100))

                    kf_start_prompt = sequence.get("keyframe_start", "")
                    kf_end_prompt = sequence.get("keyframe_end", "")
                    veo_prompt = sequence.get("veo_prompt", "") or base_prompt

                    try:
                        async with semaphore:
                            keyframes = []

                            # KEYFRAME START : frame précédente (continuité) OU génération
                            if previous_last_frame is not None:
                                print("  🔗 Using previous video's last frame as START keyframe")
                                keyframes.append(previous_last_frame)
                            else:
                                print("  🖼️ Generating START keyframe...")
                                ref_images = user_pil_images[:3] if user_pil_images else None
                                kf_start_bytes = await loop.run_in_executor(
                                    None,
                                    lambda p=kf_start_prompt, r=ref_images: get_gemini().generate_keyframe_image(
                                        keyframe_prompt=p,
                                        reference_images=r,
                                        aspect_ratio=aspect_ratio,
                                        position="START"
                                    )
                                )
                                if kf_start_bytes:
                                    keyframes.append(kf_start_bytes)

                            # KEYFRAME END (F-06 : pas de MIDDLE, il était jeté de toute façon)
                            print("  🖼️ Generating END keyframe...")
                            kf_end_bytes = await loop.run_in_executor(
                                None,
                                lambda p=kf_end_prompt: get_gemini().generate_keyframe_image(
                                    keyframe_prompt=p,
                                    reference_images=user_pil_images[:3] if user_pil_images else None,
                                    aspect_ratio=aspect_ratio,
                                    position="END"
                                )
                            )
                            if kf_end_bytes:
                                keyframes.append(kf_end_bytes)

                            if not keyframes:
                                print("  ⚠️ No keyframes generated, falling back to text-to-video")

                            video_path = os.path.join(job_tmpdir, f"seq{seq_num}.mp4")

                            if keyframes:
                                await loop.run_in_executor(
                                    None,
                                    lambda kf=list(keyframes), vp=video_path, p=veo_prompt: get_veo().generate_video_with_keyframes(
                                        prompt=p,
                                        keyframes=kf,
                                        aspect_ratio=aspect_ratio,
                                        resolution=resolution,
                                        duration_seconds=SEGMENT_SECONDS,
                                        download_path=vp,
                                        use_fast_model=use_fast_model,
                                    )
                                )
                            else:
                                await loop.run_in_executor(
                                    None,
                                    lambda vp=video_path, p=veo_prompt: get_veo().generate_video_and_wait(
                                        prompt=p,
                                        aspect_ratio=aspect_ratio,
                                        resolution=resolution,
                                        duration_seconds=SEGMENT_SECONDS,
                                        download_path=vp,
                                        use_fast_model=use_fast_model,
                                    )
                                )

                            with open(video_path, "rb") as f:
                                video_bytes = f.read()

                        all_video_bytes.append(video_bytes)
                        print(f"  ✅ Sequence {seq_num} generated: {len(video_bytes)} bytes")

                        # Continuité : extraire la dernière frame pour la séquence suivante
                        if seq_idx < len(sequences) - 1:
                            try:
                                previous_last_frame = await loop.run_in_executor(
                                    None,
                                    lambda vb=video_bytes: get_video_editor().extract_last_frame(vb)
                                )
                            except Exception as e:
                                print(f"  ⚠️ Failed to extract last frame: {e}")
                                previous_last_frame = None

                    except Exception as seq_err:
                        print(f"  ❌ Sequence {seq_num} failed: {seq_err}")
                        previous_last_frame = None

                ok_segments = len(all_video_bytes)
                if ok_segments == 0:
                    raise RuntimeError("Aucun clip n'a pu être généré (Veo)")

                if ok_segments == 1:
                    final_video_bytes = all_video_bytes[0]
                else:
                    print(f"🎞️ MERGING {ok_segments} sequences...")
                    final_video_bytes = await loop.run_in_executor(
                        None,
                        lambda: get_video_editor().concatenate_video_bytes(
                            all_video_bytes,
                            f"{job_id}_final.mp4",
                            add_transitions=add_transitions,
                            transition_duration=transition_duration
                        )
                    )

                print(f"📤 Uploading final video ({len(final_video_bytes)} bytes)...")
                final_url = await loop.run_in_executor(
                    None,
                    get_uploader().upload_bytes,
                    final_video_bytes,
                    f"{job_id}.mp4"
                )

            # =========================================================
            # BRANCHE 2 : WAN 2.2 (auto-hébergé, expérimental, séquentiel)
            # =========================================================
            elif ai_model == "wan-2.2":
                print("🎥 Wan 2.2 (self-hosted) — sequential 8s segments with last-frame continuity")
                # Taille selon le tier : vertical creator / horizontal professional
                wan_size = "720x1280" if user_tier == "creator" else "1280x720"

                script = await loop.run_in_executor(None, lambda: get_gemini().generate_video_script(
                    prompt=base_prompt,
                    duration=duration,
                    num_segments=billed_segments,
                    user_images=image_urls,
                    segment_duration=SEGMENT_SECONDS,
                    user_tier=user_tier,
                    images_per_segment=1
                ))

                segment_specs = []
                if script and "segments" in script:
                    for segment in (script.get("segments") or [])[:billed_segments]:
                        segment_specs.append(_merge_segment_prompts(segment, base_prompt))
                if not segment_specs:
                    print("⚠️ Script generation failed, falling back to simple prompts (Wan)")
                    for i in range(billed_segments):
                        suffix = f", scene {i + 1} of {billed_segments}, continuous narrative flow" if billed_segments > 1 else ""
                        segment_specs.append({
                            "segment_index": i + 1,
                            "video_prompt": f"{base_prompt}{suffix}",
                        })

                all_video_bytes = []
                # Première image : image utilisateur si fournie, sinon text-to-video
                previous_frame_bytes = _pil_to_png_bytes(user_pil_images[0]) if user_pil_images else None

                for i, spec in enumerate(segment_specs):
                    seg_num = i + 1
                    _update_job_progress(job_id, int((i / max(1, len(segment_specs))) * 100))
                    try:
                        async with semaphore:
                            seg_path = os.path.join(job_tmpdir, f"wan_seg{seg_num}.mp4")
                            input_bytes = previous_frame_bytes
                            await loop.run_in_executor(
                                None,
                                lambda p=spec["video_prompt"], ib=input_bytes, sp=seg_path: get_wan().generate_video_and_wait(
                                    prompt=p,
                                    input_image_bytes=ib,
                                    seconds=SEGMENT_SECONDS,
                                    size=wan_size,
                                    download_path=sp,
                                )
                            )
                            with open(seg_path, "rb") as f:
                                video_bytes = f.read()

                        all_video_bytes.append(video_bytes)
                        print(f"  ✅ Wan segment {seg_num} generated: {len(video_bytes)} bytes")

                        # Continuité : dernière frame du segment → image d'entrée du suivant
                        if i < len(segment_specs) - 1:
                            try:
                                previous_frame_bytes = await loop.run_in_executor(
                                    None,
                                    lambda vb=video_bytes: get_video_editor().extract_last_frame(vb)
                                )
                            except Exception as e:
                                print(f"  ⚠️ Failed to extract last frame (Wan): {e}")
                                previous_frame_bytes = None

                    except Exception as seg_err:
                        print(f"  ❌ Wan segment {seg_num} failed: {seg_err}")
                        previous_frame_bytes = None

                ok_segments = len(all_video_bytes)
                if ok_segments == 0:
                    raise RuntimeError("Aucun clip n'a pu être généré (Wan)")

                if ok_segments == 1:
                    final_video_bytes = all_video_bytes[0]
                else:
                    print(f"🎞️ MERGING {ok_segments} Wan segments...")
                    final_video_bytes = await loop.run_in_executor(
                        None,
                        lambda: get_video_editor().concatenate_video_bytes(
                            all_video_bytes,
                            f"{job_id}_final.mp4",
                            add_transitions=add_transitions,
                            transition_duration=transition_duration
                        )
                    )

                final_url = await loop.run_in_executor(
                    None,
                    get_uploader().upload_bytes,
                    final_video_bytes,
                    f"{job_id}.mp4"
                )

            # =========================================================
            # BRANCHE 3 : SORA 2 / SORA 2 PRO (1 génération par segment, parallèle)
            # =========================================================
            else:
                use_pro_model = (ai_model == "sora-2-pro")
                print(f"🎥 Sora 2 API ({'PRO' if use_pro_model else 'STANDARD'}) — one video per segment (F-39)")

                # F-01/F-02 : taille dérivée du tier (jamais 1920x1080, orientation = tier)
                size = closest_sora_size(aspect_ratio, quality, ai_model)
                print(f"📐 Sora size for {user_tier.upper()} tier: {size}")

                images_per_segment = 1 if user_tier == "creator" else 3
                script = await loop.run_in_executor(None, lambda: get_gemini().generate_video_script(
                    prompt=base_prompt,
                    duration=duration,
                    num_segments=billed_segments,
                    user_images=image_urls,
                    segment_duration=SEGMENT_SECONDS,  # F-07 : 8s (valeur valide de l'API)
                    user_tier=user_tier,
                    images_per_segment=images_per_segment
                ))

                # F-39 : jamais plus de billed_segments appels Sora ;
                # les shots multiples d'un segment sont fusionnés (' Then ')
                segment_specs = []
                if script and "segments" in script:
                    for segment in (script.get("segments") or [])[:billed_segments]:
                        segment_specs.append(_merge_segment_prompts(segment, base_prompt))

                if not segment_specs:
                    print("⚠️ Script generation failed, falling back to simple generation (Sora)")
                    enriched_prompt = await loop.run_in_executor(None, lambda: get_gemini().enrich_prompt(
                        base_prompt,
                        segment_context="Single video generation",
                        user_image_description=None,
                        user_tier=user_tier
                    ))
                    for i in range(billed_segments):
                        suffix = f", scene {i + 1} of {billed_segments}, continuous narrative flow" if billed_segments > 1 else ""
                        segment_specs.append({
                            "segment_index": i + 1,
                            "video_prompt": f"{enriched_prompt}{suffix}",
                            "image_prompt": None,
                            "use_user_image_index": 0 if (i == 0 and user_pil_images) else None,
                        })

                completed_counter = {"n": 0}

                async def process_sora_segment(spec: dict):
                    """1 segment = 1 image d'entrée (optionnelle) + 1 appel Sora (8s)."""
                    async with semaphore:
                        seg_idx = spec.get("segment_index") or 0
                        print(f"🎬 Processing Sora segment {seg_idx} ({user_tier.upper()}, {size})...")

                        input_reference = None

                        # Image utilisateur explicite ?
                        uui = spec.get("use_user_image_index")
                        if isinstance(uui, int) and 0 <= uui < len(user_pil_images):
                            print(f"  🖼️ Using user-provided image {uui}")
                            try:
                                # Redimensionnée à la taille EXACTE de la vidéo (F-03)
                                input_reference = SoraClient.resize_image_to(
                                    _pil_to_png_bytes(user_pil_images[uui]), size
                                )
                            except Exception as e:
                                print(f"  ⚠️ Failed to prepare user image: {e}")
                        elif spec.get("image_prompt"):
                            # Génération d'image Gemini (F-43 : 2K, pas 4K)
                            print(f"  📸 Generating input image (2K)...")
                            try:
                                ref_images = user_pil_images[:3] if user_pil_images else None
                                image_bytes = await loop.run_in_executor(
                                    None,
                                    lambda p=spec["image_prompt"], r=ref_images: get_gemini().generate_image(
                                        prompt=p,
                                        reference_images=r,
                                        aspect_ratio=aspect_ratio,
                                        resolution="2K"
                                    )
                                )
                                if image_bytes:
                                    input_reference = SoraClient.resize_image_to(image_bytes, size)
                                    try:
                                        await loop.run_in_executor(
                                            None, get_uploader().upload_bytes,
                                            input_reference, f"{job_id}_seg{seg_idx}_input.png"
                                        )
                                    except Exception:
                                        pass
                                else:
                                    print("  ⚠️ Image generation returned None, text-to-video")
                            except Exception as img_err:
                                print(f"  ⚠️ Image generation failed, text-to-video: {img_err}")
                                input_reference = None

                        local_path = os.path.join(job_tmpdir, f"seg{seg_idx}.mp4")
                        await loop.run_in_executor(
                            None,
                            lambda p=spec["video_prompt"], ir=input_reference, lp=local_path: get_sora().generate_video_and_wait(
                                prompt=p,
                                use_pro=use_pro_model,
                                size=size,
                                seconds=SEGMENT_SECONDS,
                                input_reference=ir,
                                download_path=lp,
                            )
                        )

                        with open(local_path, "rb") as f:
                            data = f.read()
                        url = await loop.run_in_executor(
                            None, get_uploader().upload_bytes, data, f"{job_id}_seg{seg_idx}.mp4"
                        )

                        completed_counter["n"] += 1
                        _update_job_progress(job_id, int(completed_counter["n"] / max(1, len(segment_specs)) * 90))
                        return (seg_idx, url)

                print(f"🚀 Launching {len(segment_specs)} Sora segment task(s) "
                      f"(max {int(os.getenv('VIDEO_MAX_CONCURRENT_SHOTS', '3'))} concurrent)...")
                results = await asyncio.gather(
                    *(process_sora_segment(spec) for spec in segment_specs),
                    return_exceptions=True
                )

                valid_results = []
                for res in results:
                    if isinstance(res, BaseException):
                        print(f"❌ Sora segment failed: {res}")
                    else:
                        valid_results.append(res)
                valid_results.sort(key=lambda x: x[0])
                all_clip_urls = [r[1] for r in valid_results]

                ok_segments = len(all_clip_urls)
                if ok_segments == 0:
                    raise RuntimeError("Aucun clip n'a pu être généré (Sora)")

                if ok_segments == 1:
                    final_url = all_clip_urls[0]
                else:
                    print(f"🎞️ Concatenating {ok_segments} Sora clips...")
                    concatenated_data = await loop.run_in_executor(
                        None,
                        lambda: get_video_editor().concatenate_videos(
                            all_clip_urls,
                            f"{job_id}.mp4",
                            add_transitions=add_transitions,
                            transition_duration=transition_duration
                        )
                    )
                    final_url = await loop.run_in_executor(
                        None, get_uploader().upload_bytes, concatenated_data, f"{job_id}.mp4"
                    )

            # =========================================================
            # FINALISATION COMMUNE : prorata + complétion
            # =========================================================
            if not final_url or ok_segments <= 0:
                raise RuntimeError("Aucun clip n'a pu être généré")

            # Fusionner la metadata existante (dict natif — pas de json.dumps, F-21)
            current_meta = {}
            try:
                meta_res = get_supabase().table("video_jobs").select("metadata").eq("id", job_id).maybe_single().execute()
                if meta_res and meta_res.data:
                    current_meta = _parse_job_metadata(meta_res.data.get("metadata"))
            except Exception:
                pass

            # F-16 : prorata — segments facturés mais non générés (échec OU script trop court).
            # Le montant remboursé est persisté IMMÉDIATEMENT (update dédiée) : si la
            # finalisation échoue ensuite, _fail_job_and_refund relit refunded_credits
            # en base et ne rembourse que le reste (pas de double remboursement).
            missing_segments = billed_segments - ok_segments
            if missing_segments > 0:
                refund_amount = missing_segments * per_seg_cost
                print(f"💰 Partial failure: {missing_segments}/{billed_segments} segment(s) missing, "
                      f"refunding {refund_amount} credit(s)...")
                if _refund_credits(user_id, refund_amount):
                    current_meta["refunded_credits"] = int(current_meta.get("refunded_credits") or 0) + refund_amount
                    current_meta["partial"] = True
                    current_meta["partial_note"] = (
                        f"{missing_segments} segment(s) sur {billed_segments} n'ont pas pu être générés — "
                        f"{refund_amount} crédit(s) remboursé(s)."
                    )
                    get_supabase().table("video_jobs").update(
                        {"metadata": current_meta}
                    ).eq("id", job_id).execute()

            # Complétion CONDITIONNELLE : uniquement si le job est encore actif.
            # Si le watchdog l'a déjà passé en failed (+ remboursé), on ne livre pas
            # par-dessus — sinon l'utilisateur aurait la vidéo ET le remboursement.
            completion = get_supabase().table("video_jobs").update({
                "status": "completed",
                "video_url": final_url,
                "progress": 100,
                "completed_at": datetime.now(timezone.utc).isoformat(),  # F-20
                "metadata": current_meta,
            }).eq("id", job_id).in_("status", ["pending", "generating"]).execute()

            if not (completion.data or []):
                print(f"⚠️ Job {job_id}: terminé mais déjà marqué failed (watchdog) — "
                      f"vidéo non livrée, remboursement conservé. URL orpheline: {final_url}")
                try:
                    notify_event("Job terminé après watchdog (vidéo orpheline)",
                                 {"job_id": job_id, "url": final_url})
                except Exception:
                    pass
            else:
                print(f"✅ Job {job_id} COMPLETED! URL: {final_url} "
                      f"({ok_segments}/{billed_segments} segments)")

    except Exception as e:
        print(f"❌ Error generating video {job_id}: {e}")
        import traceback
        traceback.print_exc()
        # Remboursement du credits_cost STOCKÉ + garde anti-double-remboursement + notification
        _fail_job_and_refund(job_id, str(e))

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

def _get_profile_or_404(user_id: str) -> dict:
    """Récupère le profil — PAS de création automatique (le trigger DB crée
    les profils à l'inscription ; la création explicite vit dans /api/users/sync)."""
    try:
        user = get_supabase().table("profiles").select("*").eq("id", user_id).maybe_single().execute()
        profile = user.data if user else None
    except Exception as e:
        print(f"❌ Error checking user: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    if not profile:
        raise HTTPException(status_code=404, detail="Profil introuvable — reconnectez-vous")
    return profile


def _check_active_job_limit(user_id: str):
    """429 si l'utilisateur a déjà trop de jobs actifs (pending/generating)."""
    max_active = int(os.getenv("MAX_ACTIVE_JOBS_PER_USER", "2"))
    try:
        res = get_supabase().table("video_jobs").select(
            "id", count="exact"
        ).eq("user_id", user_id).in_("status", ["pending", "generating"]).execute()
        active = res.count if res.count is not None else len(res.data or [])
    except Exception as e:
        print(f"⚠️ Unable to count active jobs for {user_id}: {e}")
        return
    if active >= max_active:
        raise HTTPException(
            status_code=429,
            detail=f"Trop de générations en cours ({active}). Attendez la fin de vos vidéos avant d'en lancer une nouvelle."
        )


def _decrement_credits_or_raise(user_id: str, amount: int):
    """Déduit les crédits atomiquement via la RPC.

    - La RPC lève 'INSUFFICIENT_CREDITS' si solde insuffisant → 402.
    - Elle retourne le solde restant (0 est légitime) → seule data None est une erreur.
    """
    try:
        decrement = get_supabase().rpc("decrement_credits", {
            "p_user_id": user_id,
            "p_amount": amount,
        }).execute()
    except Exception as e:
        msg = str(e)
        if "INSUFFICIENT_CREDITS" in msg or "insufficient credits" in msg.lower():
            raise HTTPException(
                status_code=402,
                detail=f"Crédits insuffisants. {amount} crédit(s) requis."
            )
        print(f"❌ Error decrementing credits: {e}")
        raise HTTPException(status_code=500, detail="Impossible de déduire les crédits")

    # remaining == 0 est un solde légitime : seule une réponse None est anormale
    if decrement is None or decrement.data is None:
        print(f"❌ decrement_credits returned no data for user {user_id}")
        raise HTTPException(status_code=500, detail="Impossible de déduire les crédits")


def _insert_job_or_refund(user_id: str, required_credits: int, job_row: dict) -> str:
    """Insère le job ; si l'insert échoue APRÈS le débit → remboursement avant 500."""
    try:
        job = get_supabase().table("video_jobs").insert(job_row).execute()
        return job.data[0]["id"]
    except Exception as e:
        print(f"❌ Error creating job (refunding {required_credits} credits): {e}")
        _refund_credits(user_id, required_credits)
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


def _reject_unsupported_combo(ai_model: str, model_type: str):
    """400 explicite pour les combos non supportés (au lieu de générer autre chose en silence)."""
    if model_type == "storyboard" and ai_model not in SORA_MODELS:
        raise HTTPException(
            status_code=400,
            detail="Le mode storyboard n'est pas pris en charge par ce modèle — utilisez Sora (sora-2 ou sora-2-pro)."
        )


@app.post("/api/videos/generate", response_model=VideoResponse)
@limiter.limit("10/minute")
async def generate_video(req: VideoRequest, background_tasks: BackgroundTasks, request: Request):
    """
    Endpoint principal : génère une vidéo de durée variable

    Handles two user tiers:
    - CREATOR tier: Fixed duration (8s), TikTok/Shorts optimized (9:16)
    - PROFESSIONAL tier: Variable duration up to 64s, ad-optimized (16:9)
    """
    # Auth: derive user_id from JWT
    token_user_id = await _get_authenticated_user_id(request)
    # Security: ignore body user_id and use token subject
    req.user_id = token_user_id

    # Profil requis (créé par le trigger DB à l'inscription — pas d'auto-création ici)
    user_data = _get_profile_or_404(req.user_id)
    user_tier = get_user_tier(user_data)
    print(f"👤 User: {req.user_id}, Credits: {user_data.get('credits')}, "
          f"Plan: {user_data.get('plan')}, Tier: {user_tier}")

    # For CREATOR tier: Force fixed duration (no choice)
    if user_tier == "creator":
        fixed_duration = get_fixed_duration_for_creator(req.ai_model)
        req.duration = fixed_duration
        print(f"👤 Creator tier detected - forcing duration to {fixed_duration}s")

    # Validate model/duration
    _validate_duration_and_model(req.duration, req.ai_model)

    if not req.niche and not req.custom_prompt:
        raise HTTPException(status_code=400, detail="Either niche or custom_prompt is required")

    # Limite de jobs actifs par utilisateur (avant tout débit)
    _check_active_job_limit(req.user_id)

    # Segments de 8s pour tous les modèles → facturé == généré
    num_clips = num_segments_for_duration(req.duration)
    required_credits = calculate_credits_cost(req.duration, req.quality, req.ai_model)

    # Deduct credits atomically BEFORE scheduling work (backend source of truth)
    _decrement_credits_or_raise(req.user_id, required_credits)

    job_id = _insert_job_or_refund(req.user_id, required_credits, {
        "user_id": req.user_id,
        "status": "pending",
        "niche": req.niche or "custom",
        "duration": req.duration,
        "quality": req.quality,
        "progress": 0,
        "credits_cost": required_credits,
        "prompt": req.custom_prompt or generate_prompt(req.niche, user_tier=user_tier),
        "metadata": {
            "num_clips": num_clips,
            "target_duration": req.duration,
            "custom_prompt": req.custom_prompt,
            "ai_model": req.ai_model,
            "user_tier": user_tier
        }
    })
    print(f"📋 Job created: {job_id}")

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
@limiter.limit("10/minute")
async def generate_video_advanced(req: VideoRequestAdvanced, background_tasks: BackgroundTasks, request: Request):
    """
    Endpoint avancé : supporte storyboard, image-to-video, etc.

    Handles two user tiers:
    - CREATOR tier: Fixed duration (8s), TikTok/Shorts optimized, 1-3 images
    - PROFESSIONAL tier: Variable duration up to 64s, ad-optimized, multiple sequences
    """
    # Auth: derive user_id from JWT
    token_user_id = await _get_authenticated_user_id(request)
    req.user_id = token_user_id

    # Profil requis (pas d'auto-création — voir /api/users/sync)
    user_data = _get_profile_or_404(req.user_id)
    user_tier = get_user_tier(user_data)

    # Combos non supportés → 400 explicite (au lieu d'une génération silencieusement différente)
    _reject_unsupported_combo(req.ai_model, req.model_type)

    # For CREATOR tier: Force fixed duration (no choice)
    if user_tier == "creator":
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

    # Limite de jobs actifs par utilisateur (avant tout débit)
    _check_active_job_limit(req.user_id)

    # Calculer le coût (segments de 8s pour tous les modèles)
    num_clips = num_segments_for_duration(req.duration)
    required_credits = calculate_credits_cost(req.duration, req.quality, req.ai_model)

    # Deduct credits BEFORE scheduling generation
    _decrement_credits_or_raise(req.user_id, required_credits)

    job_id = _insert_job_or_refund(req.user_id, required_credits, {
        "user_id": req.user_id,
        "status": "pending",
        "niche": req.niche or ("storyboard" if req.model_type == "storyboard" else "custom"),
        "duration": req.duration,
        "quality": req.quality,
        "progress": 0,
        "credits_cost": required_credits,
        "prompt": req.custom_prompt or generate_prompt(req.niche, user_tier=user_tier),
        "metadata": {
            "model_type": req.model_type,
            "has_images": bool(req.image_urls),
            "num_images": len(req.image_urls) if req.image_urls else 0,
            "num_shots": len(req.shots) if req.shots else 0,
            "ai_model": req.ai_model,
            "user_tier": user_tier
        }
    })

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

    estimated_time = num_clips * 40
    return VideoResponse(
        job_id=job_id,
        status="pending",
        estimated_time=f"{estimated_time}-{estimated_time + 60}s",
        num_clips=num_clips,
        total_credits=required_credits
    )

@app.get("/api/videos/{job_id}/status")
async def get_video_status(job_id: str, request: Request):
    """Check le statut d'une vidéo"""
    try:
        # Require auth and ensure ownership
        token_user_id = await _get_authenticated_user_id(request)
        job = get_supabase().table("video_jobs").select("*").eq("id", job_id).maybe_single().execute()

        job_data = job.data if job else None
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        if job_data.get("user_id") != token_user_id:
            raise HTTPException(status_code=403, detail="Forbidden")

        # Tolérant aux deux formats de metadata : dict (nouveau) et string JSON (ancien)
        if job_data.get("metadata"):
            job_data["metadata"] = _parse_job_metadata(job_data["metadata"])

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
    except HTTPException:
        raise
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
        user = get_supabase().table("profiles").select("*").eq("id", user_id).maybe_single().execute()

        if not user or not user.data:
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

    TIER LOGIC (source of truth = profiles.plan_family):
    - plan_family 'creator' (creator_basic/pro/max, free) → CREATOR tier (9:16 vertical)
    - plan_family 'professional' (professional_starter/pro/max) → PROFESSIONAL tier (16:9 horizontal)

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

        user = get_supabase().table("profiles").select("plan, plan_family, credits").eq("id", user_id).maybe_single().execute()

        if not user or not user.data:
            raise HTTPException(status_code=404, detail="User not found")

        plan = user.data.get("plan", "free")
        credits = user.data.get("credits", 0)
        tier = get_user_tier(user.data)  # plan_family est la source de vérité
        is_creator = (tier == "creator")
        aspect_ratio = get_aspect_ratio_for_tier(tier)

        # Build tier-specific features
        if is_creator:
            features = {
                "duration_selection": False,  # Creator tier cannot select duration
                "fixed_duration_veo": 8,
                "fixed_duration_sora": 8,
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
                "min_duration": MIN_VIDEO_DURATION,
                "max_duration": MAX_VIDEO_DURATION,
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
    """Synchronise les données utilisateur depuis Supabase Auth (appelé après login OAuth).

    SEUL endroit (hors trigger DB à l'inscription) où un profil peut être créé,
    et uniquement avec le VRAI email transmis par le frontend depuis la session
    Supabase Auth (jamais d'email fabriqué '{user_id}@vykso.com').
    """
    try:
        # Require auth and ensure identity consistency when possible
        token_user_id = await _get_authenticated_user_id(request)
        user_id = user_data.get("id")
        email = (user_data.get("email") or "").strip() or None

        # Parsing explicite du prénom / nom (avec gardes sur les listes vides)
        user_metadata = user_data.get("user_metadata") or {}
        full_name = (user_metadata.get("full_name") or "").strip()
        name_parts = full_name.split() if full_name else []

        first_name = user_metadata.get("first_name")
        if not first_name and name_parts:
            first_name = name_parts[0]

        last_name = user_metadata.get("last_name")
        if not last_name and len(name_parts) > 1:
            last_name = " ".join(name_parts[1:])

        if not user_id:
            raise HTTPException(status_code=400, detail="User ID is required")

        if token_user_id and user_id and token_user_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden")

        # Check if user exists
        existing = get_supabase().table("profiles").select("*").eq("id", user_id).execute()

        update_data = {}
        if email:
            update_data["email"] = email
        if first_name:
            update_data["first_name"] = first_name
        if last_name:
            update_data["last_name"] = last_name

        if existing.data:
            # Update existing user
            if update_data:
                result = get_supabase().table("profiles").update(update_data).eq("id", user_id).execute()
            else:
                result = existing
        else:
            # Create new user — exige le vrai email (pas d'email fabriqué)
            if not email:
                raise HTTPException(
                    status_code=400,
                    detail="Email requis pour créer le profil — reconnectez-vous"
                )
            update_data.update({
                "id": user_id,
                "credits": 10,
                "plan": "free"
            })
            result = get_supabase().table("profiles").insert(update_data).execute()

            # Notification best-effort (ne lève jamais)
            notify_event("Nouvel utilisateur", {
                "user_id": user_id,
                "email": email,
                "nom": f"{first_name or ''} {last_name or ''}".strip() or "inconnu",
            })

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
    token_user_id = await _get_authenticated_user_id(request)

    # Default body if not provided
    if body is None:
        body = YouTubeUploadRequest()

    temp_video_path = None
    try:
        # 1. Get User YouTube Tokens from profiles table
        user = get_supabase().table("profiles").select("youtube_tokens").eq("id", token_user_id).maybe_single().execute()
        if not user or not user.data or not user.data.get("youtube_tokens"):
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
            # Persist the refreshed credentials (includes new token + expiry)
            get_supabase().table("profiles").update({
                "youtube_tokens": refreshed_tokens
            }).eq("id", token_user_id).execute()
            tokens = refreshed_tokens

        # 2. Get Video Job Data
        job = get_supabase().table("video_jobs").select("*").eq("id", job_id).maybe_single().execute()
        if not job or not job.data:
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
            # Try direct download if it's a full URL (async, non bloquant)
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as http_client:
                r = await http_client.get(video_url)
                r.raise_for_status()
                video_data = r.content
        else:
            video_data = get_supabase().storage.from_(VIDEOS_BUCKET).download(path)

        temp_video_path = f"/tmp/{job_id}_upload.mp4"
        with open(temp_video_path, "wb") as f:
            f.write(video_data)

        # 6. Reuse, download or generate thumbnail
        thumbnail_bytes = None
        current_metadata = _parse_job_metadata(job.data.get("metadata"))

        if body.thumbnail_url:
            # Download thumbnail from provided URL
            print(f"📥 Downloading provided thumbnail...")
            try:
                async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http_client:
                    r = await http_client.get(body.thumbnail_url)
                    if r.status_code == 200:
                        thumbnail_bytes = r.content
            except Exception as e:
                print(f"⚠️ Failed to download thumbnail: {e}")

        # F-44 : réutiliser la miniature déjà générée lors d'une tentative précédente
        if not thumbnail_bytes:
            previous_thumbnail_path = current_metadata.get("thumbnail_path")
            if previous_thumbnail_path and os.path.exists(previous_thumbnail_path):
                try:
                    with open(previous_thumbnail_path, "rb") as f:
                        thumbnail_bytes = f.read()
                    print(f"♻️ Reusing previously generated thumbnail: {previous_thumbnail_path}")
                except Exception as e:
                    print(f"⚠️ Failed to reuse previous thumbnail: {e}")

        if not thumbnail_bytes:
            # Generate thumbnail with Imagen (optimized for YouTube Shorts 9:16)
            print("🖼️ Generating YouTube Shorts thumbnail with AI...")
            try:
                thumbnail_bytes, thumbnail_path = get_gemini().generate_thumbnail(
                    title=final_title,
                    description=final_description,
                    original_prompt=original_prompt
                )

                # Save thumbnail path to video_jobs metadata (dict natif, pas de json.dumps)
                if thumbnail_path:
                    try:
                        current_metadata["thumbnail_path"] = thumbnail_path
                        get_supabase().table("video_jobs").update({
                            "metadata": current_metadata
                        }).eq("id", job_id).execute()
                        print(f"💾 Thumbnail path saved to metadata: {thumbnail_path}")
                    except Exception as e:
                        print(f"⚠️ Failed to save thumbnail path to metadata: {e}")

            except Exception as e:
                print(f"⚠️ Thumbnail generation failed: {e}")
                # Continue without thumbnail - YouTube will auto-generate one

        # 7. Upload to YouTube with thumbnail (blocking client → executor)
        print(f"🚀 Uploading to YouTube...")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: get_youtube().upload_video_with_thumbnail(
            file_path=temp_video_path,
            title=final_title,
            description=final_description,
            credentials_dict=tokens,
            privacy=final_privacy,
            tags=final_tags,
            schedule_time=schedule_time_iso,
            thumbnail_bytes=thumbnail_bytes
        ))

        # 8. Return response
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
    finally:
        # Cleanup temp file on success OR failure (F-18)
        if temp_video_path:
            try:
                os.remove(temp_video_path)
            except Exception:
                pass

# ============= YOUTUBE AUTH ENDPOINTS =============

@app.get("/api/auth/youtube/url")
async def get_youtube_auth_url(request: Request):
    token_user_id = await _get_authenticated_user_id(request)
    # F-34 : state signé (HMAC + expiration 10 min) — anti-CSRF
    state = make_oauth_state(token_user_id)
    url = get_youtube().get_auth_url(user_id=state)
    return {"url": url}

@app.get("/api/auth/youtube/callback")
async def youtube_auth_callback(code: str, state: str):
    """
    Callback from Google. 'state' is a signed token built by make_oauth_state
    (F-34: CSRF protection) — verified before any DB write.
    """
    frontend_url = os.getenv("FRONTEND_URL", "https://vykso.com").rstrip("/")

    # F-34 : vérifier la signature + l'expiration du state
    user_id = verify_oauth_state(state)
    if not user_id:
        raise HTTPException(status_code=400, detail="State OAuth invalide ou expiré — relancez la connexion YouTube")

    try:
        credentials = get_youtube().get_credentials_from_code(code)

        # F-35 : sérialisation via le client (inclut `expiry` pour le refresh proactif)
        creds_dict = YouTubeClient.credentials_to_dict(credentials)

        # Validate that we got a refresh_token (required for long-term access)
        if not creds_dict.get('refresh_token'):
            print("⚠️ Warning: No refresh_token received from Google. User may need to revoke app access and reconnect.")

        print(f"📝 Storing YouTube credentials with fields: {list(creds_dict.keys())}")

        # Store in DB
        get_supabase().table("profiles").update({
            "youtube_tokens": creds_dict
        }).eq("id", user_id).execute()

        return RedirectResponse(url=f"{frontend_url}/dashboard?youtube=connected")

    except Exception as e:
        print(f"❌ YouTube callback error: {e}")
        return RedirectResponse(url=f"{frontend_url}/dashboard?youtube=error")


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
        
        user = get_supabase().table("profiles").select("youtube_tokens").eq("id", token_user_id).maybe_single().execute()

        if not user or not user.data or not user.data.get("youtube_tokens"):
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

@app.get("/api/videos/{job_id}/download")
async def download_video(job_id: str, request: Request):
    """Télécharge une vidéo directement depuis la plateforme (proxy + streaming, supporte gros fichiers)."""
    try:
        # Require auth and ensure ownership
        token_user_id = await _get_authenticated_user_id(request)
        job = get_supabase().table("video_jobs").select("video_url, niche, created_at, user_id").eq("id", job_id).maybe_single().execute()
        if not job or not job.data:
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
        job = get_supabase().table("video_jobs").select("video_url, user_id").eq("id", job_id).maybe_single().execute()
        if not job or not job.data:
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

# Extension dérivée du content_type validé — jamais du nom de fichier client
_ALLOWED_IMAGE_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

@app.post("/api/upload-image")
@limiter.limit("20/minute")
async def upload_image_to_supabase(request: Request, file: UploadFile = File(...)):
    """Upload une image vers Supabase Storage"""
    try:
        # Require auth
        await _get_authenticated_user_id(request)
        # Vérifier le type de fichier (whitelist jpg/png/webp)
        if file.content_type not in _ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(_ALLOWED_IMAGE_TYPES)}"
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

        # Nom unique — extension issue du content_type validé (pas du filename client)
        file_ext = _ALLOWED_IMAGE_TYPES[file.content_type]
        filename = f"{uuid.uuid4()}.{file_ext}"

        print(f"📤 Uploading image to Supabase: {filename}")

        supabase_client = get_supabase()

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

# ============= STALE JOBS WATCHDOG =============
# Toutes les 10 min : les jobs pending/generating SANS ACTIVITÉ (updated_at,
# bumpe à chaque écriture de progress) depuis JOB_STALE_MINUTES sont passés en
# failed avec remboursement du credits_cost stocké + notification.
# Staleness sur updated_at (pas created_at) : un job long mais vivant qui
# écrit sa progression n'est jamais tué.

WATCHDOG_INTERVAL_SECONDS = 600  # 10 minutes


async def _watchdog_loop():
    while True:
        try:
            stale_minutes = int(os.getenv("JOB_STALE_MINUTES", "45"))
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)).isoformat()
            res = get_supabase().table("video_jobs").select("id").in_(
                "status", ["pending", "generating"]
            ).lt("updated_at", cutoff).execute()
            stale_jobs = res.data or []
            if stale_jobs:
                print(f"🕰️ Watchdog: {len(stale_jobs)} stale job(s) older than {stale_minutes} min")
            for row in stale_jobs:
                try:
                    _fail_job_and_refund(
                        row["id"],
                        "Interrompu (redémarrage serveur ou timeout)",
                        notify_label="Job vidéo échoué (watchdog)",
                    )
                except Exception as job_err:
                    print(f"❌ Watchdog: error handling job {row.get('id')}: {job_err}")
        except Exception as e:
            print(f"❌ Watchdog loop error: {e}")
        await asyncio.sleep(WATCHDOG_INTERVAL_SECONDS)


@app.on_event("startup")
async def _start_watchdog():
    asyncio.create_task(_watchdog_loop())
    print(f"🕰️ Stale-jobs watchdog started (every {WATCHDOG_INTERVAL_SECONDS // 60} min, "
          f"stale after {os.getenv('JOB_STALE_MINUTES', '45')} min)")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
