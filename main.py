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
from pydantic import BaseModel
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

# Clients
sora = SoraClient()
veo = VeoAIClient()
supabase = get_client()
uploader = SupabaseVideoUploader()
video_editor = VideoEditor()
gemini_client = GeminiClient()
youtube_client = YouTubeClient()
content_generator = ContentGenerator(gemini_client=gemini_client)
schedule_calculator = ScheduleCalculator()

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

class VideoRequest(BaseModel):
    user_id: str  # Ignored server-side; derived from JWT
    niche: Optional[str] = None
    duration: int
    quality: str = "basic"
    custom_prompt: Optional[str] = None
    ai_model: Literal["sora2", "veo3.1"] = "veo3.1"

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
    ai_model: Literal["sora2", "veo3.1"] = "veo3.1"


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

def generate_prompt(niche: str = None, custom_prompt: str = None, clip_index: int = None, total_clips: int = None) -> str:
    """Génère un prompt optimisé pour Sora"""
    
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
    
    return f"{base}{sequence_info}, 9:16 vertical format, TikTok optimized, high quality, cinematic"

def calculate_credits_cost(duration: int, quality: str, ai_model: str = "veo3.1") -> int:
    """Calcule le coût en crédits selon la durée, la qualité et le modèle"""
    # Veo 3.1 uses 8s segments, Sora uses 10s segments
    if ai_model == "veo3.1":
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
    if duration < 8 or duration > 60:
        raise HTTPException(status_code=400, detail="Duration must be between 8 and 60 seconds")
    if ai_model == "veo3.1":
        # Veo 3.1 supports 4s, 6s, or 8s clips - duration should be multiple of 8 for segments
        if duration % 8 not in (0,):
            raise HTTPException(status_code=400, detail="Duration must be a multiple of 8 for Veo 3.1 model")
    else:
        if duration % 10 not in (0,):
            raise HTTPException(status_code=400, detail="Duration must be a multiple of 10 for Sora model")

def _validate_image_urls(image_urls: Optional[List[str]]):
    if not image_urls:
        return
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
    ai_model: str = "veo3_fast"
):
    """Background task : génère la vidéo (tous les modèles supportés)"""
    try:
        print(f"🎬 Starting generation for job {job_id}")
        print(f"🤖 AI Model: {ai_model}")
        print(f"📊 Model type: {model_type}")
        
        supabase.table("video_jobs").update({
            "status": "generating"
        }).eq("id", job_id).execute()
        
        # ===== DÉTECTION DU MODÈLE AI =====
        if ai_model == "veo3.1":
            # ===== MODE VEO 3.1 (Google GenAI) - Parallel Advanced Scripting =====
            print(f"🎥 Using Veo 3.1 API ({ai_model}) with Parallel Advanced Scripting")

            # 1. Calculate Segments (8s blocks for Veo 3.1)
            num_segments = (duration + 7) // 8
            
            # 2. Generate Script using Gemini with prompt enrichment
            print(f"📜 Generating enriched script for {duration}s video ({num_segments} segments)...")
            script = gemini_client.generate_video_script(
                prompt=custom_prompt or generate_prompt(niche),
                duration=duration,
                num_segments=num_segments,
                user_images=image_urls
            )
            
            # 3. Download user images if provided (for Veo 3.1 reference images)
            user_pil_images = []
            if image_urls:
                import httpx
                from PIL import Image
                for img_url in image_urls[:3]:  # Max 3 images for Veo 3.1
                    try:
                        print(f"📥 Downloading user image: {img_url[:50]}...")
                        resp = httpx.get(img_url, timeout=30)
                        user_pil_images.append(Image.open(BytesIO(resp.content)))
                    except Exception as e:
                        print(f"⚠️ Failed to download image: {e}")
            
            import asyncio
            from concurrent.futures import ThreadPoolExecutor
            
            async def process_shot(segment_index, shot_data, user_images_list):
                """Helper to process a single shot: Image Gen -> Video Gen with Veo 3.1"""
                shot_idx = shot_data.get("shot_index", 0)
                img_prompt = shot_data.get("image_prompt")
                vid_prompt = shot_data.get("video_prompt")
                use_user_image_idx = shot_data.get("use_user_image_index")
                shot_duration = shot_data.get("duration", 8)
                
                print(f"🎬 Processing Seg {segment_index} Shot {shot_idx}...")
                
                loop = asyncio.get_running_loop()
                
                pil_image = None
                reference_images = None
                
                # Check if we should use a user-provided image
                if use_user_image_idx is not None and use_user_image_idx < len(user_images_list):
                    print(f"  🖼️ Using user-provided image {use_user_image_idx} for this shot")
                    pil_image = user_images_list[use_user_image_idx]
                else:
                    # A. Generate Image with enriched prompt (Parallel)
                    print(f"  📸 Seg {segment_index} Shot {shot_idx}: Generating Image with gemini-3-pro-image-preview...")
                    image_bytes = await loop.run_in_executor(None, gemini_client.generate_image, img_prompt)
                    
                    if image_bytes:
                        from PIL import Image
                        pil_image = Image.open(BytesIO(image_bytes))
                        # Upload generated image for reference
                        try:
                            img_path = f"/tmp/{job_id}_seg{segment_index}_shot{shot_idx}.png"
                            with open(img_path, "wb") as f:
                                f.write(image_bytes)
                            await loop.run_in_executor(None, uploader.upload_file, img_path, f"{job_id}_seg{segment_index}_shot{shot_idx}.png", "video-images")
                        except Exception as e:
                            print(f"⚠️ Failed to upload generated image: {e}")

                # B. Generate Video with Veo 3.1 (enriched prompts already applied)
                print(f"  🎥 Seg {segment_index} Shot {shot_idx}: Generating Video with Veo 3.1...")
                
                # Validate duration for Veo 3.1 (4, 6, or 8 seconds)
                veo_duration = 8  # Default to 8s for best quality
                if shot_duration in [4, 6, 8]:
                    veo_duration = shot_duration
                
                local_path = await loop.run_in_executor(
                    None, 
                    lambda: veo.generate_video_and_wait(
                        prompt=vid_prompt,
                        aspect_ratio="9:16",
                        resolution="720p",
                        duration_seconds=veo_duration,
                        image=pil_image,
                        download_path=f"/tmp/{job_id}_seg{segment_index}_shot{shot_idx}.mp4",
                    )
                )
                
                # Upload clip
                with open(local_path, "rb") as f:
                    data = f.read()
                url = await loop.run_in_executor(None, uploader.upload_bytes, data, f"{job_id}_seg{segment_index}_shot{shot_idx}.mp4")
                return (segment_index, shot_idx, url)

            all_clip_urls = []
            
            if script and "segments" in script:
                tasks = []
                # Create tasks for ALL shots across ALL segments
                for segment in script["segments"]:
                    seg_idx = segment.get("segment_index", 0)
                    for shot in segment.get("shots", []):
                        tasks.append(process_shot(seg_idx, shot, user_pil_images))
                
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
                # Fallback to simple loop if script generation fails
                print("⚠️ Script generation failed, falling back to simple generation.")
                # Generate a single 8s video with the enriched prompt
                enriched_prompt = gemini_client.enrich_prompt(
                    custom_prompt or generate_prompt(niche),
                    segment_context="Single video generation",
                    user_image_description=None
                )
                
                # Use first user image if available
                first_image = user_pil_images[0] if user_pil_images else None
                
                local_path = veo.generate_video_and_wait(
                    prompt=enriched_prompt,
                    aspect_ratio="9:16",
                    resolution="720p",
                    duration_seconds=8,
                    image=first_image,
                    download_path=f"/tmp/{job_id}_fallback.mp4",
                )
                
                with open(local_path, "rb") as f:
                    data = f.read()
                url = uploader.upload_bytes(data, f"{job_id}_fallback.mp4")
                all_clip_urls = [url]

            if len(all_clip_urls) == 1:
                final_url = all_clip_urls[0]
            elif len(all_clip_urls) > 1:
                print(f"🎞️ Concatenating {len(all_clip_urls)} clips...")
                concatenated_data = video_editor.concatenate_videos(all_clip_urls, f"{job_id}.mp4")
                final_url = uploader.upload_bytes(concatenated_data, f"{job_id}.mp4")
            else:
                raise Exception("No clips generated")

            supabase.table("video_jobs").update({
                "status": "completed",
                "video_url": final_url,
                "completed_at": "now()",
            }).eq("id", job_id).execute()

            print(f"✅ Job {job_id} completed!")
        
        else:
            # ===== MODE SORA 2 (OpenAI Videos API) - génération synchronisée avec polling =====
            print(f"🎥 Using Sora 2 API")

            def quality_to_sora_params(q: str):
                # Map simple: basic => default, pro_720p => size 1280x720 + pro, pro_1080p => size 1920x1080 + pro
                if q == "pro_1080p":
                    return True, "1920x1080"
                if q == "pro_720p":
                    return True, "1280x720"
                return False, None

            use_pro, size = quality_to_sora_params(quality)

            # Sora gère 10s/15s; découpons en clips de 10s
            num_clips = (duration + 9) // 10
            clip_seconds = 10
            clip_urls = []

            # Handle image-to-video: download images if provided
            input_reference = None
            if model_type == "image-to-video" and image_urls and len(image_urls) > 0:
                # Use first image for all clips (or can be extended to use different images per clip)
                image_url = image_urls[0]
                print(f"🖼️ Using image reference: {image_url}")
                input_reference = image_url  # sora_client will download it from URL

            if model_type == "storyboard" and shots:
                iterable = enumerate(shots)
            else:
                iterable = enumerate([None] * num_clips)

            for i, shot in iterable:
                clip_prompt = shot["Scene"] if shot else generate_prompt(niche, custom_prompt, i + 1, num_clips)
                print(f"📝 Sora clip {i+1} prompt: {clip_prompt[:100]}...")

                # For image-to-video, use image only for first clip
                clip_input_reference = input_reference if (i == 0 and input_reference) else None

                local_path = sora.generate_video_and_wait(
                    prompt=clip_prompt,
                    use_pro=use_pro,
                    size=size,
                    seconds=(int(shot["duration"]) if shot else clip_seconds),
                    input_reference=clip_input_reference,
                    download_path=f"/tmp/{job_id}_sora_{i}.mp4",
                )

                with open(local_path, "rb") as f:
                    data = f.read()
                url = uploader.upload_bytes(data, f"{job_id}_clip_{i}.mp4")
                clip_urls.append(url)

            if len(clip_urls) == 1:
                final_url = clip_urls[0]
            else:
                print(f"🎞️ Concatenating {len(clip_urls)} Sora clips...")
                concatenated_data = video_editor.concatenate_videos(clip_urls, f"{job_id}.mp4")
                final_url = uploader.upload_bytes(concatenated_data, f"{job_id}.mp4")

            supabase.table("video_jobs").update({
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
            supabase.rpc("refund_credits", {
                "p_user_id": user_id,
                "p_amount": cost
            }).execute()
            print(f"✅ Refunded {cost} credits.")
        except Exception as refund_error:
            print(f"❌ Error refunding credits: {refund_error}")

        supabase.table("video_jobs").update({
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
    """Endpoint principal : génère une vidéo de durée variable"""
    # Auth: derive user_id from JWT
    token_user_id = await _get_authenticated_user_id(request)
    # Security: ignore body user_id and use token subject
    req.user_id = token_user_id

    # Validate model/duration
    _validate_duration_and_model(req.duration, req.ai_model)
    
    if not req.niche and not req.custom_prompt:
        raise HTTPException(status_code=400, detail="Either niche or custom_prompt is required")
    
    # Calculate clips based on model (8s for Veo 3.1, 10s for Sora)
    if req.ai_model == "veo3.1":
        num_clips = (req.duration + 7) // 8
    else:
        num_clips = (req.duration + 9) // 10
    required_credits = calculate_credits_cost(req.duration, req.quality, req.ai_model)
    
    try:
        user = supabase.table("profiles").select("*").eq("id", req.user_id).execute()
        
        if not user.data:
            print(f"👤 Creating new user: {req.user_id}")
            supabase.table("profiles").insert({
                "id": req.user_id,
                "email": f"{req.user_id}@vykso.com",
                "credits": 10,
                "plan": "free"
            }).execute()
            user = supabase.table("profiles").select("*").eq("id", req.user_id).execute()
        
        user_data = user.data[0]
        print(f"👤 User: {req.user_id}, Credits: {user_data['credits']}, Plan: {user_data['plan']}")
        
    except Exception as e:
        print(f"❌ Error checking user: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    # Deduct credits atomically BEFORE scheduling work (backend source of truth)
    try:
        decrement = supabase.rpc("decrement_credits", {
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
        job = supabase.table("video_jobs").insert({
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
                "ai_model": req.ai_model
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
        req.ai_model
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
    """Endpoint avancé : supporte storyboard, image-to-video, etc."""
    # Auth: derive user_id from JWT
    token_user_id = await _get_authenticated_user_id(request)
    req.user_id = token_user_id

    # Calculer la durée totale pour storyboard
    if req.model_type == "storyboard" and req.shots:
        total_duration = sum(shot.duration for shot in req.shots)
        req.duration = int(total_duration)
    # Validate model/duration
    _validate_duration_and_model(req.duration, req.ai_model)
    
    if req.model_type != "storyboard":
        if not req.niche and not req.custom_prompt:
            raise HTTPException(status_code=400, detail="Either niche or custom_prompt is required")
    
    # Additional server-side validations
    _validate_image_urls(req.image_urls)

    # Calculer le coût
    required_credits = calculate_credits_cost(req.duration, req.quality, req.ai_model)
    
    # Vérifier user et crédits
    try:
        user = supabase.table("profiles").select("*").eq("id", req.user_id).execute()
        
        if not user.data:
            supabase.table("profiles").insert({
                "id": req.user_id,
                "email": f"{req.user_id}@vykso.com",
                "credits": 10,
                "plan": "free"
            }).execute()
            user = supabase.table("profiles").select("*").eq("id", req.user_id).execute()
        
        user_data = user.data[0]
        
        # Deduct credits BEFORE scheduling generation
        decrement = supabase.rpc("decrement_credits", {
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
        job = supabase.table("video_jobs").insert({
            "user_id": req.user_id,
            "status": "pending",
            "niche": req.niche or ("storyboard" if req.model_type == "storyboard" else "custom"),
            "duration": req.duration,
            "quality": req.quality,
            "prompt": req.custom_prompt or generate_prompt(req.niche),
            "metadata": json.dumps({
                "model_type": req.model_type,
                "has_images": bool(req.image_urls),
                "num_shots": len(req.shots) if req.shots else 0,
                "ai_model": req.ai_model
            })
        }).execute()
        
        job_id = job.data[0]["id"]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    # Lancer génération
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
        req.ai_model
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
        job = supabase.table("video_jobs").select("*").eq("id", job_id).single().execute()
        
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
        videos = supabase.table("video_jobs").select("*").eq("user_id", user_id).order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        
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
        user = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
        
        if not user.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        return user.data
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
        existing = supabase.table("profiles").select("*").eq("id", user_id).execute()
        
        update_data = {
            "email": email or f"{user_id}@vykso.com",
        }
        
        if first_name:
            update_data["first_name"] = first_name
        if last_name:
            update_data["last_name"] = last_name
        
        if existing.data:
            # Update existing user
            result = supabase.table("profiles").update(update_data).eq("id", user_id).execute()
        else:
            # Create new user
            update_data.update({
                "id": user_id,
                "credits": 10,
                "plan": "free"
            })
            result = supabase.table("profiles").insert(update_data).execute()
        
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
        user = supabase.table("profiles").select("youtube_tokens").eq("id", token_user_id).single().execute()
        if not user.data or not user.data.get("youtube_tokens"):
            raise HTTPException(
                status_code=400, 
                detail="YouTube account not connected. Please connect your YouTube account first."
            )
        
        tokens = user.data["youtube_tokens"]
        
        # Refresh tokens if needed
        refreshed_tokens = youtube_client.refresh_credentials(tokens)
        if refreshed_tokens and refreshed_tokens != tokens:
            # Update tokens in database
            supabase.table("profiles").update({
                "youtube_tokens": refreshed_tokens
            }).eq("id", token_user_id).execute()
            tokens = refreshed_tokens
        
        # 2. Get Video Job Data
        job = supabase.table("video_jobs").select("*").eq("id", job_id).single().execute()
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
            final_title = content_generator.generate_clickbait_title(original_prompt)
        
        # Description
        if body.description:
            final_description = body.description
        else:
            print("📝 Generating description...")
            final_description = content_generator.generate_description(original_prompt)
        
        # Ensure #Shorts is present
        final_title, final_description = content_generator.check_shorts_tag_present(
            final_title, final_description
        )
        
        # Tags
        final_tags = content_generator.get_default_tags(body.tags)
        
        # 4. Calculate schedule time if requested
        schedule_time_iso = None
        schedule_time_display = None
        final_privacy = body.privacy
        
        if body.schedule:
            print("📅 Calculating optimal publish time...")
            optimal_time = schedule_calculator.calculate_optimal_publish_time()
            schedule_time_iso = schedule_calculator.format_for_youtube_api(optimal_time)
            schedule_time_display = schedule_calculator.format_for_display(optimal_time)
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
            video_data = supabase.storage.from_(VIDEOS_BUCKET).download(path)
        
        temp_video_path = f"/tmp/{job_id}_upload.mp4"
        with open(temp_video_path, "wb") as f:
            f.write(video_data)
        
        # 6. Generate or download thumbnail
        thumbnail_bytes = None
        
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
            # Generate thumbnail with Imagen
            print("🖼️ Generating thumbnail with AI...")
            try:
                thumbnail_bytes = gemini_client.generate_thumbnail(
                    title=final_title,
                    description=final_description,
                    original_prompt=original_prompt
                )
            except Exception as e:
                print(f"⚠️ Thumbnail generation failed: {e}")
        
        # 7. Upload to YouTube with thumbnail
        print(f"🚀 Uploading to YouTube...")
        result = youtube_client.upload_video_with_thumbnail(
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
    url = youtube_client.get_auth_url(user_id=token_user_id)
    return {"url": url}

@app.get("/api/auth/youtube/callback")
async def youtube_auth_callback(code: str, state: str):
    """
    Callback from Google. 'state' is the user_id we passed.
    """
    try:
        user_id = state
        credentials = youtube_client.get_credentials_from_code(code)
        
        # Convert credentials to dict
        creds_dict = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': list(credentials.scopes) if credentials.scopes else []
        }
        
        # Store in DB
        supabase.table("profiles").update({
            "youtube_tokens": creds_dict
        }).eq("id", user_id).execute()
        
        return {"status": "success", "message": "YouTube connected successfully"}
        
    except Exception as e:
        print(f"❌ YouTube callback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============= STRIPE ENDPOINTS =============

@app.post("/api/stripe/create-checkout")
async def create_checkout_session(req: CheckoutRequest, request: Request):
    """Créer une session Stripe Checkout pour abonnement"""
    # Auth: derive user_id from JWT and ignore body value
    token_user_id = await _get_authenticated_user_id(request)
    req.user_id = token_user_id

    price_ids = {
        "starter": os.getenv("STRIPE_PRICE_STARTER"),
        "pro": os.getenv("STRIPE_PRICE_PRO"),
        "max": os.getenv("STRIPE_PRICE_MAX")
    }
    
    if req.plan not in price_ids:
        raise HTTPException(status_code=400, detail="Invalid plan")
    
    if not price_ids[req.plan]:
        raise HTTPException(status_code=500, detail=f"Price ID for {req.plan} not configured")
    
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': price_ids[req.plan],
                'quantity': 1,
            }],
            mode='subscription',
            success_url=f"{os.getenv('FRONTEND_URL', 'https://vykso.lovable.app')}/payment-success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{os.getenv('FRONTEND_URL', 'https://vykso.lovable.app')}/pricing",
            client_reference_id=req.user_id,
            metadata={
                'user_id': req.user_id,
                'plan': req.plan,
                'type': 'subscription'
            }
        )
        
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

@app.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request):
    """Webhook Stripe pour gérer les paiements"""
    
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
    
    print(f"📨 Received Stripe webhook: {event['type']}")
    
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        metadata = session.get('metadata', {})
        user_id = metadata.get('user_id')
        
        if metadata.get('type') == 'credit_purchase':
            credits_to_add = int(metadata.get('credits', 0))
            
            print(f"💳 Credit purchase: {credits_to_add} credits for user {user_id}")
            
            try:
                user = supabase.table("profiles").select("credits").eq("id", user_id).single().execute()
                current_credits = user.data.get('credits', 0)
                
                supabase.table("profiles").update({
                    "credits": current_credits + credits_to_add
                }).eq("id", user_id).execute()
                
                print(f"✅ Added {credits_to_add} credits to user {user_id} (total: {current_credits + credits_to_add})")
            except Exception as e:
                print(f"❌ Error adding credits: {e}")
        
        elif metadata.get('type') == 'subscription':
            plan = metadata.get('plan')
            
            credits_map = {
                "starter": 600,
                "pro": 1200,
                "max": 1800
            }
            
            print(f"✅ Subscription {plan} for user {user_id}")
            
            try:
                supabase.table("profiles").update({
                    "plan": plan,
                    "credits": credits_map.get(plan, 600),
                    "stripe_customer_id": session.get('customer'),
                    "stripe_subscription_id": session.get('subscription')
                }).eq("id", user_id).execute()
                
                print(f"✅ User {user_id} upgraded to {plan} with {credits_map.get(plan)} credits")
            except Exception as e:
                print(f"❌ Error updating user: {e}")
    
    elif event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        subscription_id = invoice.get('subscription')
        
        if subscription_id:
            try:
                user = supabase.table("profiles").select("*").eq("stripe_subscription_id", subscription_id).single().execute()
                
                if user.data:
                    plan = user.data['plan']
                    credits_map = {
                        "starter": 600,
                        "pro": 1200,
                        "max": 1800
                    }
                    
                    supabase.table("profiles").update({
                        "credits": credits_map.get(plan, 600)
                    }).eq("id", user.data['id']).execute()
                    
                    print(f"✅ Monthly credits recharged for user {user.data['id']}: {credits_map.get(plan)} credits")
            except Exception as e:
                print(f"❌ Error recharging credits: {e}")
    
    return {"status": "success"}

@app.get("/api/videos/{job_id}/download")
async def download_video(job_id: str, request: Request):
    """Télécharge une vidéo directement depuis la plateforme (proxy + streaming, supporte gros fichiers)."""
    try:
        # Require auth and ensure ownership
        token_user_id = await _get_authenticated_user_id(request)
        job = supabase.table("video_jobs").select("video_url, niche, created_at, user_id").eq("id", job_id).single().execute()
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
        job = supabase.table("video_jobs").select("video_url, user_id").eq("id", job_id).single().execute()
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
