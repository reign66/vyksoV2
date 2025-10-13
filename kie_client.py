import os
import httpx
import asyncio
from typing import Literal, Optional

class KieAIClient:
    """Client pour Kie.ai Sora 2 API - Version corrigée"""
    
    BASE_URL = "https://api.kie.ai/api/v1"
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("KIE_AI_API_KEY")
        self.callback_url = os.getenv("CALLBACK_URL")
        
    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    async def generate_video(
        self,
        prompt: str,
        duration: int,
        quality: Literal["basic", "pro_720p", "pro_1080p"] = "basic",
        remove_watermark: bool = False
    ) -> dict:
        """
        Génère une vidéo via Kie.ai
        
        Args:
            prompt: Description de la vidéo (max 5000 chars)
            duration: Durée en secondes (10, 15, 20, 30, 45, 60)
            quality: basic (sora-2), pro_720p, pro_1080p
            remove_watermark: Enlever le watermark (coûte $0.05)
        
        Returns:
            dict avec taskId pour polling
        """
        
        # Map quality to model names
        model_map = {
            "basic": "sora-2-text-to-video",
            "pro_720p": "sora-2-pro-text-to-video",
            "pro_1080p": "sora-2-pro-text-to-video"
        }
        model = model_map.get(quality, "sora-2-text-to-video")
        
        # Map duration to n_frames
        # Kie.ai only supports 10s or 15s for pro models
        if quality != "basic" and duration > 15:
            duration = 15  # Cap at 15s for pro models
        
        n_frames = str(duration) if duration in [10, 15] else "10"
        
        payload = {
            "model": model,
            "callBackUrl": self.callback_url,  # Optional
            "input": {
                "prompt": prompt[:5000],  # Max 5000 chars
                "aspect_ratio": "portrait",  # 9:16 for TikTok
                "remove_watermark": remove_watermark
            }
        }
        
        # Add pro-specific params
        if quality != "basic":
            payload["input"]["n_frames"] = n_frames
            payload["input"]["size"] = "high" if quality == "pro_1080p" else "standard"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/jobs/createTask",
                headers=self._get_headers(),
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            
            # API returns: {"code": 0, "data": {"taskId": "..."}, "msg": "success"}
            if result.get("code") == 0:
                return result["data"]
            else:
                raise Exception(f"Kie.ai error: {result.get('msg')}")
    
    async def get_task_status(self, task_id: str) -> dict:
        """
        Check le statut d'une génération
        
        Returns:
            dict avec status et video_url si completed
        """
        params = {"taskId": task_id}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/jobs/recordInfo",
                headers=self._get_headers(),
                params=params
            )
            response.raise_for_status()
            result = response.json()
            
            # API returns: {"code": 0, "data": {...}, "msg": "success"}
            if result.get("code") == 0:
                return result["data"]
            else:
                raise Exception(f"Kie.ai error: {result.get('msg')}")
    
    async def poll_until_complete(self, task_id: str, max_wait: int = 600) -> dict:
        """
        Poll le statut jusqu'à completion
        
        Args:
            task_id: ID de la tâche
            max_wait: Temps max d'attente en secondes (default 10min)
        
        Returns:
            dict avec video_url
        """
        start_time = asyncio.get_event_loop().time()
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > max_wait:
                raise TimeoutError(f"Video generation timeout after {max_wait}s")
            
            status = await self.get_task_status(task_id)
            
            # Kie.ai status: "pending", "processing", "success", "failed"
            task_status = status.get("status")
            
            if task_status == "success":
                # Return video URL from result
                return {
                    "status": "completed",
                    "video_url": status.get("result", {}).get("video_url"),
                    "task_id": task_id
                }
            elif task_status == "failed":
                error_msg = status.get("error", "Unknown error")
                raise Exception(f"Generation failed: {error_msg}")
            
            # Still processing, wait 5s before re-check
            await asyncio.sleep(5)
            print(f"⏳ Task {task_id} status: {task_status} (elapsed: {int(elapsed)}s)")
    
    async def remove_watermark(self, video_url: str) -> dict:
        """
        Enlève le watermark d'une vidéo existante
        Coût: $0.05
        """
        payload = {
            "model": "sora-watermark-remover",
            "callBackUrl": self.callback_url,
            "input": {
                "video_url": video_url
            }
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/jobs/createTask",
                headers=self._get_headers(),
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") == 0:
                return result["data"]
            else:
                raise Exception(f"Kie.ai error: {result.get('msg')}")
