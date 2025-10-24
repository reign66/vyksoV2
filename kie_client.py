import os
import httpx
import asyncio
import json
from typing import Literal, Optional, List, Dict

class KieAIClient:
    """Client pour Kie.ai Sora 2 API - Version complète avec tous les modèles"""
    
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
        duration: int = 10,
        quality: Literal["basic", "pro_720p", "pro_1080p"] = "basic",
        image_urls: Optional[List[str]] = None,
        shots: Optional[List[Dict]] = None,
        model_type: Literal["text-to-video", "image-to-video", "storyboard"] = "text-to-video"
    ) -> dict:
        """
        Génère une vidéo via Kie.ai avec support de tous les modèles
        
        Args:
            prompt: Description de la vidéo (max 5000 chars)
            duration: Durée en secondes (10 ou 15)
            quality: basic (standard), pro_720p (high 720p), pro_1080p (high 1080p)
            image_urls: Liste d'URLs d'images (pour image-to-video)
            shots: Liste de scènes (pour storyboard)
            model_type: Type de modèle à utiliser
        
        Returns:
            dict avec taskId pour polling
        """
        
        # Déterminer le modèle selon le type et la qualité
        if model_type == "storyboard":
            model = "sora-2-pro-storyboard"
        elif model_type == "image-to-video":
            if quality in ["pro_720p", "pro_1080p"]:
                model = "sora-2-pro-image-to-video"
            else:
                model = "sora-2-image-to-video"
        else:  # text-to-video
            if quality in ["pro_720p", "pro_1080p"]:
                model = "sora-2-pro-text-to-video"
            else:
                model = "sora-2-text-to-video"
        
        # Map n_frames selon la durée (seulement 10 ou 15 supportés)
        n_frames = "10" if duration <= 10 else "15"
        
        # Map size selon la qualité (pour les modèles Pro)
        size_map = {
            "basic": "standard",
            "pro_720p": "standard",  # 720p
            "pro_1080p": "high"       # 1080p
        }
        size = size_map.get(quality, "standard")
        
        # Construire le payload selon le type de modèle
        payload = {
            "model": model,
            "callBackUrl": self.callback_url,
            "input": {
                "aspect_ratio": "portrait",  # 9:16 for TikTok
                "n_frames": n_frames,
                "remove_watermark": True  # Toujours enlever le watermark
            }
        }
        
        # Ajouter les paramètres spécifiques selon le modèle
        if model_type == "storyboard":
            # Mode Storyboard
            if not shots:
                raise ValueError("shots parameter is required for storyboard model")
            payload["input"]["shots"] = shots
            if image_urls:
                payload["input"]["image_urls"] = image_urls
        
        elif model_type == "image-to-video":
            # Mode Image-to-Video
            if not image_urls:
                raise ValueError("image_urls parameter is required for image-to-video model")
            payload["input"]["prompt"] = prompt[:5000]
            payload["input"]["image_urls"] = image_urls
            
            # Ajouter size pour les modèles Pro
            if quality in ["pro_720p", "pro_1080p"]:
                payload["input"]["size"] = size
        
        else:
            # Mode Text-to-Video (default)
            payload["input"]["prompt"] = prompt[:5000]
            
            # Ajouter size pour les modèles Pro
            if quality in ["pro_720p", "pro_1080p"]:
                payload["input"]["size"] = size
        
        print(f"🎬 Creating task with model: {model}")
        print(f"📦 Payload: {json.dumps(payload, indent=2)}")
        
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
    
    async def get_task_status(self, task_id: str) -> dict:
        """Check le statut d'une génération"""
        params = {"taskId": task_id}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/jobs/queryTask",
                headers=self._get_headers(),
                params=params
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") == 200:
                return result["data"]
            else:
                raise Exception(f"Kie.ai error: {result.get('msg')}")
    
    async def poll_until_complete(self, task_id: str, max_wait: int = 600) -> dict:
        """Poll le statut jusqu'à completion"""
        start_time = asyncio.get_event_loop().time()
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > max_wait:
                raise TimeoutError(f"Video generation timeout after {max_wait}s")
            
            status = await self.get_task_status(task_id)
            task_state = status.get("state")
            
            if task_state == "success":
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
            
            await asyncio.sleep(5)
            print(f"⏳ Task {task_id} status: {task_state} (elapsed: {int(elapsed)}s)")
