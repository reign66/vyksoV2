import os
import httpx
import asyncio
import json
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
        
        payload = {
            "model": model,
            "callBackUrl": self.callback_url,
            "input": {
                "prompt": prompt[:5000],  # Max 5000 chars
                "aspect_ratio": "portrait",  # 9:16 for TikTok
                "remove_watermark": remove_watermark
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
            
            # FIX: API returns code 200, not 0
            if result.get("code") == 200:
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
                f"{self.BASE_URL}/jobs/queryTask",  # FIX: correct endpoint
                headers=self._get_headers(),
                params=params
            )
            response.raise_for_status()
            result = response.json()
            
            # FIX: API returns code 200, not 0
            if result.get("code") == 200:
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
            
            # FIX: correct field name is "state" not "status"
            task_state = status.get("state")
            
            if task_state == "success":
                # Parse resultJson string to get video URL
                result_json_str = status.get("resultJson", "{}")
                result_json = json.loads(result_json_str)
                video_url = result_json.get("resultUrls", [None])[0]
                
                return {
                    "status": "completed",
                    "video_url": video_url,
                    "task_id": task_id
                }
            elif task_state == "fail":
                error_msg = f"{status.get('failCode')}: {status.get('failMsg')}"
                raise Exception(f"Generation failed: {error_msg}")
            
            # Still processing, wait 5s before re-check
            await asyncio.sleep(5)
            print(f"⏳ Task {task_id} status: {task_state} (elapsed: {int(elapsed)}s)")
    
    async def generate_long_video(
        self,
        base_prompt: str,
        target_duration: int = 60,
        quality: str = "basic"
    ) -> list[dict]:
        """
        Génère plusieurs vidéos de 10s pour créer une vidéo longue
        
        Args:
            base_prompt: Prompt de base
            target_duration: Durée cible en secondes (ex: 60 pour 1min)
            quality: Qualité vidéo
        
        Returns:
            Liste de dict avec video_url pour chaque clip
        """
        num_clips = target_duration // 10
        
        # Créer des variations du prompt pour chaque clip
        prompts = []
        for i in range(num_clips):
            scene_prompt = f"{base_prompt}, scene {i+1} of {num_clips}, smooth transition"
            prompts.append(scene_prompt)
        
        print(f"🎬 Generating {num_clips} clips of 10s each...")
        
        # Lancer toutes les générations en parallèle
        tasks = []
        for i, prompt in enumerate(prompts):
            print(f"🎥 Launching clip {i+1}/{num_clips}")
            task = await self.generate_video(
                prompt=prompt,
                duration=10,
                quality=quality,
                remove_watermark=False
            )
            tasks.append(task)
        
        # Poll toutes les vidéos en parallèle
        print(f"⏳ Waiting for all {num_clips} clips to complete...")
        completed = await asyncio.gather(*[
            self.poll_until_complete(task["taskId"])
            for task in tasks
        ])
        
        print(f"✅ All {num_clips} clips generated successfully")
        return completed
    
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
            
            if result.get("code") == 200:
                return result["data"]
            else:
                raise Exception(f"Kie.ai error: {result.get('msg')}")
