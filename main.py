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
from io import BytesIO
from starlette.requests import Request as StarletteRequest
from starlette.responses import StreamingResponse as StarletteStreamingResponse

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

# Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# ========= VIDEO STREAMING/PROXY HELPERS =========
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
VIDEOS_BUCKET = os.getenv("VIDEOS_BUCKET", "vykso-videos")

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
    user_id: str
    niche: Optional[str] = None
    duration: int
    quality: str = "basic"
    custom_prompt: Optional[str] = None
    ai_model: Literal["sora2", "veo3_fast", "veo3"] = "veo3_fast"

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
    user_id: str
    niche: Optional[str] = None
    duration: int = 10
    quality: str = "basic"
    custom_prompt: Optional[str] = None
    image_urls: Optional[List[str]] = None
    shots: Optional[List[StoryboardShot]] = None
    model_type: Literal["text-to-video", "image-to-video", "storyboard"] = "text-to-video"
    ai_model: Literal["sora2", "veo3_fast", "veo3"] = "veo3_fast"

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

def calculate_credits_cost(duration: int, quality: str) -> int:
    """Calcule le coût en crédits selon la durée et la qualité"""
    num_clips = (duration + 9) // 10
    
    if quality == "basic":
        return num_clips * 1
    elif quality == "pro_720p":
        return num_clips * 3
    elif quality == "pro_1080p":
        return num_clips * 5
    else:
        return num_clips

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
        if ai_model in ["veo3", "veo3_fast"]:
            # ===== MODE VEO 3.1 (Google GenAI) - génération synchronisée avec polling =====
            print(f"🎥 Using Veo 3.1 API ({ai_model})")
            use_fast = ai_model == "veo3_fast"

            # Veo ≈ 8s par clip => découpage puis concat
            num_clips = (duration + 7) // 8
            clip_urls = []

            for i in range(num_clips):
                clip_prompt = generate_prompt(niche, custom_prompt, i + 1, num_clips)
                print(f"📝 Veo clip {i+1}/{num_clips} prompt: {clip_prompt[:100]}...")

                local_path = veo.generate_video_and_wait(
                    prompt=clip_prompt,
                    use_fast_model=use_fast,
                    aspect_ratio="9:16",
                    download_path=f"/tmp/{job_id}_veo_{i}.mp4",
                )

                with open(local_path, "rb") as f:
                    data = f.read()
                url = uploader.upload_bytes(data, f"{job_id}_clip_{i}.mp4")
                clip_urls.append(url)

            if len(clip_urls) == 1:
                final_url = clip_urls[0]
            else:
                print(f"🎞️ Concatenating {len(clip_urls)} Veo clips...")
                concatenated_data = video_editor.concatenate_videos(clip_urls, f"{job_id}.mp4")
                final_url = uploader.upload_bytes(concatenated_data, f"{job_id}.mp4")

            supabase.table("video_jobs").update({
                "status": "completed",
                "video_url": final_url,
                "completed_at": "now()",
            }).eq("id", job_id).execute()

            credits_to_deduct = calculate_credits_cost(duration, quality)
            supabase.rpc("decrement_credits", {
                "p_user_id": user_id,
                "p_amount": credits_to_deduct,
            }).execute()
            print(f"✅ Job {job_id} completed! ({credits_to_deduct} credits deducted)")
        
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

            if model_type == "storyboard" and shots:
                iterable = enumerate(shots)
            else:
                iterable = enumerate([None] * num_clips)

            for i, shot in iterable:
                clip_prompt = shot["Scene"] if shot else generate_prompt(niche, custom_prompt, i + 1, num_clips)
                print(f"📝 Sora clip {i+1} prompt: {clip_prompt[:100]}...")

                local_path = sora.generate_video_and_wait(
                    prompt=clip_prompt,
                    use_pro=use_pro,
                    size=size,
                    seconds=(int(shot["duration"]) if shot else clip_seconds),
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

            credits_to_deduct = calculate_credits_cost(duration, quality)
            supabase.rpc("decrement_credits", {
                "p_user_id": user_id,
                "p_amount": credits_to_deduct,
            }).execute()
            print(f"✅ Job {job_id} completed! ({credits_to_deduct} credits deducted)")
        
    except Exception as e:
        print(f"❌ Error generating video {job_id}: {e}")
        import traceback
        traceback.print_exc()
        
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
async def generate_video(req: VideoRequest, background_tasks: BackgroundTasks):
    """Endpoint principal : génère une vidéo de durée variable"""
    
    if req.duration < 10 or req.duration > 60:
        raise HTTPException(status_code=400, detail="Duration must be between 10 and 60 seconds")
    
    if not req.niche and not req.custom_prompt:
        raise HTTPException(status_code=400, detail="Either niche or custom_prompt is required")
    
    num_clips = (req.duration + 9) // 10
    required_credits = calculate_credits_cost(req.duration, req.quality)
    
    try:
        user = supabase.table("users").select("*").eq("id", req.user_id).execute()
        
        if not user.data:
            print(f"👤 Creating new user: {req.user_id}")
            supabase.table("users").insert({
                "id": req.user_id,
                "email": f"{req.user_id}@vykso.com",
                "credits": 10,
                "plan": "free"
            }).execute()
            user = supabase.table("users").select("*").eq("id", req.user_id).execute()
        
        user_data = user.data[0]
        print(f"👤 User: {req.user_id}, Credits: {user_data['credits']}, Plan: {user_data['plan']}")
        
    except Exception as e:
        print(f"❌ Error checking user: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    if user_data["credits"] < required_credits:
        raise HTTPException(
            status_code=402, 
            detail=f"Crédits insuffisants. Besoin de {required_credits} crédits, vous avez {user_data['credits']}"
        )
    
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
async def generate_video_advanced(req: VideoRequestAdvanced, background_tasks: BackgroundTasks):
    """Endpoint avancé : supporte storyboard, image-to-video, etc."""
    
    # Calculer la durée totale pour storyboard
    if req.model_type == "storyboard" and req.shots:
        total_duration = sum(shot.duration for shot in req.shots)
        req.duration = int(total_duration)
    
    if req.duration < 10 or req.duration > 60:
        raise HTTPException(status_code=400, detail="Duration must be between 10 and 60 seconds")
    
    if req.model_type != "storyboard":
        if not req.niche and not req.custom_prompt:
            raise HTTPException(status_code=400, detail="Either niche or custom_prompt is required")
    
    # Calculer le coût
    required_credits = calculate_credits_cost(req.duration, req.quality)
    
    # Vérifier user et crédits
    try:
        user = supabase.table("users").select("*").eq("id", req.user_id).execute()
        
        if not user.data:
            supabase.table("users").insert({
                "id": req.user_id,
                "email": f"{req.user_id}@vykso.com",
                "credits": 10,
                "plan": "free"
            }).execute()
            user = supabase.table("users").select("*").eq("id", req.user_id).execute()
        
        user_data = user.data[0]
        
        if user_data["credits"] < required_credits:
            raise HTTPException(
                status_code=402, 
                detail=f"Crédits insuffisants. Besoin de {required_credits} crédits"
            )
        
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
async def get_video_status(job_id: str):
    """Check le statut d'une vidéo"""
    try:
        job = supabase.table("video_jobs").select("*").eq("id", job_id).execute()
        
        if not job.data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        job_data = job.data[0]
        
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
async def get_user_videos(user_id: str, limit: int = 20, offset: int = 0):
    """Liste les vidéos d'un utilisateur"""
    try:
        videos = supabase.table("video_jobs").select("*").eq("user_id", user_id).order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        
        return {
            "total": len(videos.data),
            "videos": videos.data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/users/{user_id}/info")
async def get_user_info(user_id: str):
    """Récupère les infos complètes d'un utilisateur"""
    try:
        user = supabase.table("users").select("*").eq("id", user_id).single().execute()
        
        if not user.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        return user.data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/users/sync")
async def sync_user_from_auth(user_data: dict):
    """Synchronise les données utilisateur depuis Supabase Auth (appelé après login OAuth)"""
    try:
        user_id = user_data.get("id")
        email = user_data.get("email")
        first_name = user_data.get("user_metadata", {}).get("first_name") or user_data.get("user_metadata", {}).get("full_name", "").split()[0] if user_data.get("user_metadata", {}).get("full_name") else None
        last_name = user_data.get("user_metadata", {}).get("last_name") or " ".join(user_data.get("user_metadata", {}).get("full_name", "").split()[1:]) if user_data.get("user_metadata", {}).get("full_name") and len(user_data.get("user_metadata", {}).get("full_name", "").split()) > 1 else None
        
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID is required")
        
        # Check if user exists
        existing = supabase.table("users").select("*").eq("id", user_id).execute()
        
        update_data = {
            "email": email or f"{user_id}@vykso.com",
        }
        
        if first_name:
            update_data["first_name"] = first_name
        if last_name:
            update_data["last_name"] = last_name
        
        if existing.data:
            # Update existing user
            result = supabase.table("users").update(update_data).eq("id", user_id).execute()
        else:
            # Create new user
            update_data.update({
                "id": user_id,
                "credits": 10,
                "plan": "free"
            })
            result = supabase.table("users").insert(update_data).execute()
        
        return {"success": True, "user": result.data[0] if result.data else None}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error syncing user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============= STRIPE ENDPOINTS =============

@app.post("/api/stripe/create-checkout")
async def create_checkout_session(req: CheckoutRequest):
    """Créer une session Stripe Checkout pour abonnement"""
    
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
async def buy_credits(req: BuyCreditsRequest):
    """Acheter des crédits ponctuels (pas d'abonnement)"""
    
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
                user = supabase.table("users").select("credits").eq("id", user_id).single().execute()
                current_credits = user.data.get('credits', 0)
                
                supabase.table("users").update({
                    "credits": current_credits + credits_to_add
                }).eq("id", user_id).execute()
                
                print(f"✅ Added {credits_to_add} credits to user {user_id} (total: {current_credits + credits_to_add})")
            except Exception as e:
                print(f"❌ Error adding credits: {e}")
        
        elif metadata.get('type') == 'subscription':
            plan = metadata.get('plan')
            
            credits_map = {
                "starter": 60,
                "pro": 120,
                "max": 180
            }
            
            print(f"✅ Subscription {plan} for user {user_id}")
            
            try:
                supabase.table("users").update({
                    "plan": plan,
                    "credits": credits_map.get(plan, 60),
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
                user = supabase.table("users").select("*").eq("stripe_subscription_id", subscription_id).single().execute()
                
                if user.data:
                    plan = user.data['plan']
                    credits_map = {
                        "starter": 60,
                        "pro": 120,
                        "max": 180
                    }
                    
                    supabase.table("users").update({
                        "credits": credits_map.get(plan, 60)
                    }).eq("id", user.data['id']).execute()
                    
                    print(f"✅ Monthly credits recharged for user {user.data['id']}: {credits_map.get(plan)} credits")
            except Exception as e:
                print(f"❌ Error recharging credits: {e}")
    
    return {"status": "success"}

@app.get("/api/videos/{job_id}/download")
async def download_video(job_id: str, request: Request):
    """Télécharge une vidéo directement depuis la plateforme (proxy + streaming, supporte gros fichiers)."""
    try:
        job = supabase.table("video_jobs").select("video_url, niche, created_at").eq("id", job_id).single().execute()
        if not job.data:
            raise HTTPException(status_code=404, detail="Video not found")

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
        job = supabase.table("video_jobs").select("video_url").eq("id", job_id).single().execute()
        if not job.data:
            raise HTTPException(status_code=404, detail="Video not found")

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
async def upload_image_to_supabase(file: UploadFile = File(...)):
    """Upload une image vers Supabase Storage"""
    try:
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
