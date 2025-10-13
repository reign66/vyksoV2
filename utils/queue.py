"""
Queue manager pour BullMQ (optionnel pour MVP)
Pour l'instant on fait tout en async
À activer plus tard pour scale
"""
import os
from redis import Redis

def get_redis():
    """Get Redis connection"""
    redis_url = os.getenv("REDIS_URL")
    return Redis.from_url(redis_url, decode_responses=True)

# Pour plus tard quand on scale
"""
from bullmq import Queue

queue = Queue("video-generation", connection=get_redis())

async def enqueue_video_job(job_data):
    await queue.add("generate", job_data)
"""
