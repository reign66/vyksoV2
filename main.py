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
    Background task : génère la vidéo (peut être multi-clips)
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
            num_clips += 1  # Arrondir au sup
        
        print(f"📊 Need {num_clips} clips for {duration}s video")
        
        if num_clips == 1:
            # ===== CAS SIMPLE : 1 seul clip (10s) =====
            prompt = generate_prompt(niche, 10)
            
            # 1. Lancer génération Kie.ai
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
                "kie_task_id": task_id
            }).eq("id", job_id).execute()
            
            # 2. Poll jusqu'à completion
            result = await kie.poll_until_complete(task_id, max_wait=600)
            video_url = result["video_url"]
            
            print(f"✅ Video generated: {video_url}")
            
            # 3. Upload vers R2
            final_url = uploader.upload_from_url(video_url, f"{job_id}.mp4")
        
        else:
            # ===== CAS COMPLEXE : Plusieurs clips à concaténer =====
            print(f"🎥 Generating {num_clips} clips in parallel...")
            
            # Créer des prompts pour chaque clip
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
                "kie_task_id": json.dumps(task_ids)  # Stocker comme JSON array
            }).eq("id", job_id).execute()
            
            # Poll tous les clips en parallèle
            print(f"⏳ Waiting for all {num_clips} clips...")
            results = await asyncio.gather(*[
                kie.poll_until_complete(task["taskId"], max_wait=600)
                for task in tasks
            ])
            
            video_urls = [r["video_url"] for r in results]
            print(f"✅ All {num_clips} clips generated")
            
            # Concaténer les vidéos
            print(f"🎬 Concatenating {num_clips} clips...")
            concatenated_video = video_editor.concatenate_videos(
                video_urls, 
                f"{job_id}.mp4"
            )
            
            # Upload vers R2
            print(f"📤 Uploading concatenated video to R2...")
            video_buffer = BytesIO(concatenated_video)
            
            uploader.s3.upload_fileobj(
                video_buffer,
                uploader.bucket,
                f"{job_id}.mp4",
                ExtraArgs={
                    'ContentType': 'video/mp4',
                    'CacheControl': 'public, max-age=31536000',
                    'ACL': 'public-read'
                }
            )
            
            final_url = f"{uploader.public_base}/{job_id}.mp4"
            print(f"✅ Uploaded: {final_url}")
        
        # 4. Update Supabase
        supabase.table("video_jobs").update({
            "status": "completed",
            "video_url": final_url,
            "completed_at": "now()"
        }).eq("id", job_id).execute()
        
        # 5. Débiter crédits (1 crédit par clip de 10s)
        credits_to_deduct = num_clips
        supabase.rpc("decrement_credits", {
            "p_user_id": user_id,
            "p_amount": credits_to_deduct
        }).execute()
        
        print(f"✅ Job {job_id} completed successfully ({credits_to_deduct} credits used)")
        
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
