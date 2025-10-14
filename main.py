import os
import uuid
import json
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from kie_client import KieAIClient
from supabase_client import get_client
from utils.uploader import R2Uploader
from utils.video_concat import VideoEditor
from io import BytesIO
import asyncio

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
video_editor = VideoEditor()

# Models
class VideoRequest(BaseModel):
    user_id: str
    niche: str
    duration: int  # Durée totale souhaitée (ex: 60 pour 1min)
    quality: str = "basic"

class VideoResponse(BaseModel):
    job_id: str
    status: str
    estimated_time: str
    num_clips: int  # Nombre de clips à générer

# ============= FUNCTIONS =============

def generate_prompt(niche: str, duration: int, clip_number: int = None, total_clips: int = None) -> str:
    """Génère un prompt optimisé pour Sora"""
    templates = {
        "recettes": "Cinematic cooking video showing delicious recipe preparation, beautiful food styling, warm kitchen lighting, professional chef techniques, mouth-watering close-ups",
        
        "voyage": "Breathtaking travel footage showcasing stunning landscapes, cinematic drone shots, golden hour lighting, epic adventure vibes, cultural exploration, scenic beauty",
        
        "motivation": "Inspiring motivational content with dynamic visual metaphors, uplifting atmosphere, professional cinematography, energetic pacing, success imagery, empowering message",
        
        "tech": "Modern technology showcase with sleek product presentation, futuristic aesthetics, clean minimalist style, innovative tech display, professional lighting, cutting-edge visuals"
    }
    
    base_prompt = templates.get(niche.lower(), f"High-quality viral video content about {niche}, engaging visuals, professional production")
    
    # Ajouter info de séquence si multi-clips
    if clip_number is not None and total_clips is not None:
        scene_info = f", scene {clip_number} of {total_clips}, smooth cinematic transition"
    else:
        scene_info = ""
    
    return f"{base_prompt}{scene_info}, 9:16 vertical format, TikTok optimized, cinematic quality, trending style"

async def process_video_generation(
    job_id: str, 
    niche: str,
    duration: int, 
    quality: str, 
    user_id: str
):
    """
    Background task : génère la vidéo (SANS POLLING, on attend le callback)
    """
    try:
        print(f"🎬 Starting generation for job {job_id}")
        
        # Update status to generating
        supabase.table("video_jobs").update({
            "status": "generating"
        }).eq("id", job_id).execute()
        
        # Calculer le nombre de clips nécessaires
        num_clips = duration // 10
        if duration % 10 > 0:
            num_clips += 1
        
        print(f"📊 Need {num_clips} clips for {duration}s video")
        
        if num_clips == 1:
            # ===== CAS SIMPLE : 1 seul clip (10s) =====
            prompt = generate_prompt(niche, 10)
            
            # Lancer génération Kie.ai
            task = await kie.generate_video(
                prompt=prompt,
                duration=10,
                quality=quality,
                remove_watermark=(quality != "basic")
            )
            
            task_id = task["taskId"]
            print(f"✅ Task created: {task_id}")
            
            # Sauvegarder le task_id et attendre le callback
            supabase.table("video_jobs").update({
                "kie_task_id": task_id,
                "status": "waiting_callback"  # Nouveau status
            }).eq("id", job_id).execute()
            
            print(f"⏳ Task {task_id} submitted, waiting for callback...")
        
        else:
            # ===== CAS COMPLEXE : Plusieurs clips =====
            print(f"🎥 Generating {num_clips} clips...")
            
            tasks = []
            for i in range(num_clips):
                clip_prompt = generate_prompt(niche, 10, i+1, num_clips)
                task = await kie.generate_video(
                    prompt=clip_prompt,
                    duration=10,
                    quality=quality,
                    remove_watermark=False
                )
                tasks.append(task)
                print(f"✅ Clip {i+1}/{num_clips} task created: {task['taskId']}")
            
            # Sauvegarder tous les task_ids
            task_ids = [t["taskId"] for t in tasks]
            supabase.table("video_jobs").update({
                "kie_task_id": json.dumps(task_ids),
                "status": "waiting_callback"
            }).eq("id", job_id).execute()
            
            print(f"⏳ All {num_clips} tasks submitted, waiting for callbacks...")
        
    except Exception as e:
        print(f"❌ Error generating video {job_id}: {e}")
        
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
        "status": "running"
    }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/videos/generate", response_model=VideoResponse)
async def generate_video(req: VideoRequest, background_tasks: BackgroundTasks):
    """Endpoint principal : génère une vidéo (peut faire plusieurs clips)"""
    
    # 1. Vérifier/créer user
    try:
        user = supabase.table("users").select("*").eq("id", req.user_id).execute()
        
        if not user.data:
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
    
    # 2. Calculer nombre de clips nécessaires
    num_clips = req.duration // 10
    if req.duration % 10 > 0:
        num_clips += 1
    
    # 3. Vérifier crédits (1 crédit = 1 clip de 10s)
    required_credits = num_clips
    if user_data["credits"] < required_credits:
        raise HTTPException(
            status_code=402, 
            detail=f"Crédits insuffisants. Besoin de {required_credits} crédits, vous avez {user_data['credits']}"
        )
    
    # 4. Créer job dans Supabase
    try:
        job = supabase.table("video_jobs").insert({
            "user_id": req.user_id,
            "status": "pending",
            "niche": req.niche,
            "duration": req.duration,
            "quality": req.quality,
            "prompt": f"Multi-clip video: {req.niche}"
        }).execute()
        
        job_id = job.data[0]["id"]
    except Exception as e:
        print(f"❌ Error creating job: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    # 5. Lancer génération en background
    background_tasks.add_task(
        process_video_generation, 
        job_id, 
        req.niche,
        req.duration, 
        req.quality, 
        req.user_id
    )
    
    # 6. Réponse immédiate
    estimated_time = num_clips * 30  # ~30s par clip
    return VideoResponse(
        job_id=job_id,
        status="pending",
        estimated_time=f"{estimated_time}s - {estimated_time + 60}s",
        num_clips=num_clips
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
    """Callback Kie.ai"""
    print("=" * 80)
    print("📞 CALLBACK REÇU DE KIE.AI")
    print("=" * 80)
    print(f"Code: {payload.get('code')}")
    print(f"Message: {payload.get('msg')}")
    
    data = payload.get('data', {})
    task_id = data.get('taskId')
    state = data.get('state')
    
    print(f"Task ID: {task_id}")
    print(f"State: {state}")
    print(f"Model: {data.get('model')}")
    print(f"Credits consumed: {data.get('consumeCredits')}")
    print(f"Cost time: {data.get('costTime')}s")
    
    if state == "fail":
        print("❌ ÉCHEC DÉTECTÉ")
        print(f"Fail Code: {data.get('failCode')}")
        print(f"Fail Message: {data.get('failMsg')}")
    
    if state == "success":
        print("✅ SUCCÈS")
        result_json = data.get('resultJson')
        print(f"Result JSON: {result_json}")
        
        if result_json:
            try:
                result = json.loads(result_json)
                print(f"Video URLs: {result.get('resultUrls')}")
            except:
                pass
    
    print("=" * 80)
    
    return {"status": "received", "task_id": task_id}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
