import os
import httpx
import asyncio
import json
from typing import Literal, Optional, List

class VeoAIClient:
    """Client pour Veo 3.1 API via Kie.ai"""
    
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
        model: Literal["veo3", "veo3_fast"] = "veo3_fast",
        aspect_ratio: Literal["16:9", "9:16"] = "9:16",
        image_urls: Optional[List[str]] = None,
        generation_type: Optional[Literal["TEXT_2_VIDEO", "FIRST_AND_LAST_FRAMES_2_VIDEO", "REFERENCE_2_VIDEO"]] = None,
        seeds: Optional[int] = None,
        watermark: Optional[str] = None
    ) -> dict:
        """
        Génère une vidéo via Veo 3.1
        
        Args:
            prompt: Description de la vidéo (max 5000 chars)
            model: veo3 (quality) ou veo3_fast (rapide)
            aspect_ratio: 16:9 (landscape) ou 9:16 (portrait)
            image_urls: Liste d'URLs d'images (1-3 images)
            generation_type: Type de génération (auto si non spécifié)
            seeds: Seed aléatoire (10000-99999)
            watermark: Texte du watermark (optionnel)
        
        Returns:
            dict avec taskId pour polling
        """
        
        # Construire le payload
        payload = {
            "prompt": prompt[:5000],
            "model": model,
            "aspectRatio": aspect_ratio,
            "callBackUrl": self.callback_url,
            "enableTranslation": True,  # Toujours traduire en anglais
            "enableFallback": False  # Deprecated mais on le met à False
        }
        
        # Ajouter les images si présentes
        if image_urls and len(image_urls) > 0:
            payload["imageUrls"] = image_urls[:3]  # Max 3 images
            
            # Déterminer le type de génération automatiquement si non spécifié
            if not generation_type:
                if len(image_urls) == 1:
                    generation_type = "FIRST_AND_LAST_FRAMES_2_VIDEO"
                elif len(image_urls) >= 2:
                    generation_type = "REFERENCE_2_VIDEO"
        
        # Ajouter le type de génération
        if generation_type:
            payload["generationType"] = generation_type
        
        # Ajouter seed si spécifié
        if seeds:
            payload["seeds"] = max(10000, min(99999, seeds))
        
        # Ajouter watermark si spécifié (mais on ne veut pas de watermark)
        # On ne met pas watermark pour avoir des vidéos propres
        
        print(f"🎬 Creating Veo 3.1 task")
        print(f"📦 Payload: {json.dumps(payload, indent=2)}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/veo/generate",
                headers=self._get_headers(),
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") == 200:
                return {"taskId": result["data"]["taskId"]}
            else:
                raise Exception(f"Veo AI error: {result.get('msg')}")
    
    async def get_task_status(self, task_id: str) -> dict:
        """Check le statut d'une génération Veo"""
        params = {"taskId": task_id}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.BASE_URL}/veo/query",
                headers=self._get_headers(),
                params=params
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") == 200:
                return result["data"]
            else:
                raise Exception(f"Veo AI error: {result.get('msg')}")
