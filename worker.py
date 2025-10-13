"""
Worker pour génération vidéo (optionnel pour MVP)
Pour l'instant on fait tout en async dans main.py
À activer plus tard pour scale
"""
import os
import asyncio
from kie_client import KieAIClient
from utils.uploader import R2Uploader
from supabase import create_client

# Setup clients
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)
kie = KieAIClient()
uploader = R2Uploader()

async def process_video_job(job_id: str):
    """
    Process a single video generation job
    """
    try:
        # Get job from database
        job = supabase.table("video_jobs").select("*").eq("id", job_id).single().execute()
        job_data = job.data
        
        # Generate video
        task = await kie.generate_video(
            prompt=job_data["prompt"],
            duration=job_data["duration"],
            model=f"sora-2" if job_data["quality"] == "basic" else f"sora-2-pro-{job_data['quality'].split('_')[1]}"
        )
        
        # Poll until complete
        result = await kie.poll_until_complete(task["task_id"])
        
        # Upload to R2
        final_url = uploader.upload_from_url(result["video_url"], f"{job_id}.mp4")
        
        # Update database
        supabase.table("video_jobs").update({
            "status": "completed",
            "video_url": final_url,
            "completed_at": "now()"
        }).eq("id", job_id).execute()
        
        print(f"✅ Job {job_id} completed")
        
    except Exception as e:
        print(f"❌ Job {job_id} failed: {e}")
        supabase.table("video_jobs").update({
            "status": "failed",
            "error": str(e)
        }).eq("id", job_id).execute()

if __name__ == "__main__":
    print("Worker ready (not used in MVP)")
