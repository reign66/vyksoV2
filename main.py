import os
import json
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from kie_client import KieAIClient
from supabase_client import get_client
from utils.uploader import R2Uploader

app = FastAPI(
    title="Vykso API",
    description="API de génération vidéo automatique via Sora 2",
    version="1.0.0"
)

# CORS pour Lovable
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    duration: int
    quality: str = "basic"

class VideoResponse(BaseModel):
    job_id: str
    status: str
    estimated_time: str

# ============= FUNCTIONS =============

def generate_prompt(niche: str) -> str:
    """Génère un prompt optimisé pour Sora"""
    templates = {
        "recettes": "Cinematic cooking video showing delicious recipe preparation, beautiful food styling, warm kitchen lighting, professional chef techniques, mouth-watering close-ups, 9:16 vertical format, TikTok optimized, 10 seconds",
        
        "voyage": "Breathtaking travel footage showcasing stunning landscapes, cinematic drone shots, golden hour lighting, epic adventure vibes, cultural exploration, scenic beauty, 9:16 vertical format, TikTok optimized, 10 seconds",
        
        "motivation": "Inspiring motivational content with dynamic visual metaphors, uplifting atmosphere, professional cinematography, energetic pacing, success imagery, empowering message, 9:16 vertical format, TikTok optimized, 10 seconds",
        
        "tech": "Modern technology showcase with sleek product presentation, futuristic aesthetics, clean minimalist style, innovative tech display, professional lighting, cutting-edge visuals, 9:16 vertical format, TikTok optimized, 10 seconds"
    }
    
    return templates.get(niche.lower(), f"High-quality viral video content about {niche}, engaging visuals, professional production, 9:16 vertical format, TikTok optimized, 10 seconds")

async def process_video_generation(job_id: str, niche: str, quality: str, user_id: str):
    """Background task : génère la vidéo"""
    try:
        print(f"🎬 Starting generation for job {job_id}")
        
        # Update status to generating
        supabase.table("video_jobs").update({
            "status": "generating"
        }).eq("id", job_id).execute()
        
        # Générer le prompt
        prompt = generate_prompt(niche)
        print(f"📝 Prompt: {prompt[:100]}...")
        
        # Lancer génération Kie.ai
        task = await kie.generate_video(
            prompt=prompt,
            duration=10,
            quality=quality,
            remove_watermark=(quality != "basic")
        )
        
        task_id = task["taskId"]
        print(f"✅ Task created: {task_id}")
        
        # Sauvegarder le task_id
        supabase.table("video_jobs").update({
            "kie_task_id": task_id,
            "status": "waiting_callback"
        }).eq("id", job_id).execute()
        
        print(f"⏳ Task {task_id} submitted, waiting for callback from Kie.ai...")
        
    except Exception as e:
        print(f"❌ Error generating video {job_id}: {e}")
        import traceback
        traceback.print_exc()
        
        # Update avec erreur
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
    """Endpoint principal : génère une vidéo de 10s"""
    
    # 1. Vérifier/créer user
    try:
        user = supabase.table("users").select("*").eq("id", req.user_id).execute()
        
        if not user.data:
            print(f"👤 Creating new user: {req.user_id}")
            supabase.table("users").insert({
                "id": req.user_id,
                "email": f"{req.user_id}@vykso.com",
                "credits": 10,
                "plan": "starter"
            }).execute()
            user = supabase.table("users").select("*").eq("id", req.user_id).execute()
        
        user_data = user.data[0]
        print(f"👤 User: {req.user_id}, Credits: {user_data['credits']}")
        
    except Exception as e:
        print(f"❌ Error checking user: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    # 2. Vérifier crédits
    if user_data["credits"] < 1:
        raise HTTPException(status_code=402, detail="Crédits insuffisants")
    
    # 3. Créer job dans Supabase
    try:
        job = supabase.table("video_jobs").insert({
            "user_id": req.user_id,
            "status": "pending",
            "niche": req.niche,
            "duration": 10,
            "quality": req.quality,
            "prompt": generate_prompt(req.niche)
        }).execute()
        
        job_id = job.data[0]["id"]
        print(f"📋 Job created: {job_id}")
        
    except Exception as e:
        print(f"❌ Error creating job: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    # 4. Lancer génération en background
    background_tasks.add_task(process_video_generation, job_id, req.niche, req.quality, req.user_id)
    
    # 5. Réponse immédiate
    return VideoResponse(
        job_id=job_id,
        status="pending",
        estimated_time="30-90s"
    )

@app.get("/api/videos/{job_id}/status")
async def get_video_status(job_id: str):
    """Check le statut d'une vidéo"""
    try:
        job = supabase.table("video_jobs").select("*").eq("id", job_id).execute()
        
        if not job.data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return job.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error getting job status: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.post("/api/callback")
async def kie_callback(payload: dict):
    """Callback Kie.ai - Traite la vidéo quand elle est prête"""
    print("=" * 80)
    print("📞 CALLBACK REÇU DE KIE.AI")
    print("=" * 80)
    print(f"Full payload: {json.dumps(payload, indent=2)}")
    
    data = payload.get('data', {})
    task_id = data.get('taskId')
    state = data.get('state')
    
    print(f"Task ID: {task_id}")
    print(f"State: {state}")
    
    # Si échec
    if state == "fail":
        print("❌ ÉCHEC DÉTECTÉ")
        print(f"Fail Code: {data.get('failCode')}")
        print(f"Fail Message: {data.get('failMsg')}")
        
        if task_id:
            try:
                job = supabase.table("video_jobs").select("*").eq("kie_task_id", task_id).execute()
                
                if job.data:
                    job_id = job.data[0]["id"]
                    error_msg = f"{data.get('failCode')}: {data.get('failMsg')}"
                    
                    supabase.table("video_jobs").update({
                        "status": "failed",
                        "error": error_msg
                    }).eq("id", job_id).execute()
                    
                    print(f"❌ Job {job_id} marqué échoué")
                else:
                    print(f"⚠️ Job not found for task_id: {task_id}")
                    
            except Exception as e:
                print(f"⚠️ Erreur update Supabase: {e}")
                import traceback
                traceback.print_exc()
    
    # Si succès
    if state == "success":
        print("✅ SUCCÈS")
        result_json_str = data.get('resultJson')
        print(f"Result JSON: {result_json_str}")
        
        if result_json_str and task_id:
            try:
                result = json.loads(result_json_str)
                video_url = result.get('resultUrls', [None])[0]
                print(f"Video URL: {video_url}")
                
                if not video_url:
                    print("⚠️ No video URL in result")
                    return {"status": "error", "message": "No video URL"}
                
                # Trouver le job correspondant
                job = supabase.table("video_jobs").select("*").eq("kie_task_id", task_id).execute()
                
                if not job.data:
                    print(f"⚠️ Job not found for task_id: {task_id}")
                    return {"status": "error", "message": "Job not found"}
                
                job_data = job.data[0]
                job_id = job_data["id"]
                user_id = job_data["user_id"]
                
                print(f"📤 Uploading video to R2 for job {job_id}...")
                
                # Upload vers R2
                final_url = uploader.upload_from_url(video_url, f"{job_id}.mp4")
                print(f"✅ Video uploaded: {final_url}")
                
                # Update Supabase
                supabase.table("video_jobs").update({
                    "status": "completed",
                    "video_url": final_url,
                    "completed_at": "now()"
                }).eq("id", job_id).execute()
                
                # Débiter crédit
                supabase.rpc("decrement_credits", {
                    "p_user_id": user_id,
                    "p_amount": 1
                }).execute()
                
                print(f"✅ Job {job_id} completed successfully!")
                
            except Exception as e:
                print(f"⚠️ Erreur traitement callback: {e}")
                import traceback
                traceback.print_exc()
                
                # Marquer le job en erreur
                try:
                    if task_id:
                        job = supabase.table("video_jobs").select("*").eq("kie_task_id", task_id).execute()
                        if job.data:
                            supabase.table("video_jobs").update({
                                "status": "failed",
                                "error": str(e)
                            }).eq("id", job.data[0]["id"]).execute()
                except:
                    pass
    
    print("=" * 80)
    
    return {"status": "received", "task_id": task_id}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
