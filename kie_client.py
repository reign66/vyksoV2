import os
import httpx
import asyncio
from typing import Literal

class KieAIClient:
    """Client pour Kie.ai Sora 2 API"""
    
    BASE_URL = "https://api.kie.ai/v1"
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("KIE_AI_API_KEY")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    async def generate_video(
        self,
        prompt: str,
        duration: int,
        model: Literal["sora-2", "sora-2-pro-720p", "sora-2-pro-1080p"] = "sora-2"
    ) -> dict:
        """
        Génère une vidéo via Kie.ai
        
        Args:
            prompt: Description de la vidéo
            duration: Durée en secondes (10-60)
            model: Modèle Sora à utiliser
        
        Returns:
            dict avec task_id pour polling
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "duration": duration,
            "aspect_ratio": "9:16"  # TikTok format
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/video/generate",
                headers=self.headers,
                json=payload
            )
            response.raise_for_status()
            return response.json()
    
    async def get_task_status(self, task_id: str) -> dict:
        """Check le statut d'une génération"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/tasks/{task_id}",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
    
    async def remove_watermark(self, video_url: str) -> dict:
        """Enlève le watermark d'une vidéo"""
        payload = {"video_url": video_url}
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/watermark/remove",
                headers=self.headers,
                json=payload
            )
            response.raise_for_status()
            return response.json()
    
    async def poll_until_complete(self, task_id: str, max_wait: int = 300) -> dict:
        """
        Poll le statut jusqu'à completion
        
        Args:
            task_id: ID de la tâche
            max_wait: Temps max d'attente en secondes
        
        Returns:
            dict avec video_url ou erreur
        """
        start_time = asyncio.get_event_loop().time()
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > max_wait:
                raise TimeoutError(f"Video generation timeout after {max_wait}s")
            
            status = await self.get_task_status(task_id)
            
            if status["status"] == "completed":
                return status
            elif status["status"] == "failed":
                raise Exception(f"Generation failed: {status.get('error')}")
            
            # Wait 3s avant re-check
            await asyncio.sleep(3)
