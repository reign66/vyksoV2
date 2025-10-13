import os
import uuid
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from kie_client import KieAIClient
from supabase_client import get_client
from utils.uploader import R2Uploader
import asyncio

app = FastAPI(
    title="Vykso API",
    description="API de génération vidéo automatique via Sora 2",
    version="1.0.0"
)

# CORS pour Lovable
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En prod: limiter aux domaines spécifiques
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Clients
kie = KieAIClient()
supabase = get_client()
uploader = R2Uploader()

# Models
class VideoRequest(BaseModel):
    user_id: str
    niche: str
    duration: int  # 10-60 secondes
    quality: str = "basic"  # "basic", "pro_720p", "pro_1080p"

class VideoResponse(BaseModel):
    job_id: str
    status: str
    estimated_time: str

@app.get("/")
def root():
    return {
        "service": "Vykso Backend API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/videos/generate", response_model=VideoResponse)
async def generate_video(req: VideoRequest, background_tasks: BackgroundTasks):
    """
    Endpoint principal : génère une vidéo
    """
    
    # 1. Vérifier/créer user
    try:
        user = supabase.table("users").select("*").eq("id", req.user_id).execute()
        
        if not user.data:
            # Créer user si n'existe pas (mode dev)
            supabase.table("users").insert({
                "id": req.user_id,
                "email": f"{req.user_id}@vykso.com",
                "credits": 10,
                "plan": "starter"
            }).execute()
            user = supabase.table("users").select("*").eq("id", req.user_id).execute()
        
        user_data = user.data[0]
        
    except Exception as e:
        print(f"❌ Error checking user: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    # 2. Vérifier crédits
    if user_data["credits"] < 1:
        raise HTTPException(status_code=402, detail="Crédits insuffisants")
    
    # 3. Générer prompt optimisé
    prompt = generate_prompt(req.niche, req.duration)
    
    # 4. Créer job dans Supabase
    try:
        job = supabase.table("video_jobs").insert({
            "user_id": req.user_id,
            "status": "pending",
            "niche": req.niche,
            "duration": req.duration,
            "quality": req.quality,
            "prompt": prompt
        }).execute()
        
        job_id = job.data[0]["id"]
    except Exception as e:
        print(f"❌ Error creating job: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    # 5. Lancer génération en background
    background_tasks.add_task(process_video_generation, job_id, prompt, req.duration, req.quality, req.user_id)
    
    # 6. Réponse immédiate
    return VideoResponse(
        job_id=job_id,
        status="pending",
        estimated_time=f"{req.duration * 3}-{req.duration * 5}s"
    )

@app.get("/api/videos/{job_id}/status")
async def get_video_status(job_id: str):
    """Check le statut d'une vidéo"""
    try:
        job = supabase.table("video_jobs").select("*").eq("id", job_id).execute()
        
        if not job.data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return job.data[0]
    except Exception as e:
        print(f"❌ Error getting job status: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.post("/api/callback")
async def kie_callback(payload: dict):
    """
    Callback endpoint pour Kie.ai
    (optionnel - on poll quand même dans process_video_generation)
    """
    print(f"📞 Callback received: {payload}")
    # On pourrait update le job ici mais on fait déjà le polling
    return {"status": "received"}

async def process_video_generation(job_id: str, prompt: str, duration: int, quality: str, user_id: str):
    """
    Background task : génère la vidéo
    """
    try:
        print(f"🎬 Starting generation for job {job_id}")
        
        # Update status to generating
        supabase.table("video_jobs").update({
            "status": "generating"
        }).eq("id", job_id).execute()
        
        # 1. Lancer génération Kie.ai
        task = await kie.generate_video(
            prompt=prompt,
            duration=duration,
            quality=quality,
            remove_watermark=(quality != "basic")  # Enlever watermark pour Pro plans
        )
        
        task_id = task["taskId"]
        print(f"✅ Task created: {task_id}")
        
        # 2. Poll jusqu'à completion (peut prendre 2-5 min)
        result = await kie.poll_until_complete(task_id, max_wait=600)
        video_url = result["video_url"]
        
        print(f"✅ Video generated: {video_url}")
        
        # 3. Upload vers R2
        final_url = uploader.upload_from_url(video_url, f"{job_id}.mp4")
        
        # 4. Update Supabase
        supabase.table("video_jobs").update({
            "status": "completed",
            "video_url": final_url,
            "kie_task_id": task_id,
            "completed_at": "now()"
        }).eq("id", job_id).execute()
        
        # 5. Débiter crédit
        supabase.rpc("decrement_credits", {
            "p_user_id": user_id,
            "p_amount": 1
        }).execute()
        
        print(f"✅ Job {job_id} completed successfully")
        
    except Exception as e:
        print(f"❌ Error generating video {job_id}: {e}")
        
        # Update avec erreur
        supabase.table("video_jobs").update({
            "status": "failed",
            "error": str(e)
        }).eq("id", job_id).execute()

def generate_prompt(niche: str, duration: int) -> str:
    """
    Génère un prompt optimisé pour Sora
    """
    templates = {
        "recettes": f"Cinematic cooking video showing delicious recipe preparation, beautiful food styling, warm kitchen lighting, professional chef techniques, mouth-watering close-ups, 9:16 vertical format for TikTok, {duration} seconds duration, highly detailed and appetizing",
        
        "voyage": f"Breathtaking travel footage showcasing stunning landscapes, cinematic drone shots, golden hour lighting, epic adventure vibes, cultural exploration, scenic beauty, 9:16 vertical format for TikTok, {duration} seconds duration, ultra HD quality",
        
        "motivation": f"Inspiring motivational content with dynamic visual metaphors, uplifting atmosphere, professional cinematography, energetic pacing, success imagery, empowering message, 9:16 vertical format for TikTok, {duration} seconds duration, high impact visuals",
        
        "tech": f"Modern technology showcase with sleek product presentation, futuristic aesthetics, clean minimalist style, innovative tech display, professional lighting, cutting-edge visuals, 9:16 vertical format for TikTok, {duration} seconds duration, ultra detailed"
    }
    
    # Default si niche pas trouvée
    base_prompt = templates.get(niche.lower(), f"High-quality viral video content about {niche}, engaging visuals, professional production, TikTok optimized")
    
    return f"{base_prompt}, 9:16 vertical format, {duration} seconds, cinematic quality, trending style"

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
