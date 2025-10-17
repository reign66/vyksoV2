import os
import json
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from kie_client import KieAIClient
from supabase_client import get_client
from utils.uploader import R2Uploader
from utils.video_concat import VideoEditor
from io import BytesIO

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
    duration: int  # 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60
    quality: str = "basic"

class VideoResponse(BaseModel):
    job_id: str
    status: str
    estimated_time: str
    num_clips: int
    total_credits: int

# ============= FUNCTIONS =============

def generate_prompt(niche: str, clip_index: int = None, total_clips: int = None) -> str:
    """Génère un prompt optimisé pour Sora"""
    templates = {
        "recettes": "Cinematic cooking video showing delicious recipe preparation, beautiful food styling, warm kitchen lighting, professional chef techniques, mouth-watering close-ups",
        
        "voyage": "Breathtaking travel footage showcasing stunning landscapes, cinematic drone shots, golden hour lighting, epic adventure vibes, cultural exploration, scenic beauty",
        
        "motivation": "Inspiring motivational content with dynamic visual metaphors, uplifting atmosphere, professional cinematography, energetic pacing, success imagery, empowering message",
        
        "tech": "Modern technology showcase with sleek product presentation, futuristic aesthetics, clean minimalist style, innovative tech display, professional lighting, cutting-edge visuals"
    }
    
    base = templates.get(niche.lower(), f"High-quality viral video content about {niche}, engaging visuals, professional production")
    
    # Ajouter info de séquence si multi-clips
    if clip_index is not None and total_clips is not None and total_clips > 1:
        sequence_info = f", dynamic scene {clip_index} of {total_clips}, smooth cinematic transition, continuous flow"
    else:
        sequence_info = ""
    
    return f"{base}{sequence_info}, 9:16 vertical format, TikTok optimized, high quality, cinematic"

async def process_video_generation(job_id: str, niche: str, duration: int, quality: str, user_id: str):
    """Background task : génère la vidéo (single ou multi-clips)"""
    try:
        print(f"🎬 Starting generation for job {job_id}")
        
        # Update status to generating
        supabase.table("video_jobs").update({
            "status": "generating"
        }).eq("id", job_id).execute()
        
        # Calculer le nombre de clips (chaque clip = 10s)
        num_clips = (duration + 9) // 10  # Arrondi au supérieur
        print(f"📊 Need {num_clips} clips for {duration}s video")
        
        if num_clips == 1:
            # ===== CAS SIMPLE : 1 seul clip =====
            print("🎥 Single clip generation")
            
            prompt = generate_prompt(niche)
            
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
            
            print(f"⏳ Task {task_id} submitted, waiting for callback...")
        
        else:
            # ===== CAS COMPLEXE : Multi-clips =====
            print(f"🎥 Multi-clip generation ({num_clips} clips)")
            
            # Générer tous les clips en parallèle
            tasks = []
            for i in range(num_clips):
                clip_prompt = generate_prompt(niche, i+1, num_clips)
                print(f"📝 Clip {i+1}/{num_clips} prompt: {clip_prompt[:80]}...")
                
                task = await kie.generate_video(
                    prompt=clip_prompt,
                    duration=10,
                    quality=quality,
                    remove_watermark=False
                )
                tasks.append(task)
                print(f"✅ Clip {i+1}/{num_clips} task created: {task['taskId']}")
            
            # Sauvegarder tous les task_ids en JSON
            task_ids = [t["taskId"] for t in tasks]
            supabase.table("video_jobs").update({
                "kie_task_id": json.dumps(task_ids),
                "status": "waiting_callback",
                "metadata": json.dumps({
                    "num_clips": num_clips,
                    "clips_completed": 0,
                    "clips_urls": {}
                })
            }).eq("id", job_id).execute()
            
            print(f"⏳ All {num_clips} tasks submitted, waiting for callbacks...")
        
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
    
    # Valider la durée (multiples de 5 entre 10 et 60)
    if req.duration < 10 or req.duration > 60:
        raise HTTPException(status_code=400, detail="Duration must be between 10 and 60 seconds")
    
    # Calculer le nombre de clips
    num_clips = (req.duration + 9) // 10
    
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
    
    # 2. Vérifier crédits (1 crédit par clip de 10s)
    if user_data["credits"] < num_clips:
        raise HTTPException(
            status_code=402, 
            detail=f"Crédits insuffisants. Besoin de {num_clips} crédits, vous avez {user_data['credits']}"
        )
    
    # 3. Créer job dans Supabase
    try:
        job = supabase.table("video_jobs").insert({
            "user_id": req.user_id,
            "status": "pending",
            "niche": req.niche,
            "duration": req.duration,
            "quality": req.quality,
            "prompt": generate_prompt(req.niche),
            "metadata": json.dumps({
                "num_clips": num_clips,
                "target_duration": req.duration
            })
        }).execute()
        
        job_id = job.data[0]["id"]
        print(f"📋 Job created: {job_id}")
        
    except Exception as e:
        print(f"❌ Error creating job: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    # 4. Lancer génération en background
    background_tasks.add_task(process_video_generation, job_id, req.niche, req.duration, req.quality, req.user_id)
    
    # 5. Réponse immédiate
    estimated_time = num_clips * 40  # ~40s par clip en moyenne
    return VideoResponse(
        job_id=job_id,
        status="pending",
        estimated_time=f"{estimated_time}-{estimated_time + 60}s",
        num_clips=num_clips,
        total_credits=num_clips
    )

@app.get("/api/videos/{job_id}/status")
async def get_video_status(job_id: str):
    """Check le statut d'une vidéo"""
    try:
        job = supabase.table("video_jobs").select("*").eq("id", job_id).execute()
        
        if not job.data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        job_data = job.data[0]
        
        # Parser le metadata si présent
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

@app.post("/api/callback")
async def kie_callback(payload: dict):
    """Callback Kie.ai - Traite la vidéo quand elle est prête"""
    print("=" * 80)
    print("📞 CALLBACK REÇU DE KIE.AI")
    print("=" * 80)
    
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
                # Chercher dans single task
                job = supabase.table("video_jobs").select("*").eq("kie_task_id", task_id).execute()
                
                # Si pas trouvé, chercher dans les multi-tasks
                if not job.data:
                    all_jobs = supabase.table("video_jobs").select("*").eq("status", "waiting_callback").execute()
                    for j in all_jobs.data:
                        kie_task_id = j.get("kie_task_id")
                        if kie_task_id:
                            try:
                                task_ids = json.loads(kie_task_id)
                                if task_id in task_ids:
                                    job = {"data": [j]}
                                    break
                            except:
                                pass
                
                if job.data:
                    job_id = job.data[0]["id"]
                    error_msg = f"{data.get('failCode')}: {data.get('failMsg')}"
                    
                    supabase.table("video_jobs").update({
                        "status": "failed",
                        "error": error_msg
                    }).eq("id", job_id).execute()
                    
                    print(f"❌ Job {job_id} marqué échoué")
                    
            except Exception as e:
                print(f"⚠️ Erreur update Supabase: {e}")
                import traceback
                traceback.print_exc()
    
    # Si succès
    if state == "success":
        print("✅ SUCCÈS")
        result_json_str = data.get('resultJson')
        
        if result_json_str and task_id:
            try:
                result = json.loads(result_json_str)
                video_url = result.get('resultUrls', [None])[0]
                print(f"Video URL: {video_url}")
                
                if not video_url:
                    print("⚠️ No video URL in result")
                    return {"status": "error", "message": "No video URL"}
                
                # Chercher le job (single ou multi)
                job = supabase.table("video_jobs").select("*").eq("kie_task_id", task_id).execute()
                
                # Si pas trouvé, chercher dans les multi-tasks
                if not job.data:
                    all_jobs = supabase.table("video_jobs").select("*").eq("status", "waiting_callback").execute()
                    for j in all_jobs.data:
                        kie_task_id = j.get("kie_task_id")
                        if kie_task_id:
                            try:
                                task_ids = json.loads(kie_task_id)
                                if task_id in task_ids:
                                    job = {"data": [j]}
                                    break
                            except:
                                pass
                
                if not job.data:
                    print(f"⚠️ Job not found for task_id: {task_id}")
                    return {"status": "error", "message": "Job not found"}
                
                job_data = job.data[0]
                job_id = job_data["id"]
                user_id = job_data["user_id"]
                kie_task_id_field = job_data.get("kie_task_id")
                
                # Déterminer si single ou multi-clip
                try:
                    task_ids_list = json.loads(kie_task_id_field)
                    is_multi = True
                except:
                    is_multi = False
                
                if not is_multi:
                    # ===== CAS SIMPLE : Single clip =====
                    print(f"📤 Uploading single video to R2...")
                    final_url = uploader.upload_from_url(video_url, f"{job_id}.mp4")
                    
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
                    
                    print(f"✅ Job {job_id} completed!")
                
                else:
                    # ===== CAS MULTI-CLIPS : Stocker et attendre les autres =====
                    print(f"📦 Multi-clip job, storing partial result...")
                    
                    # Récupérer metadata
                    metadata = json.loads(job_data.get("metadata", "{}"))
                    clips_urls = metadata.get("clips_urls", {})
                    num_clips = metadata.get("num_clips", len(task_ids_list))
                    
                    # Stocker l'URL du clip
                    clip_index = task_ids_list.index(task_id)
                    clips_urls[str(clip_index)] = video_url
                    metadata["clips_urls"] = clips_urls
                    metadata["clips_completed"] = len(clips_urls)
                    
                    supabase.table("video_jobs").update({
                        "metadata": json.dumps(metadata)
                    }).eq("id", job_id).execute()
                    
                    print(f"✅ Clip {clip_index + 1}/{num_clips} stored ({len(clips_urls)}/{num_clips} ready)")
                    
                    # Vérifier si tous les clips sont prêts
                    if len(clips_urls) == num_clips:
                        print(f"🎬 All {num_clips} clips ready, concatenating...")
                        
                        # Mettre en ordre les URLs
                        ordered_urls = [clips_urls[str(i)] for i in range(num_clips)]
                        
                        # Concaténer les vidéos
                        print(f"🎞️ Concatenating {num_clips} videos...")
                        concatenated_data = video_editor.concatenate_videos(ordered_urls, f"{job_id}.mp4")
                        
                        # Upload vers R2
                        print(f"📤 Uploading concatenated video to R2...")
                        video_buffer = BytesIO(concatenated_data)
                        
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
                        print(f"✅ Concatenated video uploaded: {final_url}")
                        
                        # Update Supabase
                        supabase.table("video_jobs").update({
                            "status": "completed",
                            "video_url": final_url,
                            "completed_at": "now()"
                        }).eq("id", job_id).execute()
                        
                        # Débiter crédits
                        supabase.rpc("decrement_credits", {
                            "p_user_id": user_id,
                            "p_amount": num_clips
                        }).execute()
                        
                        print(f"✅ Job {job_id} completed (multi-clip)!")
                    else:
                        print(f"⏳ Waiting for {num_clips - len(clips_urls)} more clips...")
                
            except Exception as e:
                print(f"⚠️ Erreur traitement callback: {e}")
                import traceback
                traceback.print_exc()
                
                # Marquer le job en erreur
                try:
                    if task_id:
                        job = supabase.table("video_jobs").select("*").eq("kie_task_id", task_id).execute()
                        if not job.data:
                            all_jobs = supabase.table("video_jobs").select("*").eq("status", "waiting_callback").execute()
                            for j in all_jobs.data:
                                try:
                                    task_ids = json.loads(j.get("kie_task_id", "[]"))
                                    if task_id in task_ids:
                                        job = {"data": [j]}
                                        break
                                except:
                                    pass
                        
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
