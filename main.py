import os
import json
import stripe
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
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

# Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Models
class VideoRequest(BaseModel):
    user_id: str
    niche: Optional[str] = None
    duration: int  # 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60
    quality: str = "basic"
    custom_prompt: Optional[str] = None

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

# ============= FUNCTIONS =============

def generate_prompt(niche: str = None, custom_prompt: str = None, clip_index: int = None, total_clips: int = None) -> str:
    """Génère un prompt optimisé pour Sora"""
    
    # Si custom_prompt fourni, l'utiliser en priorité
    if custom_prompt:
        base = custom_prompt
    else:
        # Sinon utiliser les templates de niche
        templates = {
            "recettes": "Cinematic cooking video showing delicious recipe preparation, beautiful food styling, warm kitchen lighting, professional chef techniques, mouth-watering close-ups",
            
            "voyage": "Breathtaking travel footage showcasing stunning landscapes, cinematic drone shots, golden hour lighting, epic adventure vibes, cultural exploration, scenic beauty",
            
            "motivation": "Inspiring motivational content with dynamic visual metaphors, uplifting atmosphere, professional cinematography, energetic pacing, success imagery, empowering message",
            
            "tech": "Modern technology showcase with sleek product presentation, futuristic aesthetics, clean minimalist style, innovative tech display, professional lighting, cutting-edge visuals"
        }
        
        base = templates.get(niche.lower() if niche else "", f"High-quality viral video content, engaging visuals, professional production")
    
    # Ajouter info de séquence si multi-clips
    if clip_index is not None and total_clips is not None and total_clips > 1:
        sequence_info = f", dynamic scene {clip_index} of {total_clips}, smooth cinematic transition, continuous flow"
    else:
        sequence_info = ""
    
    return f"{base}{sequence_info}, 9:16 vertical format, TikTok optimized, high quality, cinematic"

def calculate_credits_cost(duration: int, quality: str) -> int:
    """Calcule le coût en crédits selon la durée et la qualité"""
    num_clips = (duration + 9) // 10
    
    if quality == "basic":
        return num_clips * 1  # 1 crédit par clip
    elif quality == "pro_720p":
        return num_clips * 3  # 3 crédits par clip
    elif quality == "pro_1080p":
        return num_clips * 5  # 5 crédits par clip
    else:
        return num_clips

async def process_video_generation(job_id: str, niche: str, duration: int, quality: str, user_id: str, custom_prompt: str = None):
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
            
            prompt = generate_prompt(niche, custom_prompt)
            
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
                clip_prompt = generate_prompt(niche, custom_prompt, i+1, num_clips)
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
    
    # Valider la durée
    if req.duration < 10 or req.duration > 60:
        raise HTTPException(status_code=400, detail="Duration must be between 10 and 60 seconds")
    
    # Valider qu'on a soit niche, soit custom_prompt
    if not req.niche and not req.custom_prompt:
        raise HTTPException(status_code=400, detail="Either niche or custom_prompt is required")
    
    # Calculer le nombre de clips
    num_clips = (req.duration + 9) // 10
    
    # Calculer le coût en crédits selon la qualité
    required_credits = calculate_credits_cost(req.duration, req.quality)
    
    # 1. Vérifier/créer user
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
    
    # 2. Vérifier crédits
    if user_data["credits"] < required_credits:
        raise HTTPException(
            status_code=402, 
            detail=f"Crédits insuffisants. Besoin de {required_credits} crédits, vous avez {user_data['credits']}"
        )
    
    # 3. Créer job dans Supabase
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
                "custom_prompt": req.custom_prompt
            })
        }).execute()
        
        job_id = job.data[0]["id"]
        print(f"📋 Job created: {job_id}")
        
    except Exception as e:
        print(f"❌ Error creating job: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    # 4. Lancer génération en background
    background_tasks.add_task(
        process_video_generation, 
        job_id, 
        req.niche, 
        req.duration, 
        req.quality, 
        req.user_id,
        req.custom_prompt
    )
    
    # 5. Réponse immédiate
    estimated_time = num_clips * 40  # ~40s par clip en moyenne
    return VideoResponse(
        job_id=job_id,
        status="pending",
        estimated_time=f"{estimated_time}-{estimated_time + 60}s",
        num_clips=num_clips,
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

# ============= STRIPE ENDPOINTS =============

@app.post("/api/stripe/create-checkout")
async def create_checkout_session(req: CheckoutRequest):
    """Créer une session Stripe Checkout pour abonnement"""
    
    # Map des Price IDs
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
                    'unit_amount': req.amount * 100  # en centimes
                },
                'quantity': 1,
            }],
            mode='payment',  # Paiement unique, pas subscription
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
    
    # Gérer l'événement checkout.session.completed
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        metadata = session.get('metadata', {})
        user_id = metadata.get('user_id')
        
        # Si c'est un achat de crédits (pas une subscription)
        if metadata.get('type') == 'credit_purchase':
            credits_to_add = int(metadata.get('credits', 0))
            
            print(f"💳 Credit purchase: {credits_to_add} credits for user {user_id}")
            
            try:
                # Récupérer les crédits actuels
                user = supabase.table("users").select("credits").eq("id", user_id).single().execute()
                current_credits = user.data.get('credits', 0)
                
                # Ajouter les crédits
                supabase.table("users").update({
                    "credits": current_credits + credits_to_add
                }).eq("id", user_id).execute()
                
                print(f"✅ Added {credits_to_add} credits to user {user_id} (total: {current_credits + credits_to_add})")
            except Exception as e:
                print(f"❌ Error adding credits: {e}")
        
        # Si c'est un abonnement
        elif metadata.get('type') == 'subscription':
            plan = metadata.get('plan')
            
            # Crédits selon le plan
            credits_map = {
                "starter": 60,   # 10 vidéos × 6 crédits
                "pro": 120,      # 20 vidéos × 6 crédits
                "max": 180       # 30 vidéos × 6 crédits
            }
            
            print(f"✅ Subscription {plan} for user {user_id}")
            
            # Mettre à jour l'utilisateur
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
    
    # Gérer le renouvellement mensuel
    elif event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        subscription_id = invoice.get('subscription')
        
        if subscription_id:
            try:
                # Récupérer l'utilisateur via subscription_id
                user = supabase.table("users").select("*").eq("stripe_subscription_id", subscription_id).single().execute()
                
                if user.data:
                    plan = user.data['plan']
                    credits_map = {
                        "starter": 60,
                        "pro": 120,
                        "max": 180
                    }
                    
                    # Recharger les crédits mensuels
                    supabase.table("users").update({
                        "credits": credits_map.get(plan, 60)
                    }).eq("id", user.data['id']).execute()
                    
                    print(f"✅ Monthly credits recharged for user {user.data['id']}: {credits_map.get(plan)} credits")
            except Exception as e:
                print(f"❌ Error recharging credits: {e}")
    
    return {"status": "success"}

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
                job_result = supabase.table("video_jobs").select("*").eq("kie_task_id", task_id).execute()
                
                # Si pas trouvé, chercher dans les multi-tasks
                if not job_result.data:
                    all_jobs = supabase.table("video_jobs").select("*").eq("status", "waiting_callback").execute()
                    for j in all_jobs.data:
                        kie_task_id = j.get("kie_task_id")
                        if kie_task_id:
                            try:
                                task_ids = json.loads(kie_task_id)
                                if task_id in task_ids:
                                    job_result = type('obj', (object,), {'data': [j]})()
                                    break
                            except:
                                pass
                
                if job_result.data:
                    job_id = job_result.data[0]["id"]
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
                job_result = supabase.table("video_jobs").select("*").eq("kie_task_id", task_id).execute()
                
                # Si pas trouvé, chercher dans les multi-tasks
                if not job_result.data:
                    all_jobs = supabase.table("video_jobs").select("*").eq("status", "waiting_callback").execute()
                    for j in all_jobs.data:
                        kie_task_id = j.get("kie_task_id")
                        if kie_task_id:
                            try:
                                task_ids = json.loads(kie_task_id)
                                if task_id in task_ids:
                                    job_result = type('obj', (object,), {'data': [j]})()
                                    break
                            except:
                                pass
                
                if not job_result.data:
                    print(f"⚠️ Job not found for task_id: {task_id}")
                    return {"status": "error", "message": "Job not found"}
                
                job_data = job_result.data[0]
                job_id = job_data["id"]
                user_id = job_data["user_id"]
                quality = job_data.get("quality", "basic")
                duration = job_data.get("duration", 10)
                kie_task_id_field = job_data.get("kie_task_id")
                
                # Calculer les crédits à débiter
                credits_to_deduct = calculate_credits_cost(duration, quality)
                
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
                    
                    # Débiter crédits
                    supabase.rpc("decrement_credits", {
                        "p_user_id": user_id,
                        "p_amount": credits_to_deduct
                    }).execute()
                    
                    print(f"✅ Job {job_id} completed! ({credits_to_deduct} credits deducted)")
                
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
                        print(f"🎬 All {num_clips} clips ready, starting concatenation...")
                        
                        try:
                            # Mettre en ordre les URLs
                            ordered_urls = [clips_urls[str(i)] for i in range(num_clips)]
                            print(f"📹 Ordered URLs: {ordered_urls}")
                            
                            # Concaténer les vidéos
                            print(f"🎞️ Concatenating {num_clips} videos with ffmpeg...")
                            concatenated_data = video_editor.concatenate_videos(ordered_urls, f"{job_id}.mp4")
                            
                            # VÉRIFIER que les données sont bien chargées
                            if not concatenated_data or len(concatenated_data) == 0:
                                raise Exception("Concatenation returned empty data")
                            
                            print(f"✅ Concatenation successful, video size: {len(concatenated_data)} bytes")
                            
                            # Upload vers R2
                            print(f"📤 Uploading concatenated video to R2...")
                            video_buffer = BytesIO(concatenated_data)
                            
                            uploader.s3.upload_fileobj(
                                video_buffer,
                                uploader.bucket,
                                f"{job_id}.mp4",
                                ExtraArgs={
                                    'ContentType': 'video/mp4',
                                    'CacheControl': 'public, max-age=31536000'
                                    # ACL supprimé - R2 ne le supporte pas
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
                                "p_amount": credits_to_deduct
                            }).execute()
                            
                            print(f"✅ Job {job_id} completed (multi-clip, {num_clips} clips concatenated, {credits_to_deduct} credits deducted)!")
                        
                        except Exception as concat_error:
                            print(f"❌ Concatenation or upload failed: {concat_error}")
                            import traceback
                            traceback.print_exc()
                            
                            # Marquer le job en erreur
                            supabase.table("video_jobs").update({
                                "status": "failed",
                                "error": f"Concatenation failed: {str(concat_error)}"
                            }).eq("id", job_id).execute()
                    else:
                        print(f"⏳ Waiting for {num_clips - len(clips_urls)} more clips...")
                
            except Exception as e:
                print(f"⚠️ Erreur traitement callback: {e}")
                import traceback
                traceback.print_exc()
                
                # Marquer le job en erreur
                try:
                    if task_id:
                        job_result = supabase.table("video_jobs").select("*").eq("kie_task_id", task_id).execute()
                        if not job_result.data:
                            all_jobs = supabase.table("video_jobs").select("*").eq("status", "waiting_callback").execute()
                            for j in all_jobs.data:
                                try:
                                    task_ids = json.loads(j.get("kie_task_id", "[]"))
                                    if task_id in task_ids:
                                        job_result = type('obj', (object,), {'data': [j]})()
                                        break
                                except:
                                    pass
                        
                        if job_result.data:
                            supabase.table("video_jobs").update({
                                "status": "failed",
                                "error": str(e)
                            }).eq("id", job_result.data[0]["id"]).execute()
                except:
                    pass
    
    print("=" * 80)
    
    return {"status": "received", "task_id": task_id}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
                            
                            # Marquer le job en erreur
